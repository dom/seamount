"""Cross-test helpers for llm-forge — non-fixture utilities.

pytest's conftest.py is plugin-loaded (not importable as a module), so
shared test classes and builder functions live here instead.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class MockLLMProvider:
    """Test-double LLMProvider that records inputs and returns a canned response."""

    response_text: str = "canned mock response"
    model: str = "mock-model"
    finish_reason: str = "stop"
    tokens_in: int = 7
    tokens_out: int = 11
    provider_request_id: str = "mock-req-id"
    seen_calls: list = field(default_factory=list)

    def complete(self, **kwargs):
        from providers import ProviderResult

        self.seen_calls.append(kwargs)
        return ProviderResult(
            response_text=self.response_text,
            model=self.model,
            finish_reason=self.finish_reason,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            provider_request_id=self.provider_request_id,
            raw={"id": self.provider_request_id, "mock": True},
        )


def example_inference_envelope(
    *,
    prompt: str = "Summarize Moby-Dick in one paragraph.",
    privacy_mode: str = "verbatim",
    model: str = "deepseek-v4-pro",
) -> dict:
    """Build a minimal valid data.inference.text task envelope."""
    return {
        "thermocline": "0.3.1",
        "type": "task",
        "envelope_id": str(uuid.uuid4()),
        "issued_at": "2026-05-16T12:00:00Z",
        "issuer": "test-sovereign",
        "task": {
            "type": "data.inference.text",
            "instruction": "Run text inference.",
            "parameters": {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.0,
                "privacy_mode": privacy_mode,
            },
        },
        "context": [],
        "dispatch_signature": {
            "key_scheme": "none",
            "node_id": "test-sovereign",
            "policy_hash": None,
            "shadows_generated": [],
            "timestamp": "2026-05-16T12:00:00Z",
            "sig": None,
        },
    }
