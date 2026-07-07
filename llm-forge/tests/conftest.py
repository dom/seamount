"""Shared fixtures for llm-forge tests.

Each test gets a per-test ephemeral keystore namespace
(``seamount.llmforge.test-<uuid>``) so parallel tests cannot collide with
each other or with the production ``seamount.llmforge`` namespace. Teardown
deletes every key created.

Non-fixture helpers (MockLLMProvider, example_inference_envelope) live in
tests/_helpers.py — pytest's conftest is plugin-loaded, not importable.
"""
from __future__ import annotations

import os
import sys
import uuid

import keyring
import pytest

# Flat-layout: ensure project root is importable so `import server`,
# `import envelope`, etc. resolve when tests run from anywhere.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
# tests/ on sys.path so `from _helpers import ...` resolves.
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


@pytest.fixture()
def ephemeral_keyring_service(monkeypatch):
    """Yield a unique keystore namespace; tear down all entries on exit."""
    service = f"seamount.llmforge.test-{uuid.uuid4()}"
    monkeypatch.setenv("LLMFORGE_KEYRING_SERVICE", service)
    import importlib
    for mod_name in ("forge_identity",):
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])
    created: list[str] = []
    yield service, created
    for key in created:
        try:
            keyring.delete_password(service, key)
        except Exception:
            pass


@pytest.fixture()
def initialized_forge(monkeypatch):
    """Yield (service, identity, app) with a fresh keypair generated.

    Mirrors pi-forge/tests/test_handle_task.py::initialized_forge so the
    test patterns transfer.
    """
    service = f"seamount.llmforge.test-{uuid.uuid4()}"
    identity = "llm-forge-local"
    monkeypatch.setenv("LLMFORGE_KEYRING_SERVICE", service)
    monkeypatch.setenv("LLMFORGE_IDENTITY", identity)
    monkeypatch.setenv("FORGE_NODE_ID", identity)
    # These tests exercise relay/receipt behavior with unsigned dev
    # envelopes; dispatch-signature enforcement has its own dedicated suite
    # (test_dispatch_sig_required.py).
    monkeypatch.setenv("FORGE_REQUIRE_DISPATCH_SIG", "0")
    from thermocline.identity import BrineProvider

    provider = BrineProvider(keyring_service=service)
    provider.generate(identity=identity)

    import importlib
    for mod in ("forge_identity", "server"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    import server  # noqa: E402

    yield service, identity, server

    try:
        keyring.delete_password(service, identity)
    except Exception:
        pass


