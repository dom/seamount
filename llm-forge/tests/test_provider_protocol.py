"""OpenAICompatibleProvider posts the OpenAI Chat Completions wire shape.

Uses httpx's MockTransport to intercept the request and validate the
HTTP-level contract without touching a network.
"""
from __future__ import annotations

import json

import httpx
import pytest

from providers import OpenAICompatibleProvider, ProviderResult


def _fake_chat_completions_response(model: str) -> dict:
    return {
        "id": "chatcmpl-fake-001",
        "object": "chat.completion",
        "created": 1234567890,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "42"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
    }


def test_provider_posts_openai_chat_completions_shape(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=_fake_chat_completions_response("deepseek-v4-pro"))

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Client(transport=transport).post(*a, **kw))

    p = OpenAICompatibleProvider(base_url="https://example.test/api/v1")
    out = p.complete(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "What is 6 * 7?"}],
        api_key="sk-test-1234",
        max_tokens=10,
        temperature=0.0,
    )

    assert isinstance(out, ProviderResult)
    assert out.response_text == "42"
    assert out.model == "deepseek-v4-pro"
    assert out.finish_reason == "stop"
    assert out.tokens_in == 5
    assert out.tokens_out == 1
    assert out.provider_request_id == "chatcmpl-fake-001"

    assert captured["url"] == "https://example.test/api/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer sk-test-1234"
    body = captured["json"]
    assert body["model"] == "deepseek-v4-pro"
    assert body["messages"] == [{"role": "user", "content": "What is 6 * 7?"}]
    assert body["max_tokens"] == 10
    assert body["temperature"] == 0.0


def test_provider_propagates_upstream_4xx(monkeypatch):
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Client(transport=transport).post(*a, **kw))

    p = OpenAICompatibleProvider(base_url="https://example.test/api/v1")
    with pytest.raises(httpx.HTTPStatusError):
        p.complete(
            model="m", messages=[{"role": "user", "content": "x"}], api_key="bad",
        )


def test_provider_omits_unset_optional_params(monkeypatch):
    captured: dict = {}

    def handler(request):
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=_fake_chat_completions_response("m"))

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Client(transport=transport).post(*a, **kw))

    p = OpenAICompatibleProvider(base_url="https://example.test/api/v1")
    p.complete(model="m", messages=[{"role": "user", "content": "x"}], api_key="k")

    body = captured["json"]
    assert "max_tokens" not in body
    assert "temperature" not in body
