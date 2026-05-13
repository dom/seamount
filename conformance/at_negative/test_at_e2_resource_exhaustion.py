"""AT-E2: Resource exhaustion — forges MUST reject oversized payloads.

Failure mode: a hostile sovereign sends digits=10_000_000 to pi-forge to
exhaust CPU/memory. v0.1 pi-forge has NO explicit size limit on the digits
parameter; documented as v0.2 known limitation.
"""
# AT-SURFACE: AT-E2
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
    / "AT-E2-resource-exhaustion.json"
)


@pytest.mark.at_surface("AT-E2")
def test_at_e2_fixture_present() -> None:
    """AT-E2 fixture exists and is well-formed."""
    assert _FIXTURE.is_file(), f"AT-E2: fixture missing at {_FIXTURE}"
    data = json.loads(_FIXTURE.read_text())
    assert data.get("_at_surface") == "AT-E2"


@pytest.mark.at_surface("AT-E2")
@pytest.mark.xfail(
    reason="AT-E2: v0.1 forges have no explicit size limit on digits "
    "parameter; documented as v0.2 known limitation in seamount CHANGELOG",
    strict=False,
)
def test_oversized_payload_rejected() -> None:
    """AT-E2: a digits=10_000_000 envelope should be rejected before computation.

    Marked xfail per CONTEXT D-11 ship-discipline: v0.1 forges do not enforce
    upper bounds; v0.2 will add a configurable size limit. This test fails
    cleanly when invoked, surfacing the gap.
    """
    pytest.fail(
        "AT-E2: pi-forge does not enforce digits upper bound in v0.1; "
        "documented as v0.2 known limitation"
    )
