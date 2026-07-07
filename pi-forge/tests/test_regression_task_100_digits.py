"""Regression: pi-forge processes examples/task-100-digits.json with output equivalence.

FORGE-02 baseline check — the v0.1 pi-forge fixture has shipped with
``thermocline=0.3.0``; the upgraded forge must still process it correctly
(modulo result_id + completed_at which are nondeterministic).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from envelope import (
    build_task_result,
    validate_task_envelope,
)
from pi import compute_pi


FIXTURE = Path(__file__).parent.parent / "examples" / "task-100-digits.json"

# Known-good first 100 digits of pi as the mpmath path returns them.
# (mpmath.mp.dps = digits+10; mp.pi.__mpf__ truncated to digits decimals.)
EXPECTED_PI_100 = (
    "3.1415926535897932384626433832795028841971693993751058209749445923078164062862089986280348253421170679"
)


def test_regression_task_100_digits_equivalent():
    """Replay the v0.1 fixture through the upgraded envelope.py + pi.py path."""
    assert FIXTURE.exists(), f"missing fixture: {FIXTURE}"
    body = json.loads(FIXTURE.read_text())

    # Validate (fixture declares 0.3.0; SUPPORTED_VERSIONS includes 0.3.0).
    # The v0.1 fixture is unsigned (key_scheme=none), so replay it through
    # the explicit dev-mode path.
    envelope_id = validate_task_envelope(body, "0.3.0", require_dispatch_sig=False)
    assert envelope_id == body["envelope_id"]

    digits = body["task"]["parameters"]["digits"]
    pi_str = compute_pi(digits)

    # Build a result envelope in dev mode (no keystore touch).
    result = build_task_result(
        envelope_id=envelope_id,
        responder="pi-forge-local",
        key_scheme="none",
        outputs={
            "pi": pi_str,
            "digits_computed": digits,
            "algorithm": "mpmath",
        },
        shadows_received=[],
        tiers_present=[2],
    )

    # Equivalence assertions (modulo result_id + timestamps).
    assert result["thermocline"] == "0.3.1"
    assert result["type"] == "task_result"
    assert result["envelope_id"] == envelope_id
    assert result["responder"] == "pi-forge-local"
    assert result["outputs"]["pi"] == EXPECTED_PI_100
    assert result["outputs"]["digits_computed"] == 100
    assert result["outputs"]["algorithm"] == "mpmath"
    assert result["provenance"]["shadows_received"] == []
    assert result["provenance"]["tiers_present"] == [2]
    assert result["provenance"]["local_tiers_present"] is False
    assert result["receipt_signature"]["key_scheme"] == "none"
    assert result["receipt_signature"]["sig"] is None
