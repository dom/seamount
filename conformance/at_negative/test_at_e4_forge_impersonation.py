"""AT-E4: Forge impersonation — wrong-key signatures are rejected on both sides.

Failure modes:
  * an attacker submits a dispatch signed with an unregistered key, or a
    tampered signature, and the forge executes it;
  * a fake forge returns a receipt signed with the wrong key and the
    sovereign accepts it.

Live behavioral coverage (v0.4.0): the dispatch half runs here against a
real forge subprocess (garbage and unregistered-key signatures must be
refused with SIGNATURE_INVALID). The receipt half is exercised by
tests/test_harness.py::test_harness_detects_invalid_receipt_signature and
by photophore's forged-receipt integration test.
"""
# AT-SURFACE: AT-E4
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


def _task_envelope(sig_block: dict | None) -> dict:
    body = {
        "thermocline": "0.3.1",
        "type": "task",
        "envelope_id": "0e0e0e0e-0000-4000-8000-0000000000e4",
        "issued_at": "2026-07-07T00:00:00Z",
        "issuer": "at-e4",
        "task": {
            "type": "data.compute",
            "instruction": "compute pi",
            "parameters": {"digits": 10},
        },
        "context": [],
    }
    if sig_block is not None:
        body["dispatch_signature"] = sig_block
    return body


@pytest.mark.at_surface("AT-E4")
def test_at_e4_fixture_present() -> None:
    """AT-E4 fixture exists and declares the surface."""
    assert _FIXTURE.is_file(), f"AT-E4: fixture missing at {_FIXTURE}"
    data = json.loads(_FIXTURE.read_text())
    assert data.get("_at_surface") == "AT-E4"


@pytest.mark.at_surface("AT-E4")
@pytest.mark.integration
@pytest.mark.parametrize("conformance_forge", ["pi-forge"], indirect=True)
def test_unregistered_key_signature_rejected_live(conformance_forge) -> None:
    """LIVE: a brine signature from a signer the forge has never seen is
    refused with SIGNATURE_INVALID (impersonated sovereign)."""
    url = f"{conformance_forge.url}/task"
    body = _task_envelope({
        "key_scheme": "brine",
        "node_id": "impersonator-node",
        "policy_hash": None,
        "shadows_generated": [],
        "timestamp": "2026-07-07T00:00:00Z",
        "sig": "ab" * 64,
    })
    r = httpx.post(url, json=body, timeout=10.0)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "SIGNATURE_INVALID"


@pytest.mark.at_surface("AT-E4")
def test_forge_impersonation_integration_test_exists() -> None:
    """AT-E4 receipt-side source-of-truth: forged-receipt test at photophore."""
    assert _PHOTOPHORE_TEST.is_file(), (
        f"AT-E4: source-of-truth integration test missing at {_PHOTOPHORE_TEST}"
    )
