"""Shared fixtures for describe-forge tests."""
from __future__ import annotations

import importlib
import sys
import uuid

import keyring
import pytest

from thermocline.identity import BrineProvider


@pytest.fixture()
def initialized_forge(monkeypatch):
    """Yield (service, identity, app) with a fresh keypair generated.

    Uses an ephemeral keystore namespace per test (parallel-safe).
    """
    service = f"seamount.describeforge.test-{uuid.uuid4()}"
    identity = "describe-forge-local"  # match server.FORGE_NODE_ID default
    monkeypatch.setenv("DESCRIBEFORGE_KEYRING_SERVICE", service)
    monkeypatch.setenv("DESCRIBEFORGE_IDENTITY", identity)
    monkeypatch.setenv("FORGE_NODE_ID", identity)
    # These tests exercise describe/receipt behavior with unsigned dev
    # envelopes; dispatch-signature enforcement has its own dedicated suite
    # (test_dispatch_sig_required.py).
    monkeypatch.setenv("FORGE_REQUIRE_DISPATCH_SIG", "0")
    provider = BrineProvider(keyring_service=service)
    provider.generate(identity=identity)
    for mod in ("forge_identity", "server"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    import server  # noqa: E402
    yield service, identity, server.app
    try:
        keyring.delete_password(service, identity)
    except Exception:
        pass


def make_task_envelope(*, context: list, envelope_id: str = "task-d1") -> dict:
    """Helper: build a minimal valid task envelope with given context blocks."""
    return {
        "thermocline": "0.3.1",
        "type": "task",
        "envelope_id": envelope_id,
        "issued_at": "2026-05-11T01:00:00Z",
        "issuer": "test-sovereign",
        "task": {
            "type": "shadow.describe",
            "instruction": "describe shadows",
            "parameters": {},
        },
        "context": context,
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
