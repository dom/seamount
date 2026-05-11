"""Structured pass/fail report emitter (JSON + human-readable).

Maps the raw harness results dict ``{item_id: {status, message}}`` into the
canonical 13-entry report against the :mod:`forge_conformance._checklist`
ordering. The output shape is stable across versions so CI consumers can
parse it programmatically.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ._checklist import CHECKLIST


def build_report(
    *,
    target_url: str,
    role: str,
    started_at: str,
    completed_at: str,
    item_results: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Assemble the canonical report structure from harness raw results."""
    checklist_out: list[dict[str, str]] = []
    total_pass = total_fail = total_skip = 0
    for item in CHECKLIST:
        result = item_results.get(item.id, {"status": "skip", "message": "not run"})
        status = result["status"]
        checklist_out.append(
            {
                "id": item.id,
                "description": item.description,
                "status": status,
                "message": result["message"],
            }
        )
        if status == "pass":
            total_pass += 1
        elif status == "fail":
            total_fail += 1
        else:
            total_skip += 1
    return {
        "target_url": target_url,
        "role": role,
        "started_at": started_at,
        "completed_at": completed_at,
        "checklist": checklist_out,
        "total_pass": total_pass,
        "total_fail": total_fail,
        "total_skip": total_skip,
    }


def now_utc_iso() -> str:
    """Return current UTC time as ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


def emit_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2)


def emit_human(report: dict[str, Any]) -> str:
    lines = [
        f"forge_conformance report for {report['role']} @ {report['target_url']}",
        f"started:   {report['started_at']}",
        f"completed: {report['completed_at']}",
        "",
        f"{'ID':<24} {'STATUS':<6}  MESSAGE",
        "-" * 80,
    ]
    for item in report["checklist"]:
        lines.append(
            f"{item['id']:<24} {item['status']:<6}  {item['message']}"
        )
    lines.append("")
    lines.append(
        f"PASS: {report['total_pass']}  FAIL: {report['total_fail']}  "
        f"SKIP: {report['total_skip']}"
    )
    return "\n".join(lines)


__all__ = ["build_report", "now_utc_iso", "emit_json", "emit_human"]
