"""Tests 3 + 4: zero/empty context refusal (D-02 hard gate)."""
from __future__ import annotations

from tests.conftest import make_task_envelope


# Test 3


def test_reject_zero_shadows(initialized_forge):
    """Only tier-2 inline blocks, no shadows → HTTP 400 UNSUPPORTED_TASK_TYPE."""
    _, _, app = initialized_forge
    body = make_task_envelope(context=[
        {"tier": 2, "role": "background", "content": "just inline, no shadow"},
    ])
    tc = app.test_client()
    r = tc.post("/task", json=body)
    assert r.status_code == 400
    body_out = r.get_json()
    assert body_out["error"]["code"] == "UNSUPPORTED_TASK_TYPE"
    assert "describe-forge requires at least one tier-1 shadow in context" in body_out["error"]["message"]


# Test 4


def test_reject_empty_context(initialized_forge):
    """context=[] → HTTP 400 UNSUPPORTED_TASK_TYPE (same code)."""
    _, _, app = initialized_forge
    body = make_task_envelope(context=[])
    tc = app.test_client()
    r = tc.post("/task", json=body)
    assert r.status_code == 400
    body_out = r.get_json()
    assert body_out["error"]["code"] == "UNSUPPORTED_TASK_TYPE"
