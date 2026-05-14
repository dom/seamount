"""Templated description generator for tier-1 shadows.

The string template is NORMATIVE — any deviation breaks FORGE-03.

    "This forge received a shadow of type '<content_type>' with relevance <relevance>."

Privacy invariant T-03-11 (mixed-tier ignore-inline): this module NEVER reads or
echoes inline content from non-shadow blocks. Mixed-tier handling explicitly
filters context[] by ``tier == 1 and "shadow" in block`` BEFORE entering the
description loop. Non-shadow blocks are COUNTED (for the optional outputs.note
field) but their content fields are never inspected.

A regression test in tests/test_mixed_tier_ignore_inline.py plants a magic string
into a tier-2 inline block and asserts the magic string never appears anywhere
in the response body.
"""
from __future__ import annotations

from typing import Any


def filter_tier1_shadows(context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only blocks where ``tier == 1`` AND a ``shadow`` payload is present.

    The double check (tier and payload) handles malformed input where someone
    set tier=1 without a shadow payload (treated as ignored inline).
    """
    return [
        b for b in context
        if isinstance(b, dict)
        and b.get("tier") == 1
        and isinstance(b.get("shadow"), dict)
    ]


def count_ignored_inline_blocks(context: list[dict[str, Any]]) -> int:
    """Return the number of blocks that DO NOT carry a tier-1 shadow payload.

    These are the blocks describe-forge's privacy contract refuses to read.
    """
    return sum(
        1 for b in context
        if isinstance(b, dict)
        and not (b.get("tier") == 1 and isinstance(b.get("shadow"), dict))
    )


def describe_one_shadow(shadow: dict[str, Any]) -> dict[str, Any]:
    """Return one ShadowDescription per the normative template.

    The output dict contains:
        shadow_id      — the shadow's id (echo)
        content_type   — the shadow's declared type (echo)
        relevance      — the shadow's relevance score (echo)
        description    — the NORMATIVE templated string

    Raises ``KeyError`` if the shadow is malformed (missing shadow_id,
    content_type, or relevance) — the server lifts this into MALFORMED_ENVELOPE.
    """
    shadow_id = shadow["shadow_id"]
    content_type = shadow["content_type"]
    relevance = shadow["relevance"]
    description = (
        f"This forge received a shadow of type '{content_type}' "
        f"with relevance {relevance}."
    )
    return {
        "shadow_id": shadow_id,
        "content_type": content_type,
        "relevance": relevance,
        "description": description,
    }


def describe_shadows(context: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Iterate tier-1 shadows in context[] and return ``(descriptions, ignored_count)``.

    Mixed-tier privacy invariant (T-03-11): inline (non-shadow) blocks contribute
    ONLY to the ignored count; their ``content`` field is NEVER read or echoed.
    """
    shadows = filter_tier1_shadows(context)
    ignored = count_ignored_inline_blocks(context)
    descriptions = [describe_one_shadow(s["shadow"]) for s in shadows]
    return descriptions, ignored


def collect_tiers_present(context: list[dict[str, Any]]) -> list[int]:
    """Sorted unique tiers seen in the request envelope (``provenance.tiers_present``)."""
    seen: set[int] = set()
    for b in context:
        if isinstance(b, dict) and "tier" in b:
            try:
                seen.add(int(b["tier"]))
            except (TypeError, ValueError):
                continue
    return sorted(seen)
