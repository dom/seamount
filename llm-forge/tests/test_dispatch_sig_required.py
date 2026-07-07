"""HIGH-severity regression tests: dispatch_signature verification is mandatory.

Mirrors pi-forge/tests/test_dispatch_sig_required.py for the inference relay:
missing signature, key_scheme=none downgrade, and tampered signatures are all
rejected with SIGNATURE_INVALID when the forge is configured for brine (the
default); a valid SP-3.3 brine signature is accepted.
"""
from __future__ import annotations

import importlib
import sys
import uuid

import keyring
import pytest

from thermocline.identity import BrineProvider

from _helpers import MockLLMProvider, example_inference_envelope


@pytest.fixture()
def brine_forge(monkeypatch):
    """Forge module with default config (brine + dispatch sig required)."""
    service = f"seamount.llmforge.test-{uuid.uuid4()}"
    identity = "llm-forge-local"
    monkeypatch.setenv("LLMFORGE_KEYRING_SERVICE", service)
    monkeypatch.setenv("LLMFORGE_IDENTITY", identity)
    monkeypatch.setenv("FORGE_NODE_ID", identity)
    monkeypatch.delenv("FORGE_KEY_SCHEME", raising=False)
    monkeypatch.delenv("FORGE_REQUIRE_DISPATCH_SIG", raising=False)
    provider = BrineProvider(keyring_service=service)
    provider.generate(identity=identity)
    for mod in ("forge_identity", "server"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    import server  # noqa: E402
    yield service, server
    try:
        keyring.delete_password(service, identity)
    except Exception:
        pass


def _sovereign(forge_service: str) -> tuple[BrineProvider, str, str]:
    sov_service = f"sovereign-{uuid.uuid4()}"
    sov = BrineProvider(keyring_service=sov_service)
    sov.generate(identity="alice-node")
    pub = sov.public_key(identity="alice-node")
    BrineProvider(keyring_service=forge_service).register_public_key(
        identity="alice-node", verify_key=pub
    )
    return sov, sov_service, "alice-node"


def _signed_envelope(sov: BrineProvider, identity: str) -> dict:
    body = example_inference_envelope()
    body["dispatch_signature"] = {
        "key_scheme": "brine",
        "node_id": identity,
        "policy_hash": None,
        "shadows_generated": [],
        "timestamp": "2026-07-07T00:00:00Z",
        "sig": "",
    }
    sig = sov.sign(envelope=body, signer_identity=identity)
    body["dispatch_signature"]["sig"] = sig.bytes_.hex()
    return body


def test_missing_dispatch_signature_rejected(brine_forge):
    _, server = brine_forge
    body = example_inference_envelope()
    del body["dispatch_signature"]
    r = server.app.test_client().post(
        "/task", json=body, headers={"authorization": "Bearer fake-key"}
    )
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "SIGNATURE_INVALID"


def test_key_scheme_none_downgrade_rejected(brine_forge):
    _, server = brine_forge
    body = example_inference_envelope()  # ships a key_scheme=none block
    r = server.app.test_client().post(
        "/task", json=body, headers={"authorization": "Bearer fake-key"}
    )
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "SIGNATURE_INVALID"


def test_valid_brine_signature_accepted(brine_forge):
    service, server = brine_forge
    sov, sov_service, identity = _sovereign(service)
    server.set_provider(MockLLMProvider(response_text="ok"))
    try:
        body = _signed_envelope(sov, identity)
        r = server.app.test_client().post(
            "/task", json=body, headers={"authorization": "Bearer fake-key"}
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["outputs"]["response"] == "ok"
    finally:
        server.set_provider(None)
        try:
            keyring.delete_password(sov_service, identity)
        except Exception:
            pass


def test_tampered_brine_signature_rejected(brine_forge):
    service, server = brine_forge
    sov, sov_service, identity = _sovereign(service)
    try:
        body = _signed_envelope(sov, identity)
        sig = bytearray(bytes.fromhex(body["dispatch_signature"]["sig"]))
        sig[0] ^= 0xFF
        body["dispatch_signature"]["sig"] = bytes(sig).hex()
        r = server.app.test_client().post(
            "/task", json=body, headers={"authorization": "Bearer fake-key"}
        )
        assert r.status_code == 401
        assert r.get_json()["error"]["code"] == "SIGNATURE_INVALID"
    finally:
        try:
            keyring.delete_password(sov_service, identity)
        except Exception:
            pass


def test_dev_optout_env_flag_allows_unsigned(brine_forge, monkeypatch):
    _, server = brine_forge
    monkeypatch.setenv("FORGE_REQUIRE_DISPATCH_SIG", "0")
    importlib.reload(sys.modules["server"])
    import server as server_devmode  # noqa: E402
    server_devmode.set_provider(MockLLMProvider(response_text="ok"))
    try:
        r = server_devmode.app.test_client().post(
            "/task",
            json=example_inference_envelope(),
            headers={"authorization": "Bearer fake-key"},
        )
        assert r.status_code == 200
    finally:
        server_devmode.set_provider(None)


def test_health_reports_require_dispatch_sig(brine_forge):
    _, server = brine_forge
    r = server.app.test_client().get("/health")
    assert r.get_json()["require_dispatch_sig"] is True
