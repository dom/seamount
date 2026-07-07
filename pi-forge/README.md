# pi-forge

### A Hosted Thermocline-Compliant Compute Forge (Reference Implementation)

**Version:** 0.1.0
**Status:** Reference implementation, MIT licensed
**Implements:** Thermocline 0.4.0+
**Works with:** Photophore 0.3.0+

---

## What This Is

pi-forge is the simplest possible Thermocline-compliant compute forge. It receives a
Thermocline task envelope, computes π to the requested number of digits (max 999), and
returns a signed Thermocline task result envelope.

Its purpose is not to be useful. Its purpose is to be **correct**. It demonstrates
every required behavior of a Thermocline-compliant forge in a payload simple enough to
read in five minutes.

If your client can talk to pi-forge, it can talk to any Thermocline forge.

---

## Live Reference Deployment

A public reference instance is running at **https://pi.dom.net**. This
section is the suite's standing TOFU notary for the deployed brine pubkey:
clients should pin the BLAKE3 fingerprint below on first contact and treat
any change as a re-deployment event.

| Field | Value |
|---|---|
| URL | `https://pi.dom.net` |
| Endpoints | `GET /pubkey`, `GET /health`, `POST /task` |
| Identity | `pi-forge` |
| Key scheme | `brine` (ed25519) |
| Public key (hex) | `a45dc8374bb2db966d08fd45786292fe65bcac38e4dea09d2ef11ce879f61ee3` |
| BLAKE3 fingerprint | `blake3:f187ea52e306d9c715b0ce9dac0925e8dc92d6cab7c47e2256ed3a67fcd86cf7` |
| First deployed | 2026-05-14 |
| Deploy artifacts | [`deploy/`](./deploy/) (see [`deploy/README.md`](./deploy/README.md)) |

Verify yourself, end-to-end, from a clean machine:

```bash
# Confirm the live deployment's pubkey matches this README.
curl -s https://pi.dom.net/pubkey \
  | jq -r .pubkey \
  | xxd -r -p \
  | b3sum   # python alternative: python3 -c 'import sys,blake3; print(blake3.blake3(bytes.fromhex(sys.argv[1])).hexdigest())' "$(curl -s https://pi.dom.net/pubkey | jq -r .pubkey)"
# expected: f187ea52e306d9c715b0ce9dac0925e8dc92d6cab7c47e2256ed3a67fcd86cf7

# Verify a signed task result against the published pubkey via thermocline-py.
curl -sX POST https://pi.dom.net/task \
  -H 'content-type: application/json' \
  --data @examples/task-100-digits.json \
  | jq .
```

Re-deployments (key rotation) append a row to a `### Previous fingerprints`
table below; old fingerprints are never removed (append-only TOFU history).

---

## Task Contract

**Accepted task type:** `data.compute`

**Input (in `task.parameters`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `digits` | integer | yes | Number of digits of π to compute. 1–999 inclusive. |

**Output (in `task_result.outputs`):**

| Field | Description |
|-------|-------------|
| `pi` | String — π to the requested number of decimal places (e.g. `"3.14159..."`) |
| `digits_computed` | Integer — echoes the requested digit count |
| `algorithm` | String — algorithm used (always `"mpmath"` in this implementation) |

**Error behavior:**

If `digits` is missing, non-integer, or outside [1, 999], the forge returns HTTP 422
with a Thermocline error envelope (see Error Envelopes section below).

---

## Envelope Flow

```
Tasker (sovereign node)                 pi-forge (forge)
────────────────────────                ─────────────────
POST /task  ──────────────────────────► validate envelope
                                        verify dispatch_signature
                                        check task.type == "data.compute"
                                        validate digits in [1, 999]
                                        compute π
                                        build task_result envelope
                                        sign receipt_signature
            ◄─────────────────────────  200 OK — task_result JSON
```

The forge holds **nothing** after the response is dispatched. No database. No log of
task contents. No job history. The Pi digits are computed inline and discarded after
the result envelope is returned.

---

## Running Locally

**Requirements:** Python 3.11+ · `mpmath` · `flask`

```bash
pip install mpmath flask
python server.py
# Listening on http://127.0.0.1:5100
```

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `FORGE_NODE_ID` | `pi-forge-local` | Node identity declared in receipt signatures |
| `FORGE_KEY_SCHEME` | `brine` | Key scheme for signatures (`brine` = ed25519 via the platform keystore; `none` = dev mode, no cryptographic signing) |
| `FORGE_REQUIRE_DISPATCH_SIG` | on when `FORGE_KEY_SCHEME=brine` | When on, envelopes without a verified brine `dispatch_signature` are rejected with `SIGNATURE_INVALID` (including `key_scheme: none` downgrades). Set `0` only for dev |
| `FORGE_PORT` | `5100` | Port to bind |
| `FORGE_BIND_HOST` | `127.0.0.1` | Bind host. Non-loopback (`0.0.0.0`) is an explicit opt-in; run behind a reverse proxy |
| `FORGE_MAX_CONTENT_LENGTH` | `1048576` | Maximum request body size in bytes; larger bodies get a structured 413 |
| `PIFORGE_KEYRING_SERVICE` | `seamount.piforge` | Keystore namespace for the forge keypair |
| `PIFORGE_IDENTITY` | `pi-forge` | Keystore entry name |

> **Note on `key_scheme: none`:** the production default is `brine` (run
> `pi-forge init` once to create the keypair). `FORGE_KEY_SCHEME=none` remains
> supported for development and regression replay: receipts carry `sig: null`
> (honest absence of guarantee) and dispatch-signature enforcement defaults
> off. A `brine` forge never accepts an envelope-declared `key_scheme: none`.

---

## API

### `POST /task`

Accepts a Thermocline task envelope. Returns a Thermocline task result envelope.

**Request:** `Content-Type: application/json`, with a Thermocline task envelope body.

**Response 200:** Thermocline task result envelope.

**Response 422:** Thermocline error envelope, invalid parameters.

**Response 400:** Thermocline error envelope, malformed or unrecognized envelope.

**Response 415:** If `Content-Type` is not `application/json`.

---

### `GET /health`

Returns forge health and identity.

```json
{
  "status": "ok",
  "forge": "pi-forge",
  "thermocline_version": "0.3.1",
  "node_id": "pi-forge-local",
  "key_scheme": "brine",
  "require_dispatch_sig": true,
  "max_digits": 999
}
```

---

## Example Request

```bash
curl -X POST http://localhost:5100/task \
  -H "Content-Type: application/json" \
  -d @examples/task-100-digits.json
```

---

## Error Envelopes

pi-forge returns a structured error body for all non-2xx responses:

```json
{
  "thermocline": "0.3.1",
  "type": "task_error",
  "envelope_id": "<echoed from request, or null if unparseable>",
  "error": {
    "code": "INVALID_PARAMETERS",
    "message": "digits must be an integer between 1 and 999"
  }
}
```

**Error codes:**

| Code | HTTP | Meaning |
|------|------|---------|
| `INVALID_PARAMETERS` | 422 | Missing, wrong-type, or out-of-range `digits` |
| `UNSUPPORTED_VERSION` | 400 | Unrecognized `thermocline` version in envelope |
| `UNSUPPORTED_TASK_TYPE` | 400 | `task.type` is not `data.compute` |
| `MALFORMED_ENVELOPE` | 400/413/415 | Envelope is not valid JSON, is missing required fields, exceeds the size limit, or is sent with a non-JSON `Content-Type` |
| `SIGNATURE_INVALID` | 401 | `dispatch_signature` missing, downgraded to `none`, or fails verification (when required, the default) |

---

## Privacy Properties

pi-forge holds **no private context**. A well-formed task envelope for this forge
carries only `digits` in `task.parameters`, a public integer. There is no reason
to send private context, and the forge ignores any `context[]` blocks present.

The forge:
- Does **not** log envelope contents
- Does **not** persist task inputs, outputs, or provenance
- Does **not** access any system outside the request/response cycle
- **Does** return a receipt signature (or `sig: null` if `key_scheme: none`)

This makes pi-forge a valid Tier-2 forge: all data in the envelope is public by
nature of the task, and the privacy guarantee is trivially satisfied.

---

## Conformance Checklist

Use this to verify any Thermocline forge implementation, not just pi-forge.

| Requirement | pi-forge |
|-------------|----------|
| Validates envelope JSON structure | ✅ |
| Rejects unrecognized `thermocline` versions | ✅ |
| Rejects unsupported task types | ✅ |
| Requires a verified `dispatch_signature` (brine config, the default) | ✅ (`FORGE_REQUIRE_DISPATCH_SIG=0` is the dev opt-out) |
| Returns `task_result` with correct `envelope_id` | ✅ |
| Returns `receipt_signature` block | ✅ |
| Returns `provenance.tiers_present` | ✅ |
| Holds no state after response | ✅ |
| Returns structured error envelopes | ✅ |

---

## Files

```
pi-forge/
├── README.md          — this file
├── server.py          — forge server (Flask)
├── pi.py              — π computation (mpmath)
├── envelope.py        — Thermocline envelope builder/validator
└── examples/
    ├── task-100-digits.json     — example task envelope
    └── result-100-digits.json   — expected result envelope
```

---

*pi-forge is maintained as part of the Thermocline Suite reference implementation set.*
*MIT licensed.*
