"""at_negative fixtures: reuse the live forge spawner from tests/conftest.py.

The AT-E* surface tests were file-existence checks in v0.1; they now run
against a real forge subprocess, so they share the ``conformance_forge``
fixture (and the real-keyring guard) with the harness tests.
"""
from __future__ import annotations

from tests.conftest import (  # noqa: F401
    ConformanceForgeHandle,
    _force_real_keyring_backend,
    conformance_forge,
)
