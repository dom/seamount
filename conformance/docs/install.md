# Seamount Conformance Harness Install Guide

The conformance harness validates any forge against the Seamount spec checklist
(12 universal forge MUST/SHOULD requirements). It runs against the reference
forges (`pi-forge`, `describe-forge`) in CI and may be run against third-party
implementations on demand.

## 1. Prerequisites

- **Python**: 3.11+.
- **A running forge** to test against (URL + key_scheme known).

## 2. Install

```bash
cd ~/Projects/dom/seamount/conformance
pip install -e .[dev]
```

## 3. Run against a forge

```bash
python -m forge_conformance --target http://localhost:5117 --role pi-forge
python -m forge_conformance --target http://localhost:5118 --role describe-forge
```

Exits 0 on full pass; non-zero with a per-check pass/fail/skip table on any
failure. Use `--json` for machine-readable output suitable for CI summaries.

## 4. AT-* negative tests

The harness also runs the Seamount AT-E1..AT-E5 attack-surface negative tests
under `at_negative/`. These validate that the target forge rejects malicious
payloads, oversized inputs, tool-escape attempts, forged receipts, and
timing-side-channel probes:

```bash
pytest at_negative/ -v
```

In v0.1, `test_at_e2_resource_exhaustion` is marked `xfail` (size-limit
enforcement deferred to v0.2).

## 5. Known Limitations (v0.1)

- **AT-E2 size-limit enforcement** deferred to v0.2. The reference forges
  accept arbitrarily large requests; the harness marks the test xfail.
- **Third-party forge certification** is not yet a thing; running the
  harness against a non-reference forge produces a pass/fail report, but no
  formal certification badge exists in v0.1.

## Next steps

- [pi-forge install](../../pi-forge/docs/install.md)
- [describe-forge install](../../describe-forge/docs/install.md)
- [Suite quickstart](../../../thermocline/docs/quickstart.md)
