"""describe-forge identity adapter — BrineProvider bound to seamount.describeforge.

Forges hold their keypairs under per-forge keystore namespaces. For
describe-forge that namespace is ``seamount.describeforge`` (override via
``DESCRIBEFORGE_KEYRING_SERVICE``). The forge identity string is
``describe-forge`` by default (override via ``DESCRIBEFORGE_IDENTITY``).

Namespace distinctness from pi-forge (``seamount.piforge``) is the T-03-13
mitigation: a single sovereign that trusts both forges keeps two independent
pubkey entries; a forge cannot impersonate another by collision.
"""
from __future__ import annotations

import os

from thermocline.identity import BrineProvider, Verifier


FORGE_KEYRING_SERVICE = os.environ.get(
    "DESCRIBEFORGE_KEYRING_SERVICE", "seamount.describeforge"
)
FORGE_IDENTITY = os.environ.get("DESCRIBEFORGE_IDENTITY", "describe-forge")


def get_provider(keyring_service: str | None = None) -> BrineProvider:
    service = keyring_service or os.environ.get(
        "DESCRIBEFORGE_KEYRING_SERVICE", FORGE_KEYRING_SERVICE
    )
    return BrineProvider(keyring_service=service)


def get_verifier(keyring_service: str | None = None) -> Verifier:
    v = Verifier()
    v.register(get_provider(keyring_service))
    return v
