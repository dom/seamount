"""GET /pubkey shape and FORGE_NOT_INITIALIZED error path."""
from __future__ import annotations


def test_pubkey_returns_expected_shape(initialized_forge):
    _, identity, server = initialized_forge
    tc = server.app.test_client()
    r = tc.get("/pubkey")
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["identity"] == identity
    assert body["key_scheme"] == "brine"
    assert isinstance(body["pubkey"], str)
    assert len(body["pubkey"]) == 64  # 32-byte ed25519 verify key as hex


def test_pubkey_returns_503_when_keypair_missing(monkeypatch):
    """Forge with no keypair in the configured namespace returns 503."""
    import uuid as _uuid

    service = f"seamount.llmforge.no-key-{_uuid.uuid4()}"
    monkeypatch.setenv("LLMFORGE_KEYRING_SERVICE", service)
    monkeypatch.setenv("LLMFORGE_IDENTITY", "llm-forge")

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


def test_health_returns_status_ok(initialized_forge):
    _, _, server = initialized_forge
    tc = server.app.test_client()
    r = tc.get("/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["forge"] == "llm-forge"
    assert body["key_scheme"] == "brine"
    assert "thermocline_version" in body
