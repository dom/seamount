"""AT-E2: Resource exhaustion — forges MUST reject oversized payloads.

Failure mode: a hostile sovereign posts a multi-megabyte envelope (or
digits=10_000_000) to exhaust CPU/memory.

Live behavioral coverage (v0.4.0): forges enforce FORGE_MAX_CONTENT_LENGTH
(default 1 MiB) and return a structured 413; the previous xfail placeholder
is retired.
"""
# AT-SURFACE: AT-E2
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
    / "AT-E2-resource-exhaustion.json"
)


@pytest.mark.at_surface("AT-E2")
def test_at_e2_fixture_present() -> None:
    """AT-E2 fixture exists and is well-formed."""
    assert _FIXTURE.is_file(), f"AT-E2: fixture missing at {_FIXTURE}"
    data = json.loads(_FIXTURE.read_text())
    assert data.get("_at_surface") == "AT-E2"


@pytest.mark.at_surface("AT-E2")
@pytest.mark.integration
@pytest.mark.parametrize("conformance_forge", ["pi-forge"], indirect=True)
def test_oversized_payload_rejected_live(conformance_forge) -> None:
    """LIVE: a 2 MiB envelope is refused with a structured 413 before
    any computation happens."""
    url = f"{conformance_forge.url}/task"
    oversized = {
        "thermocline": "0.3.1",
        "type": "task",
        "envelope_id": "0e0e0e0e-0000-4000-8000-0000000000e2",
        "issued_at": "2026-07-07T00:00:00Z",
        "issuer": "at-e2",
        "task": {
            "type": "data.compute",
            "instruction": "x" * (2 * 1024 * 1024),
            "parameters": {"digits": 10},
        },
        "context": [],
    }
    r = httpx.post(url, json=oversized, timeout=30.0)
    assert r.status_code == 413
    body = r.json()
    assert body["type"] == "task_error"
    assert body["error"]["code"] == "MALFORMED_ENVELOPE"


@pytest.mark.at_surface("AT-E2")
@pytest.mark.integration
@pytest.mark.parametrize("conformance_forge", ["pi-forge"], indirect=True)
def test_huge_digits_parameter_rejected_live(conformance_forge) -> None:
    """LIVE: digits=10_000_000 never reaches computation."""
    url = f"{conformance_forge.url}/task"
    envelope = {
        "thermocline": "0.3.1",
        "type": "task",
        "envelope_id": "0e0e0e0e-0000-4000-8000-0000000001e2",
        "issued_at": "2026-07-07T00:00:00Z",
        "issuer": "at-e2",
        "task": {
            "type": "data.compute",
            "instruction": "compute pi",
            "parameters": {"digits": 10_000_000},
        },
        "context": [],
    }
    r = httpx.post(url, json=envelope, timeout=10.0)
    # Signature enforcement (401) fires before parameter validation on a
    # default-configured forge; either refusal prevents the computation.
    assert r.status_code in (401, 422)
    assert r.json()["error"]["code"] in ("SIGNATURE_INVALID", "INVALID_PARAMETERS")
