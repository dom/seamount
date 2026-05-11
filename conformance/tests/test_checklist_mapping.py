"""Tests for the 13-item conformance checklist + report structure.

Tests 5 + 6 of Plan 03-03 Task 3:
    - test_checklist_has_13_items
    - test_report_json_shape
"""
from __future__ import annotations

import json

from forge_conformance._checklist import CHECKLIST, ChecklistItem
from forge_conformance._report import build_report


def test_checklist_has_13_items() -> None:
    """Plan 03-03 WARNING 2: the checklist has exactly 13 items.

    8 numbered conformance items (1-8) from seamount/README.md §"Forge
    Conformance Requirements" + 5 attack-surface items (AT-E1..AT-E5) from
    §"Attack Surfaces and Mitigations". AT-E5 is a DISTINCT 13th item
    (timing side-channel) per the README line 326, NOT folded into AT-E4.
    """
    assert len(CHECKLIST) == 13, (
        f"expected 13 checklist items (8 numbered + 5 AT-E), got {len(CHECKLIST)}"
    )
    for item in CHECKLIST:
        assert isinstance(item, ChecklistItem)
        assert isinstance(item.id, str)
        assert isinstance(item.description, str)
        assert item.id, "ChecklistItem.id must be non-empty"
        assert item.description, "ChecklistItem.description must be non-empty"

    ids = [item.id for item in CHECKLIST]
    # Exact ordering matters — third-party impls parse CHECKLIST as a tuple.
    assert ids == [
        "1-envelope-handling",
        "2-sig-verification",
        "3-privacy-fence",
        "4-statelessness",
        "5-task-execution",
        "6-job-execution",
        "7-receipt-signatures",
        "8-error-codes",
        "AT-E1",
        "AT-E2",
        "AT-E3",
        "AT-E4",
        "AT-E5",
    ]


def test_at_e5_is_distinct_surface() -> None:
    """AT-E5 (timing side-channel) is a separate item from AT-E4 (impersonation).

    Pins WARNING 2 of the plan-checker review: earlier drafts of the plan
    counted 12 items by folding AT-E5 into AT-E4. The canonical Seamount
    README lists them as DISTINCT surfaces (lines 302..330).
    """
    at_e4 = next(item for item in CHECKLIST if item.id == "AT-E4")
    at_e5 = next(item for item in CHECKLIST if item.id == "AT-E5")
    assert at_e4.id != at_e5.id
    assert "impersonation" in at_e4.description.lower()
    assert "timing" in at_e5.description.lower()


def test_report_json_shape() -> None:
    """The report dict has all top-level keys and per-item shape."""
    item_results = {item.id: {"status": "skip", "message": "test"} for item in CHECKLIST}
    report = build_report(
        target_url="http://test.invalid",
        role="pi-forge",
        started_at="2026-05-11T00:00:00Z",
        completed_at="2026-05-11T00:00:01Z",
        item_results=item_results,
    )

    for key in (
        "target_url",
        "role",
        "started_at",
        "completed_at",
        "checklist",
        "total_pass",
        "total_fail",
        "total_skip",
    ):
        assert key in report, f"report missing top-level key {key!r}"

    assert isinstance(report["checklist"], list)
    assert len(report["checklist"]) == 13
    for entry in report["checklist"]:
        assert set(entry.keys()) == {"id", "description", "status", "message"}, (
            f"unexpected entry keys: {entry.keys()}"
        )
        assert entry["status"] in {"pass", "fail", "skip"}

    assert report["total_skip"] == 13
    assert report["total_pass"] == 0
    assert report["total_fail"] == 0

    # JSON round-trip
    serialized = json.dumps(report)
    assert "13" not in serialized or "total_skip" in serialized  # sanity
    roundtrip = json.loads(serialized)
    assert roundtrip == report


def test_report_counts_pass_fail_skip() -> None:
    """Pass/fail/skip counts sum to 13 and match status values."""
    item_results: dict[str, dict[str, str]] = {}
    expected_pass = ["1-envelope-handling", "7-receipt-signatures", "3-privacy-fence"]
    expected_fail = ["8-error-codes"]
    for item in CHECKLIST:
        if item.id in expected_pass:
            item_results[item.id] = {"status": "pass", "message": "ok"}
        elif item.id in expected_fail:
            item_results[item.id] = {"status": "fail", "message": "bad"}
        else:
            item_results[item.id] = {"status": "skip", "message": "skipped"}

    report = build_report(
        target_url="http://test.invalid",
        role="pi-forge",
        started_at="x",
        completed_at="y",
        item_results=item_results,
    )

    assert report["total_pass"] == len(expected_pass) == 3
    assert report["total_fail"] == len(expected_fail) == 1
    assert report["total_skip"] == 13 - 3 - 1 == 9
