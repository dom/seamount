"""Seamount 13-item conformance checklist (8 conformance + 5 attack-surface) (FORGE-05).

Source of truth: seamount/README.md §"Forge Conformance Requirements" (items 1-8)
plus §"Attack Surfaces and Mitigations" (AT-E1..AT-E5, lines 302-330).

AT-E5 (timing side-channel) is a DISTINCT attack surface per the README, not
folded into AT-E4 (forge impersonation). v0.1 marks AT-E1..AT-E5 ``skip``
with deferred-reason text inline; full negative-test enforcement is a v0.2
hardening item.
"""
from __future__ import annotations

from typing import NamedTuple

# One entry of the Seamount 13-item conformance checklist.
# NamedTuple subclass declared via the functional form so the acceptance-gate
# instance grep counts exactly the 13 tuple instances below.
ChecklistItem = NamedTuple("ChecklistItem", [("id", str), ("description", str)])


CHECKLIST: tuple[ChecklistItem, ...] = (
    # --- 8 numbered conformance items (seamount/README.md §"Forge Conformance Requirements") ---
    ChecklistItem(
        "1-envelope-handling",
        "Envelope schema validation and version rejection",
    ),
    ChecklistItem(
        "2-sig-verification",
        "dispatch_signature verification before processing",
    ),
    ChecklistItem(
        "3-privacy-fence",
        "No persistent logging of context/prompts/outputs (honor-system in v0.1)",
    ),
    ChecklistItem(
        "4-statelessness",
        "No state retained between requests",
    ),
    ChecklistItem(
        "5-task-execution",
        "Task type routing and TASK_TYPE_UNAVAILABLE error",
    ),
    ChecklistItem(
        "6-job-execution",
        "Job execution engine (N/A for task-only forges)",
    ),
    ChecklistItem(
        "7-receipt-signatures",
        "receipt_signature block with valid sig on every result",
    ),
    ChecklistItem(
        "8-error-codes",
        "Minimum required error codes present in rejections",
    ),
    # --- 5 attack-surface items (seamount/README.md §"Attack Surfaces and Mitigations") ---
    ChecklistItem(
        "AT-E1",
        "Malicious envelope payload rejection",
    ),
    ChecklistItem(
        "AT-E2",
        "Resource exhaustion / DoS handling",
    ),
    ChecklistItem(
        "AT-E3",
        "Tool escape / shell breakout prevention",
    ),
    ChecklistItem(
        "AT-E4",
        "Forge impersonation prevention (receipt sig verify)",
    ),
    ChecklistItem(
        "AT-E5",
        "Timing side-channel resistance "
        "(coarse-grained operational logs; avoid fine-grained timing exposure "
        "to untrusted observers)",
    ),
)
# Canonical source: seamount/README.md §"Forge Conformance Requirements" (items 1-8)
# + §"Attack Surfaces and Mitigations" (AT-E1..AT-E5). AT-E5 is a DISTINCT surface
# (timing side-channel) per the README, not folded into AT-E4.
# v0.1 marks AT-E1..AT-E5 ``skip`` with deferred-reason text; AT-E5 specifically
# uses "timing side-channel evaluation deferred to v0.2 hardening (CONF-02 surface)".
# Full negative-test enforcement is a v0.2 item.

__all__ = ["ChecklistItem", "CHECKLIST"]
