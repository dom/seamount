"""AT-E1: Malicious envelope payloads — strict validation, structured rejection.

Failure mode: a hostile sovereign sends a malformed envelope to the forge;
the forge MUST reject with a structured error response and never crash.

Live behavioral coverage (v0.4.0): posts hostile payloads at a real
pi-forge subprocess and asserts structured MALFORMED_ENVELOPE rejections
with no unstructured 5xx.
"""
# AT-SURFACE: AT-E1
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
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
@pytest.mark.integration
@pytest.mark.parametrize("conformance_forge", ["pi-forge"], indirect=True)
def test_malformed_payloads_rejected_live(conformance_forge) -> None:
    """LIVE: garbage object, non-object JSON, and non-JSON bodies all get
    structured 4xx errors from a real forge; nothing 5xxs."""
    url = f"{conformance_forge.url}/task"

    # (a) JSON object with none of the required fields.
    r = httpx.post(url, json={"garbage": "input"}, timeout=10.0)
    assert 400 <= r.status_code < 500
    assert r.json()["error"]["code"] == "MALFORMED_ENVELOPE"

    # (b) Non-object JSON body (array) — the pre-fix 500 path.
    r = httpx.post(url, json=[1, 2, 3], timeout=10.0)
    assert 400 <= r.status_code < 500
    assert r.json()["error"]["code"] == "MALFORMED_ENVELOPE"

    # (c) Non-JSON content type.
    r = httpx.post(
        url,
        content=b"\x00\x01\x02",
        headers={"content-type": "text/plain"},
        timeout=10.0,
    )
    assert 400 <= r.status_code < 500
    assert r.json()["error"]["code"] == "MALFORMED_ENVELOPE"
