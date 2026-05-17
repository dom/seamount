"""shadows.py — adapt chat messages to photophore.shadow.generate().

photophore's shadow API takes ``content: bytes`` plus a ContentType. Chat
messages are structured (list of role+content dicts), so we canonical-JSON
them into bytes before calling ``generate()`` with
``ContentType.CONVERSATION``. The same approach is used for the model's
response text (treated as a single conversation turn).

The irreversibility test runs INSIDE photophore.shadow.generate(); a
ShadowIrreversibilityError raised here MUST propagate to the caller and
abort dispatch per SHADOW-04. llm-forge does not catch and continue —
shadowed mode is a privacy guarantee, not a best-effort attempt.
"""
from __future__ import annotations

import json
from typing import Any

from photophore.shadow import ContentType, Shadow, generate


def shadow_messages(messages: list[dict[str, Any]]) -> Shadow:
    """Produce a tier-1 conversation Shadow over the prompt messages.

    Canonical-JSON serialization (sort_keys=True, no insignificant
    whitespace) ensures stable byte input independent of dict ordering.
    """
    blob = _canonical_bytes(messages)
    result = generate(blob, ContentType.CONVERSATION, relevance=0.5)
    return result.shadow


def shadow_response(response_text: str) -> Shadow:
    """Produce a tier-1 conversation Shadow over the model response text.

    Encoded as UTF-8 bytes directly (single turn — no JSON wrapping needed).
    """
    blob = response_text.encode("utf-8")
    result = generate(blob, ContentType.CONVERSATION, relevance=0.5)
    return result.shadow


def shadow_to_dict(shadow: Shadow) -> dict[str, Any]:
    """Serialize a Shadow to the dict shape used in task_result.outputs.

    Mirrors the spec ``_Shadow`` sub-block in thermocline-py:
    shadow_id, content_type (string value of the enum), abstraction,
    relevance. Tier (always 1) is implicit at the consumer.
    """
    return {
        "shadow_id": shadow.shadow_id,
        "content_type": shadow.content_type.value,
        "abstraction": shadow.abstraction,
        "relevance": shadow.relevance,
    }


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


__all__ = ["shadow_messages", "shadow_response", "shadow_to_dict"]
