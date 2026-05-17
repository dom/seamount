"""Relay-fidelity tests: forge forwards the caller's messages verbatim.

The brine signature attests "I, llm-forge, forwarded these exact messages
to provider X and received this verbatim response." These tests assert
the first half: the messages the upstream provider sees are byte-identical
to what the caller put in the envelope.
"""
from __future__ import annotations

import json

from _helpers import MockLLMProvider, example_inference_envelope


def test_messages_forwarded_verbatim_to_provider(initialized_forge):
    import server

    mock = MockLLMProvider()
    server.set_provider(mock)
    try:
        tc = server.app.test_client()
        env = example_inference_envelope(
            prompt="What is the airspeed velocity of an unladen swallow?",
        )
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
        assert r.status_code == 200
        assert len(mock.seen_calls) == 1
        call = mock.seen_calls[0]
        assert call["model"] == env["task"]["parameters"]["model"]
        assert call["messages"] == env["task"]["parameters"]["messages"]
        assert call["max_tokens"] == env["task"]["parameters"]["max_tokens"]
        assert call["temperature"] == env["task"]["parameters"]["temperature"]
        assert call["api_key"] == "fake-key"
    finally:
        server.set_provider(None)


def test_provider_response_forwarded_verbatim_to_envelope(initialized_forge):
    import server

    canned = "The answer is 42, definitively."
    mock = MockLLMProvider(response_text=canned, tokens_in=12, tokens_out=8)
    server.set_provider(mock)
    try:
        tc = server.app.test_client()
        env = example_inference_envelope()
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
        assert r.status_code == 200
        body = r.get_json()
        assert body["outputs"]["response"] == canned
        assert body["outputs"]["tokens_in"] == 12
        assert body["outputs"]["tokens_out"] == 8
        assert body["outputs"]["finish_reason"] == "stop"
        assert body["outputs"]["provider_request_id"] == "mock-req-id"
    finally:
        server.set_provider(None)


def test_byok_key_not_persisted_anywhere(initialized_forge, tmp_path):
    """The provider API key the caller supplies must not leak into the receipt."""
    import server

    secret = "sk-this-must-never-appear-anywhere-2c7f9b"
    mock = MockLLMProvider(response_text="ok")
    server.set_provider(mock)
    try:
        tc = server.app.test_client()
        env = example_inference_envelope()
        r = tc.post("/task", json=env, headers={"authorization": f"Bearer {secret}"})
        assert r.status_code == 200
        body = r.get_json()
        # The full signed envelope serialized as JSON must contain no copy.
        serialized = json.dumps(body)
        assert secret not in serialized
        # And not in any of the envelope's nested string values.
        def walk(node):
            if isinstance(node, str):
                assert secret not in node
            elif isinstance(node, dict):
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(body)
    finally:
        server.set_provider(None)
