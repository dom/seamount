# pi-forge Install Guide

`pi-forge` is the simplest possible Seamount-compliant forge. It accepts
tier-2 task envelopes requesting π digit computation and returns signed
`task_result` envelopes.

## 1. Prerequisites

- **Python**: 3.11+.
- **OS**: macOS 12+ (first-class) or Linux/Windows (best-effort).
- **Dependencies**: Flask 3.x, mpmath 1.3+, `thermocline-py` (for envelope
  validation + canonicalization).

## 2. Install

```bash
cd ~/Projects/dom/seamount/pi-forge
pip install -e .[dev]
```

Or with `uv`:

```bash
cd ~/Projects/dom/seamount/pi-forge
uv venv
uv pip install -e .[dev]
```

## 3. Initialize the signing identity

pi-forge stores its ed25519 keypair under a dedicated `python-keyring` service
namespace. Initialize on a fresh install:

```bash
python -m pi_forge init --keyring-service seamount.piforge
```

This generates a new keypair, stores the private half in the keystore, and
prints the public key. The first invocation triggers a Keychain prompt on
macOS. Click **"Always Allow"** so the `serve` command doesn't re-prompt.

## 4. Serve

```bash
python -m pi_forge serve --keyring-service seamount.piforge --port 5117
```

Wait for the readiness marker:

```
PIFORGE_READY port=5117
```

This marker is contractual. Photophore's integration-test harness greps for
it. The server exposes:

- `GET /pubkey`, public key for TOFU acquisition.
- `POST /task`, accept and process a `task` envelope; return a signed
  `task_result`.

## 5. Verify

```bash
curl http://localhost:5117/pubkey
```

Expected: a JSON object with `public_key`, `key_scheme`, and `algo` fields.

## 6. Known Limitations (v0.1)

- **`mypy --strict` is deferred to v0.2.** pi-forge currently has 20
  type-annotation gaps (predominantly missing dict/list type-args in
  envelope.py helpers and missing return annotations on Flask route handlers).
  Re-enable by uncommenting `strict = true` in `pyproject.toml [tool.mypy]`.
- **Payload size limits (AT-E2)** are deferred to v0.2. pi-forge currently
  accepts arbitrary `digits` parameter values; production deployments should
  proxy through a size-limiting reverse proxy until size limits ship.
- **Default Keychain entries** are software-backed (not Secure Enclave).
  Hardware anchoring deferred to v0.2.

## Next steps

- [describe-forge install](../../describe-forge/docs/install.md)
- [Conformance harness](../../conformance/docs/install.md)
- [Suite quickstart](../../../thermocline/docs/quickstart.md)
