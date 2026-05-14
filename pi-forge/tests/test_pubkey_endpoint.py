"""Tests for the GET /pubkey endpoint."""
from __future__ import annotations

import json
import uuid

import keyring
import pytest

from thermocline.identity import BrineProvider


@pytest.fixture()
def initialized_forge(monkeypatch):
    """Yield (service, identity, app) with a fresh keypair generated."""
    service = f"seamount.piforge.test-{uuid.uuid4()}"
    identity = "pi-forge"
    monkeypatch.setenv("PIFORGE_KEYRING_SERVICE", service)
    monkeypatch.setenv("PIFORGE_IDENTITY", identity)
    provider = BrineProvider(keyring_service=service)
    provider.generate(identity=identity)
    # Re-import server with the new env vars applied.
    import importlib
    import sys
    for mod in ("forge_identity", "server"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    import server  # noqa: E402
    yield service, identity, server.app
    try:
        keyring.delete_password(service, identity)
    except Exception:
        pass


def test_pubkey_endpoint_shape(initialized_forge):
    """200 + {identity, key_scheme: 'brine', pubkey: <64-char hex>}."""
    service, identity, app = initialized_forge
    tc = app.test_client()
    r = tc.get("/pubkey")
    assert r.status_code == 200
    body = r.get_json()
    assert body["identity"] == identity
    assert body["key_scheme"] == "brine"
    assert isinstance(body["pubkey"], str)
    assert len(body["pubkey"]) == 64  # 32 bytes * 2 hex chars
    int(body["pubkey"], 16)  # raises if not hex


def test_pubkey_endpoint_unauthenticated(initialized_forge):
    """GET succeeds without any auth header (intentional bootstrap surface)."""
    _, _, app = initialized_forge
    tc = app.test_client()
    r = tc.get("/pubkey")
    assert r.status_code == 200


def test_pubkey_endpoint_no_private_key_leak(initialized_forge):
    """Response body MUST NOT contain 'private', 'secret', or any value >64 hex chars."""
    _, _, app = initialized_forge
    tc = app.test_client()
    r = tc.get("/pubkey")
    body_str = r.get_data(as_text=True)
    lower = body_str.lower()
    assert "private" not in lower
    assert "secret" not in lower
    # pubkey field is 64 hex chars; verify no longer hex strings sneak in
    # (an ed25519 *seed* would be 64 hex chars also — 32 bytes — so the
    # bound check is "no hex string longer than 64 chars"). The signing
    # key seed and verify key are both 32 bytes; the SIGNATURE is 64 bytes
    # (128 hex). If a signature ever appeared here it would be a leak.
    body_obj = r.get_json()
    for k, v in body_obj.items():
        if isinstance(v, str) and len(v) > 64:
            # All hex? Then it's a key-material-shaped value.
            try:
                int(v, 16)
                pytest.fail(f"suspicious long hex value in pubkey response: {k}={v[:16]}...")
            except ValueError:
                pass


def test_pubkey_endpoint_503_when_not_initialized(monkeypatch):
    """If no keypair has been generated, /pubkey returns 503 FORGE_NOT_INITIALIZED."""
    service = f"seamount.piforge.test-{uuid.uuid4()}"
    monkeypatch.setenv("PIFORGE_KEYRING_SERVICE", service)
    monkeypatch.setenv("PIFORGE_IDENTITY", "pi-forge")
    import importlib
    import sys
    for mod in ("forge_identity", "server"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    import server  # noqa: E402

    tc = server.app.test_client()
    r = tc.get("/pubkey")
    assert r.status_code == 503
    body = r.get_json()
    assert body["error"] == "FORGE_NOT_INITIALIZED"
