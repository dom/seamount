# pi-forge

### A Hosted Thermocline-Compliant Compute Forge — Reference Implementation

**Version:** 0.1.0
**Status:** Reference implementation — MIT licensed
**Implements:** Thermocline 0.3.0+
**Works with:** Photophore 0.3.0+

---

## What This Is

pi-forge is the simplest possible Thermocline-compliant compute forge. It receives a
Thermocline task envelope, computes π to the requested number of digits (max 999), and
returns a signed Thermocline task result envelope.

Its purpose is not to be useful. Its purpose is to be **correct** — to demonstrate
every required behavior of a Thermocline-compliant forge in a payload simple enough to
read in five minutes.

If your client can talk to pi-forge, it can talk to any Thermocline forge.

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
| `FORGE_KEY_SCHEME` | `none` | Key scheme for signatures (`none` = no cryptographic signing; use `brine` for ed25519) |
| `FORGE_PORT` | `5100` | Port to bind |

> **Note on `key_scheme: none`:** The reference implementation defaults to `none`
> to eliminate key management overhead for development and testing. `none` is a
> valid declared scheme per the Thermocline spec — honest about the absence of a
> signature guarantee. For production use, configure `FORGE_KEY_SCHEME=brine` and
> provide a keypair via the identity provider interface.

---

## API

### `POST /task`

Accepts a Thermocline task envelope. Returns a Thermocline task result envelope.

**Request:** `Content-Type: application/json` — Thermocline task envelope body.

**Response 200:** Thermocline task result envelope.

**Response 422:** Thermocline error envelope — invalid parameters.

**Response 400:** Thermocline error envelope — malformed or unrecognized envelope.

**Response 415:** If `Content-Type` is not `application/json`.

---

### `GET /health`

Returns forge health and identity.

```json
{
  "status": "ok",
  "forge": "pi-forge",
  "thermocline_version": "0.3.0",
  "node_id": "pi-forge-local",
  "key_scheme": "none",
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
  "thermocline": "0.3.0",
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
| `MALFORMED_ENVELOPE` | 400 | Envelope is not valid JSON or is missing required fields |
| `SIGNATURE_INVALID` | 400 | `dispatch_signature` present but fails verification |

---

## Privacy Properties

pi-forge holds **no private context**. A well-formed task envelope for this forge
carries only `digits` in `task.parameters` — a public integer. There is no reason
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
| Verifies `dispatch_signature` when key_scheme ≠ `none` | ✅ (key_scheme: none by default) |
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
