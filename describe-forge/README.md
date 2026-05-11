# describe-forge

> Thermocline reference forge that exercises the **core privacy primitive**
> end-to-end: receive a tier-1 shadow envelope, emit a templated description.
> First reference forge to exercise shadow handling on a real wire.

## Purpose

`pi-forge` proved a Thermocline-compliant forge could compute a mathematical
result. `describe-forge` proves a forge can **describe a shadow** without ever
seeing the underlying content — the entire FORGE-03 requirement (CONTEXT D-02):

- Accept task envelopes with `task.type` in `{shadow.describe, data.compute}`
  and `context[]` containing at least one tier-1 shadow block.
- For each tier-1 shadow, emit a description using the normative template:
  ```
  "This forge received a shadow of type '<content_type>' with relevance <relevance>."
  ```
- Refuse zero-shadow envelopes with `UNSUPPORTED_TASK_TYPE` (HTTP 400).
- Mixed-tier handling: tier-2 inline content blocks are COUNTED in
  `outputs.note` but NEVER read or echoed. Privacy invariant T-03-11.

## Wire Shape

### Request (POST /task)
```json
{
  "thermocline": "0.3.1",
  "type": "task",
  "envelope_id": "...",
  "issued_at": "2026-...",
  "issuer": "sovereign-node",
  "task": { "type": "shadow.describe", "instruction": "...", "parameters": {} },
  "context": [
    { "tier": 1, "shadow": { "shadow_id": "s1", "content_type": "document", "relevance": 0.85 } }
  ],
  "result_policy": { "persist_to_shared": [...], "return_only": [...], "strip_before_persist": [...] },
  "dispatch_signature": { "key_scheme": "brine", "node_id": "sovereign-node", "...": "..." }
}
```

### Response (200)
```json
{
  "thermocline": "0.3.1",
  "type": "task_result",
  "envelope_id": "...",
  "result_id": "...",
  "completed_at": "2026-...",
  "responder": "describe-forge-local",
  "outputs": {
    "descriptions": [
      { "shadow_id": "s1", "content_type": "document", "relevance": 0.85,
        "description": "This forge received a shadow of type 'document' with relevance 0.85." }
    ],
    "note": null
  },
  "provenance": {
    "shadows_received": ["s1"],
    "tiers_present": [1],
    "local_tiers_present": false
  },
  "receipt_signature": { "key_scheme": "brine", "node_id": "...", "sig": "<128-char hex>" }
}
```

## Bootstrap

```bash
# 1. Create the venv and install (one time)
python3.11 -m venv .venv
.venv/bin/pip install -e .

# 2. Initialize the forge keypair (idempotent)
.venv/bin/python -m describe_forge init

# 3. Serve
.venv/bin/python -m describe_forge serve
# -> DESCRIBEFORGE_READY port=5200
```

## Keystore Namespace

Keypairs live under platform-keystore service `seamount.describeforge`
(override via `DESCRIBEFORGE_KEYRING_SERVICE` env var). Distinct from
pi-forge's `seamount.piforge` namespace per T-03-13 (forge identity
confusion mitigation).

## Tests

```bash
.venv/bin/python -m pytest tests/ -xvs
```

The privacy regression test plants a magic string `BEWARE-MAGIC-STRING` into
a tier-2 inline content block and asserts the magic string never appears in
the response body. If this test ever fails the privacy contract is broken.

## License

MIT.
