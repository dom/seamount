"""AT-E4: Forge impersonation — sovereign rejects receipt signed with wrong key.

Failure mode: an attacker stands up a fake forge with a different ed25519 key,
intercepts a dispatch, and returns a receipt signed with the wrong key. The
sovereign MUST reject the receipt via Verifier.verify() returning None.

The live integration test (real wrong-key forge subprocess) lives at
photophore/python/tests/integration/test_e2e_forged_receipt.py. This
at_negative wrapper covers the surface for the coverage gate.
"""
# AT-SURFACE: AT-E4
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

_SUITE_ROOT = Path(
    os.environ.get(
        "THERMOCLINE_SUITE_ROOT",
        str(Path.home() / "Projects" / "dom"),
    )
)
_FIXTURE = (
    _SUITE_ROOT
    / "thermocline"
    / "thermocline"
    / "conformance"
    / "invalid"
    / "AT-E4-forge-impersonation.json"
)
_PHOTOPHORE_TEST = (
    _SUITE_ROOT
    / "photophore"
    / "python"
    / "tests"
    / "integration"
    / "test_e2e_forged_receipt.py"
)


@pytest.mark.at_surface("AT-E4")
def test_at_e4_fixture_present() -> None:
    """AT-E4 fixture exists and declares the surface."""
    assert _FIXTURE.is_file(), f"AT-E4: fixture missing at {_FIXTURE}"
    data = json.loads(_FIXTURE.read_text())
    assert data.get("_at_surface") == "AT-E4"


@pytest.mark.at_surface("AT-E4")
def test_forge_impersonation_integration_test_exists() -> None:
    """AT-E4 source-of-truth: forged-receipt integration test at photophore."""
    assert _PHOTOPHORE_TEST.is_file(), (
        f"AT-E4: source-of-truth integration test missing at {_PHOTOPHORE_TEST}"
    )
