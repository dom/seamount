# describe-forge Install Guide

`describe-forge` is a tier-1-aware Seamount forge: it accepts tier-1 shadow
envelopes and returns templated descriptions of the shadow content. Unlike
pi-forge, it operates on the abstraction (not the source content) — the
sovereign node's shadow generation is what makes the forge useful.

## 1. Prerequisites

- **Python**: 3.11+.
- **OS**: macOS 12+ (first-class) or Linux/Windows (best-effort).
- **Dependencies**: Flask 3.x, `thermocline-py`.

## 2. Install

```bash
cd ~/Projects/dom/seamount/describe-forge
pip install -e .[dev]
```

Or `uv`:

```bash
cd ~/Projects/dom/seamount/describe-forge
uv venv
uv pip install -e .[dev]
```

## 3. Initialize the signing identity

```bash
python -m describe_forge init --keyring-service seamount.describeforge
```

First invocation triggers a Keychain prompt on macOS — click **"Always Allow"**.

## 4. Serve

```bash
python -m describe_forge serve --keyring-service seamount.describeforge --port 5118
```

Wait for `DESCRIBEFORGE_READY port=5118`. The server exposes the same shape as
pi-forge (`GET /pubkey`, `POST /task`).

## 5. Tier-1 shadow contract

describe-forge MUST receive tier-1 shadow envelopes from the dispatching
sovereign node. The shadow's `abstraction` field is the input the forge
operates on; the original source content is never sent. The result envelope
describes the abstraction (not the source).

This is intentional: tier-1 abstractions are visible on the wire and may be
correlated by an adversary, but the underlying source content remains
tier-0/local on the sovereign node. The shadow is the privacy boundary.

## 6. Known Limitations (v0.1)

- **`mypy --strict` is deferred to v0.2** (17 type-annotation gaps; same
  shape as pi-forge). Re-enable in `pyproject.toml [tool.mypy]`.
- **Default Keychain entries** are software-backed (not Secure Enclave).
- **No payload size enforcement** at the forge layer (AT-E2 deferred).

## Next steps

- [pi-forge install](../../pi-forge/docs/install.md)
- [Conformance harness](../../conformance/docs/install.md)
- [Suite quickstart](../../../thermocline/docs/quickstart.md)
