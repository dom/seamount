"""providers.py — LLMProvider Protocol + OpenAI-compatible adapter.

The forge talks to upstream model hosts through a single Protocol so
0G Private Computer, OpenAI, OpenRouter, vLLM, and any other
OpenAI-Chat-Completions-compatible endpoint drop in by swapping
``LLM_FORGE_BASE_URL`` + ``LLM_FORGE_PROVIDER_LABEL``.

Auth is BYOK: the caller's HTTP request to ``/task`` carries
``Authorization: Bearer <provider-key>``; the forge forwards that header
verbatim and never persists it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class ProviderResult:
    """Verbatim relay of the provider's chat-completion response.

    Fields mirror OpenAI Chat Completions response shape, but only the bits
    llm-forge writes into the signed envelope. Any extra provider-specific
    fields land in ``raw`` so a future provenance.relay sub-block can carry
    them without changing the Protocol.
    """

    response_text: str
    model: str
    finish_reason: str
    tokens_in: int
    tokens_out: int
    provider_request_id: str
    raw: dict[str, Any]


class LLMProvider(Protocol):
    """Minimal contract every provider adapter implements."""

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ProviderResult:
        ...


class OpenAICompatibleProvider:
    """POSTs ``{base_url}/chat/completions`` and returns a ProviderResult.

    Works against OpenAI, 0G Private Computer (https://pc.0g.ai/api/v1),
    OpenRouter (https://openrouter.ai/api/v1), local vLLM, and anything else
    that speaks the same wire shape.
    """

    def __init__(self, *, base_url: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ProviderResult:
        body: dict[str, Any] = {"model": model, "messages": messages}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if extra:
            body.update(extra)

        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        resp = httpx.post(url, headers=headers, json=body, timeout=self.timeout_seconds)
        resp.raise_for_status()
        raw = resp.json()

        # Standard OpenAI Chat Completions shape.
        choice0 = (raw.get("choices") or [{}])[0]
        message = choice0.get("message") or {}
        usage = raw.get("usage") or {}
        return ProviderResult(
            response_text=message.get("content", "") or "",
            model=raw.get("model", model),
            finish_reason=choice0.get("finish_reason", "") or "",
            tokens_in=int(usage.get("prompt_tokens", 0) or 0),
            tokens_out=int(usage.get("completion_tokens", 0) or 0),
            provider_request_id=raw.get("id", "") or "",
            raw=raw,
        )


__all__ = ["LLMProvider", "OpenAICompatibleProvider", "ProviderResult"]
