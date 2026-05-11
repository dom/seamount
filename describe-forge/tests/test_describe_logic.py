"""Tests for describe-forge core templating logic.

Behaviors covered: Test 1, 2, 6, 7, 9, 11 of Task 3 plan.
"""
from __future__ import annotations

import pytest

from tests.conftest import make_task_envelope


# Test 1


def test_describe_one_shadow(initialized_forge):
    """Single tier-1 shadow → 1 description with normative D-02 string."""
    service, identity, app = initialized_forge
    body = make_task_envelope(context=[
        {
            "tier": 1,
            "shadow": {
                "shadow_id": "s1",
                "content_type": "document",
                "relevance": 0.85,
                "abstraction": "Document about Q4 plan",
            },
        }
    ])
    tc = app.test_client()
    r = tc.post("/task", json=body)
    assert r.status_code == 200, r.get_data(as_text=True)
    result = r.get_json()
    descs = result["outputs"]["descriptions"]
    assert len(descs) == 1
    assert descs[0] == {
        "shadow_id": "s1",
        "content_type": "document",
        "relevance": 0.85,
        "description": "This forge received a shadow of type 'document' with relevance 0.85.",
    }


# Test 2


def test_describe_multiple_shadows(initialized_forge):
    """Two tier-1 shadows → 2 descriptions, each with the normative string."""
    _, _, app = initialized_forge
    body = make_task_envelope(context=[
        {"tier": 1, "shadow": {"shadow_id": "a", "content_type": "document", "relevance": 0.9}},
        {"tier": 1, "shadow": {"shadow_id": "b", "content_type": "calendar", "relevance": 0.3}},
    ])
    tc = app.test_client()
    r = tc.post("/task", json=body)
    assert r.status_code == 200
    descs = r.get_json()["outputs"]["descriptions"]
    assert len(descs) == 2
    assert descs[0]["description"] == "This forge received a shadow of type 'document' with relevance 0.9."
    assert descs[1]["description"] == "This forge received a shadow of type 'calendar' with relevance 0.3."


# Test 6


def test_provenance_local_tiers_present_always_false(initialized_forge):
    """provenance.local_tiers_present is always False (tier-0 never crosses)."""
    _, _, app = initialized_forge
    body = make_task_envelope(context=[
        {"tier": 1, "shadow": {"shadow_id": "x", "content_type": "doc", "relevance": 1.0}}
    ])
    tc = app.test_client()
    r = tc.post("/task", json=body)
    assert r.status_code == 200
    assert r.get_json()["provenance"]["local_tiers_present"] is False


# Test 7


def test_malformed_shadow_block(initialized_forge):
    """Tier-1 shadow missing required fields → HTTP 400 MALFORMED_ENVELOPE."""
    _, _, app = initialized_forge
    body = make_task_envelope(context=[
        {"tier": 1, "shadow": {"missing_fields": "no shadow_id, no content_type"}}
    ])
    tc = app.test_client()
    r = tc.post("/task", json=body)
    assert r.status_code == 400
    body_out = r.get_json()
    assert body_out["error"]["code"] == "MALFORMED_ENVELOPE"


# Test 9


def test_receipt_signature_real_brine(initialized_forge):
    """receipt_signature.sig is 128-char hex (real ed25519 sig)."""
    _, _, app = initialized_forge
    body = make_task_envelope(context=[
        {"tier": 1, "shadow": {"shadow_id": "x", "content_type": "doc", "relevance": 0.5}}
    ])
    tc = app.test_client()
    r = tc.post("/task", json=body)
    assert r.status_code == 200
    rs = r.get_json()["receipt_signature"]
    assert rs["key_scheme"] == "brine"
    assert isinstance(rs["sig"], str)
    assert len(rs["sig"]) == 128
    int(rs["sig"], 16)


# Test 11


def test_relevance_formatting_preserved(initialized_forge):
    """relevance values printed via Python's default float-to-str (no rounding)."""
    _, _, app = initialized_forge
    cases = [
        (1.0, "with relevance 1.0."),
        (0.85, "with relevance 0.85."),
        (0, "with relevance 0."),
    ]
    tc = app.test_client()
    for rel, suffix in cases:
        body = make_task_envelope(context=[
            {"tier": 1, "shadow": {"shadow_id": "x", "content_type": "doc", "relevance": rel}}
        ])
        r = tc.post("/task", json=body)
        assert r.status_code == 200, f"failed for relevance={rel}: {r.get_data(as_text=True)}"
        desc = r.get_json()["outputs"]["descriptions"][0]["description"]
        assert desc.endswith(suffix), f"got: {desc}"
