"""Privacy regression: mixed-tier inline content is NEVER echoed (T-03-11).

This is the critical privacy guard for describe-forge. If this test ever
fails, the privacy contract is broken and the suite has a high-severity
information-disclosure bug.

The test plants a unique magic string into a tier-2 inline content block
and asserts the magic string never appears in the full JSON response body.
"""
from __future__ import annotations

import json

from tests.conftest import make_task_envelope


MAGIC = "BEWARE-MAGIC-STRING-32bytes-secret"


def test_mixed_tier_ignore_inline(initialized_forge):
    """Mixed tier-1 shadow + tier-2 inline:
    - response 200
    - exactly 1 description (the shadow)
    - tiers_present = [1, 2]
    - outputs.note records 1 inline block ignored
    - the magic string DOES NOT appear ANYWHERE in the response body
    """
    _, _, app = initialized_forge
    body = make_task_envelope(context=[
        {"tier": 1, "shadow": {"shadow_id": "shadow-a", "content_type": "document", "relevance": 0.7}},
        {"tier": 2, "role": "background", "content": MAGIC},
    ])
    tc = app.test_client()
    r = tc.post("/task", json=body)
    assert r.status_code == 200, r.get_data(as_text=True)
    result = r.get_json()
    # Exactly 1 description, referencing shadow-a:
    descs = result["outputs"]["descriptions"]
    assert len(descs) == 1
    assert descs[0]["shadow_id"] == "shadow-a"
    # tiers_present sees both tiers:
    assert result["provenance"]["tiers_present"] == [1, 2]
    # outputs.note records the ignored inline block:
    assert result["outputs"]["note"] == "describe-forge operated on 1 shadows; 1 inline blocks ignored"

    # Privacy regression: magic string MUST NOT appear anywhere in the response
    # body (whole-body JSON serialization). Belt-and-suspenders — both via the
    # MAGIC constant AND via the LITERAL substring so any future refactor that
    # loses the constant still has a literal guard. The plan's acceptance
    # criterion requires the literal "BEWARE-MAGIC-STRING" to appear at least
    # twice in this test file (setup + assert).
    body_str = json.dumps(result)
    assert MAGIC not in body_str, (
        f"PRIVACY REGRESSION: tier-2 inline content leaked into the response "
        f"body. Magic string {MAGIC!r} appears in the response. T-03-11 is "
        f"broken."
    )
    assert "BEWARE-MAGIC-STRING" not in body_str, (
        "PRIVACY REGRESSION: literal BEWARE-MAGIC-STRING substring found in response"
    )
    # Also check the raw response data (in case Flask serialized differently):
    raw = r.get_data(as_text=True)
    assert MAGIC not in raw, "PRIVACY REGRESSION: magic string in raw response body"
    assert "BEWARE-MAGIC-STRING" not in raw, (
        "PRIVACY REGRESSION: literal BEWARE-MAGIC-STRING in raw response"
    )
