"""Shared fixtures for pi-forge tests.

Each test gets a per-test ephemeral keystore namespace (``seamount.piforge.test-<uuid>``)
so parallel tests cannot collide with each other or with the production
``seamount.piforge`` namespace. Teardown deletes every key created.
"""
from __future__ import annotations

import os
import uuid

import keyring
import pytest


@pytest.fixture()
def ephemeral_keyring_service(monkeypatch):
    """Yield a unique keystore namespace; tear down all entries on exit."""
    service = f"seamount.piforge.test-{uuid.uuid4()}"
    monkeypatch.setenv("PIFORGE_KEYRING_SERVICE", service)
    # Force the module-level constant to re-read by reloading forge_identity
    # if it has already been imported.
    import importlib
    import sys
    for mod_name in ("forge_identity",):
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])
    created: list[str] = []
    yield service, created
    # Teardown: delete every key that any test recorded.
    for key in created:
        try:
            keyring.delete_password(service, key)
        except Exception:
            pass


@pytest.fixture()
def fresh_identity(ephemeral_keyring_service):
    """Generate a fresh ed25519 keypair for ``pi-forge`` under the ephemeral ns.

    Returns a ``(service, identity, provider)`` triple. The identity is
    registered in two ways: once as a seed (so the provider can sign as
    ``pi-forge``) and the corresponding verify key is registered under the
    same service as a pubkey (so the verifier can verify foreign sigs in the
    same namespace). This matches the deployment model where a forge knows
    its own seed AND the sovereign's verify key.
    """
    service, created = ephemeral_keyring_service
    from thermocline.identity import BrineProvider

    provider = BrineProvider(keyring_service=service)
    identity = "pi-forge"
    provider.generate(identity=identity)
    created.append(identity)
    return service, identity, provider
