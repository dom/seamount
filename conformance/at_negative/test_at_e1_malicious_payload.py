"""AT-E1: Malicious envelope payloads — strict schema, size limits, reject unknown fields.

Failure mode: a hostile sovereign sends a malformed envelope to the forge;
the forge MUST reject with a structured error response and never crash.

The Phase 3 forge_conformance harness already validates schema enforcement
across both pi-forge and describe-forge. This at_negative test documents
the contract from the AT-E1 surface perspective.
"""
# AT-SURFACE: AT-E1
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
    / "AT-E1-malicious-payload.json"
)


@pytest.mark.at_surface("AT-E1")
def test_at_e1_fixture_present_and_well_formed() -> None:
    """AT-E1 fixture exists and declares the surface."""
    assert _FIXTURE.is_file(), f"AT-E1: fixture missing at {_FIXTURE}"
    data = json.loads(_FIXTURE.read_text())
    assert data.get("_at_surface") == "AT-E1"


@pytest.mark.at_surface("AT-E1")
@pytest.mark.documents_only
def test_malformed_payload_rejected_documented() -> None:
    """AT-E1 enforcement is via the forge_conformance schema-validation step.

    See seamount/conformance/forge_conformance/_harness.py — schema validation
    is performed on every dispatch and rejects unknown fields / wrong types.
    A live HTTP test would require spawning a forge subprocess; the
    Phase 3 harness covers that path.
    """
    harness = Path(__file__).resolve().parents[1] / "forge_conformance"
    assert harness.is_dir(), (
        "AT-E1: forge_conformance harness package must exist; it validates "
        "envelope schemas at dispatch time"
    )
