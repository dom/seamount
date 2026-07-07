"""LOW review fixes: request-size limit and non-reflective error envelopes."""
from __future__ import annotations

import importlib
import json
import sys

from _helpers import example_inference_envelope


def test_oversized_request_rejected_structured(initialized_forge, monkeypatch):
    """Bodies over FORGE_MAX_CONTENT_LENGTH get a structured 413."""
    monkeypatch.setenv("FORGE_MAX_CONTENT_LENGTH", "1024")
    importlib.reload(sys.modules["server"])
    import server
    tc = server.app.test_client()
    env = example_inference_envelope(prompt="x" * 4096)
    r = tc.post("/task", json=env, headers={"authorization": "Bearer k"})
    assert r.status_code == 413
    body = r.get_json()
    assert body["type"] == "task_error"
    assert body["error"]["code"] == "MALFORMED_ENVELOPE"


def test_error_envelope_caps_reflected_version(initialized_forge):
    """Attacker-supplied version strings are clipped in error envelopes."""
    import server
    tc = server.app.test_client()
    env = example_inference_envelope()
    env["thermocline"] = "v" * 5000
    r = tc.post("/task", json=env, headers={"authorization": "Bearer k"})
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"]["code"] == "UNSUPPORTED_VERSION"
    assert "v" * 100 not in body["error"]["message"]
    assert len(body["error"]["message"]) < 300


def test_upstream_error_message_is_generic(initialized_forge):
    """The raw upstream exception text must never reach the caller."""
    import server

    secret = "internal-upstream-secret-9f2c"

    class ExplodingProvider:
        def complete(self, **kwargs):
            raise RuntimeError(f"connection refused: {secret}")

    server.set_provider(ExplodingProvider())
    try:
        tc = server.app.test_client()
        env = example_inference_envelope()
        r = tc.post("/task", json=env, headers={"authorization": "Bearer k"})
        assert r.status_code == 502
        body = r.get_json()
        assert body["error"]["code"] == "UPSTREAM_PROVIDER_ERROR"
        assert secret not in json.dumps(body)
    finally:
        server.set_provider(None)
