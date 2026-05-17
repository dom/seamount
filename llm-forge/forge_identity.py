"""llm-forge identity adapter — BrineProvider bound to seamount.llmforge keystore namespace.

Mirrors seamount/pi-forge/forge_identity.py. Each forge gets its own keystore
namespace so co-tenanted forges on the same host cannot accidentally sign as
each other. Default namespace is ``seamount.llmforge``; override with the
``LLMFORGE_KEYRING_SERVICE`` env var. Identity defaults to ``llm-forge``;
override with ``LLMFORGE_IDENTITY``.
"""
from __future__ import annotations

import os

from thermocline.identity import BrineProvider, Verifier


def _resolve_service() -> str:
    return os.environ.get("LLMFORGE_KEYRING_SERVICE", "seamount.llmforge")


def _resolve_identity() -> str:
    return os.environ.get("LLMFORGE_IDENTITY", "llm-forge")


FORGE_KEYRING_SERVICE = _resolve_service()
FORGE_IDENTITY = _resolve_identity()


def get_provider(keyring_service: str | None = None) -> BrineProvider:
    """Return a BrineProvider bound to the configured keystore namespace.

    Re-reads the env var on each call so tests can swap namespaces between
    requests; falls back to the module-level constant (cached at import time)
    when the env var is not set.
    """
    service = keyring_service or os.environ.get(
        "LLMFORGE_KEYRING_SERVICE", FORGE_KEYRING_SERVICE
    )
    return BrineProvider(keyring_service=service)


def get_verifier(keyring_service: str | None = None) -> Verifier:
    """Return a Verifier with the local BrineProvider registered."""
    v = Verifier()
    v.register(get_provider(keyring_service))
    return v
