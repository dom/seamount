"""pi-forge identity adapter — BrineProvider bound to seamount.piforge keystore namespace.

Forge keypairs live under a per-forge keystore service namespace. For
pi-forge that namespace is ``seamount.piforge`` (override via
``PIFORGE_KEYRING_SERVICE`` env var; tests use a per-test ephemeral namespace).
The forge identity string is ``pi-forge`` by default (override via
``PIFORGE_IDENTITY`` env var).
"""
from __future__ import annotations

import os

from thermocline.identity import BrineProvider, Verifier


def _resolve_service() -> str:
    return os.environ.get("PIFORGE_KEYRING_SERVICE", "seamount.piforge")


def _resolve_identity() -> str:
    return os.environ.get("PIFORGE_IDENTITY", "pi-forge")


FORGE_KEYRING_SERVICE = _resolve_service()
FORGE_IDENTITY = _resolve_identity()


def get_provider(keyring_service: str | None = None) -> BrineProvider:
    """Return a BrineProvider bound to the configured keystore namespace.

    Re-reads the env var on each call so tests can swap namespaces between
    requests; falls back to the module-level constant (cached at import time)
    when the env var is not set.
    """
    service = keyring_service or os.environ.get(
        "PIFORGE_KEYRING_SERVICE", FORGE_KEYRING_SERVICE
    )
    return BrineProvider(keyring_service=service)


def get_verifier(keyring_service: str | None = None) -> Verifier:
    """Return a Verifier with the local BrineProvider registered."""
    v = Verifier()
    v.register(get_provider(keyring_service))
    return v
