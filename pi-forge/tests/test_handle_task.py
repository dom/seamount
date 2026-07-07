"""Tests for the POST /task handler via Flask test_client.

Behaviors 4-6 from Task 2 plan:
    4. default key_scheme is brine
    5. FORGE_KEY_SCHEME=none -> dev mode
    6. brine sig is real (128-char hex)
"""
from __future__ import annotations

import json
import uuid

import keyring
import pytest

from thermocline.identity import BrineProvider


@pytest.fixture()
def initialized_forge(monkeypatch):
    """Yield (service, identity, app) with a fresh keypair generated.

    Restores module state between tests via importlib.reload.
    """
    service = f"seamount.piforge.test-{uuid.uuid4()}"
    identity = "pi-forge-local"  # responder identity = node_id; matches default
    monkeypatch.setenv("PIFORGE_KEYRING_SERVICE", service)
    monkeypatch.setenv("PIFORGE_IDENTITY", identity)
    # FORGE_NODE_ID also needs to match the signer identity for self-signed
    # receipts in tests (server uses FORGE_NODE_ID as the responder).
    monkeypatch.setenv("FORGE_NODE_ID", identity)
    # These tests exercise the receipt-signing side with unsigned dev
    # envelopes; dispatch-signature enforcement has its own dedicated suite
    # (test_dispatch_sig_required.py).
    monkeypatch.setenv("FORGE_REQUIRE_DISPATCH_SIG", "0")
    provider = BrineProvider(keyring_service=service)
    provider.generate(identity=identity)
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


def _example_task_envelope() -> dict:
    """Minimal valid envelope using key_scheme=none in the dispatch sig."""
    return {
        "thermocline": "0.3.1",
        "type": "task",
        "envelope_id": "task-handle-001",
        "issued_at": "2026-05-11T01:00:00Z",
        "issuer": "test-sovereign",
        "task": {
            "type": "data.compute",
            "instruction": "compute pi",
            "parameters": {"digits": 10},
        },
        "context": [],
        "result_policy": {"persist_to_shared": [], "return_only": [], "strip_before_persist": []},
        "dispatch_signature": {
            "key_scheme": "none",
            "node_id": "test-sovereign",
            "policy_hash": None,
            "shadows_generated": [],
            "timestamp": "2026-05-11T01:00:00Z",
            "sig": None,
        },
    }


def test_handle_task_default_key_scheme_brine(initialized_forge):
    """No FORGE_KEY_SCHEME override -> server uses brine and produces a real sig."""
    service, identity, app = initialized_forge
    tc = app.test_client()
    r = tc.post("/task", json=_example_task_envelope())
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["receipt_signature"]["key_scheme"] == "brine"


def test_handle_task_dev_mode_none(initialized_forge, monkeypatch):
    """FORGE_KEY_SCHEME=none -> receipt_signature.sig is null (dev mode preserved)."""
    service, identity, app = initialized_forge
    monkeypatch.setenv("FORGE_KEY_SCHEME", "none")
    import importlib
    import sys
    importlib.reload(sys.modules["server"])
    import server  # noqa: E402
    tc = server.app.test_client()
    r = tc.post("/task", json=_example_task_envelope())
    assert r.status_code == 200
    body = r.get_json()
    assert body["receipt_signature"]["key_scheme"] == "none"
    assert body["receipt_signature"]["sig"] is None


def test_handle_task_brine_sig_is_real(initialized_forge):
    """receipt_signature.sig must be 128-char hex (64-byte ed25519 sig)."""
    service, identity, app = initialized_forge
    tc = app.test_client()
    r = tc.post("/task", json=_example_task_envelope())
    assert r.status_code == 200
    body = r.get_json()
    sig_hex = body["receipt_signature"]["sig"]
    assert isinstance(sig_hex, str)
    assert len(sig_hex) == 128  # 64 bytes * 2 hex chars
    int(sig_hex, 16)  # must be valid hex


def test_non_object_json_body_returns_structured_error(initialized_forge):
    """MEDIUM review fix: a JSON array body must yield MALFORMED_ENVELOPE, not 500."""
    service, identity, app = initialized_forge
    tc = app.test_client()
    r = tc.post("/task", json=[1, 2, 3])
    assert r.status_code == 400
    body = r.get_json()
    assert body["type"] == "task_error"
    assert body["envelope_id"] is None
    assert body["error"]["code"] == "MALFORMED_ENVELOPE"


def test_bind_host_defaults_to_loopback(monkeypatch):
    """LOW review fix: never bind 0.0.0.0 unless explicitly opted in."""
    import importlib
    import sys
    monkeypatch.delenv("FORGE_BIND_HOST", raising=False)
    if "server" in sys.modules:
        importlib.reload(sys.modules["server"])
    import server
    assert server.resolve_bind_host() == "127.0.0.1"
    monkeypatch.setenv("FORGE_BIND_HOST", "0.0.0.0")
    assert server.resolve_bind_host() == "0.0.0.0"


def test_oversized_request_rejected_structured(initialized_forge, monkeypatch):
    """LOW review fix: bodies over FORGE_MAX_CONTENT_LENGTH get a structured 413."""
    import importlib
    import sys
    monkeypatch.setenv("FORGE_MAX_CONTENT_LENGTH", "1024")
    importlib.reload(sys.modules["server"])
    import server
    tc = server.app.test_client()
    big = _example_task_envelope()
    big["task"]["instruction"] = "x" * 4096
    r = tc.post("/task", json=big)
    assert r.status_code == 413
    body = r.get_json()
    assert body["type"] == "task_error"
    assert body["error"]["code"] == "MALFORMED_ENVELOPE"


def test_error_envelope_caps_reflected_version(initialized_forge):
    """LOW review fix: attacker-supplied version strings are clipped in errors."""
    service, identity, app = initialized_forge
    tc = app.test_client()
    env = _example_task_envelope()
    env["thermocline"] = "v" * 5000
    r = tc.post("/task", json=env)
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"]["code"] == "UNSUPPORTED_VERSION"
    assert "v" * 100 not in body["error"]["message"]
    assert len(body["error"]["message"]) < 300


def test_error_envelope_caps_reflected_task_type(initialized_forge):
    service, identity, app = initialized_forge
    tc = app.test_client()
    env = _example_task_envelope()
    env["task"]["type"] = "t" * 5000
    r = tc.post("/task", json=env)
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"]["code"] == "UNSUPPORTED_TASK_TYPE"
    assert "t" * 100 not in body["error"]["message"]
    assert len(body["error"]["message"]) < 300
