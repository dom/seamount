# `forge_conformance` — Thermocline Forge Conformance Harness

Cross-suite conformance test harness for any Thermocline forge. Runs the
**Seamount 13-item conformance checklist** against a live forge URL and emits
a structured pass/fail report any CI system can consume.

The 13 items:
- **8 numbered conformance items** from `seamount/README.md` §"Forge Conformance Requirements"
  (envelope handling, sig verification, privacy fence, statelessness,
  task execution, job execution, receipt signatures, error codes)
- **5 attack-surface items** from §"Attack Surfaces and Mitigations"
  (AT-E1 malicious payload, AT-E2 DoS, AT-E3 tool escape, AT-E4 impersonation,
  AT-E5 timing side-channel)

## Install

```bash
pip install -e /Users/dom/Projects/dom/seamount/conformance
```

Dependencies are pulled from `pyproject.toml`: `thermocline>=0.3.1`,
`httpx>=0.27`, `jsonschema>=4.26`, `pyyaml>=6.0`.

## Run

```bash
# Start the forge first (separate terminal)
python -m pi_forge serve --port 5100
# In another terminal — run the conformance harness
python -m forge_conformance --target http://127.0.0.1:5100 --role pi-forge

# Or output JSON for CI consumption
python -m forge_conformance --target http://127.0.0.1:5200 --role describe-forge --output json
```

## Exit codes

- `0` — all checklist items report `pass` or `skip`; nothing failed.
- `1` — at least one item reports `fail`.
- `2` — bootstrap error (could not reach `/pubkey` on the target URL).

## Report structure

```jsonc
{
  "target_url": "http://127.0.0.1:5100",
  "role": "pi-forge",
  "started_at": "2026-05-11T00:00:00Z",
  "completed_at": "2026-05-11T00:00:02Z",
  "checklist": [
    {
      "id": "1-envelope-handling",
      "description": "Envelope schema validation and version rejection",
      "status": "pass",
      "message": "task-pi-100-digits.json accepted + schema valid"
    },
    // ... 12 more entries
  ],
  "total_pass": 5,
  "total_fail": 0,
  "total_skip": 8
}
```

v0.1 marks AT-E1..AT-E5 as `skip` with deferred-reason text; full negative-
test enforcement is a v0.2 hardening item. AT-E5 specifically is marked
`skip` with the reason
`"timing side-channel evaluation deferred to v0.2 hardening (CONF-02 surface)"`.

## What gets exercised

The harness consumes fixtures from
`/Users/dom/Projects/dom/thermocline/thermocline/conformance/{valid,invalid}/`.
Override the location with `--conformance-root` for cross-repo testing.

Response schemas come from
`/Users/dom/Projects/dom/thermocline/thermocline/schema/*.schema.json`.
Override with `--schema-root`.

## Run the harness's own test suite

```bash
cd /Users/dom/Projects/dom/seamount/conformance
python -m pytest tests/ -xvs
```

Includes:
- `test_checklist_mapping.py` — 13-item invariant + report shape.
- `test_harness.py` — live subprocess pi-forge + describe-forge + forged-sig forge.

## CI integration

The CI matrix step (see `photophore/.github/workflows/ci.yml` and
`seamount/.github/workflows/ci.yml`) runs:

```bash
python -m pi_forge serve --port 5100 &
sleep 3
python -m forge_conformance --target http://127.0.0.1:5100 --role pi-forge --output json
```

with `forge: [pi-forge, describe-forge]` as the matrix axis.
