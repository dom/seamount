"""Signed task_result envelope parses via thermocline.envelope.TaskResult.parse_strict.

This asserts the structural contract: a llm-forge receipt is a valid
TaskResult per the spec's pydantic model. ``extra="forbid"`` in
thermocline-py means any field we add at the top level would break this
test, which is the desired guardrail.
"""
from __future__ import annotations

from _helpers import MockLLMProvider, example_inference_envelope


def test_verbatim_receipt_parses_as_taskresult(initialized_forge):
    from thermocline.envelope import TaskResult
    import server

    server.set_provider(MockLLMProvider(response_text="hello world"))
    try:
        tc = server.app.test_client()
        env = example_inference_envelope(prompt="say hello", privacy_mode="verbatim")
        r = tc.post(
            "/task",
            json=env,
            headers={"authorization": "Bearer fake-key"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        parsed = TaskResult.parse_strict(body)
        assert parsed.type == "task_result"
        assert parsed.envelope_id == env["envelope_id"]
        assert parsed.outputs["response"] == "hello world"
        assert parsed.outputs["provider"] == "unknown"  # LLM_FORGE_PROVIDER_LABEL unset in test
        assert parsed.receipt_signature is not None
        assert parsed.receipt_signature.key_scheme.value == "brine"
        sig_hex = parsed.receipt_signature.sig
        assert isinstance(sig_hex, str) and len(sig_hex) == 128
        int(sig_hex, 16)  # valid hex
    finally:
        server.set_provider(None)


def test_shadowed_receipt_parses_as_taskresult(initialized_forge):
    from thermocline.envelope import TaskResult
    import server

    server.set_provider(MockLLMProvider(response_text="A summary of the novel."))
    try:
        tc = server.app.test_client()
        env = example_inference_envelope(prompt="summarize a book", privacy_mode="shadowed")
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        parsed = TaskResult.parse_strict(body)
        assert "response" not in parsed.outputs
        assert "prompt_shadow" in parsed.outputs
        assert "response_shadow" in parsed.outputs
    finally:
        server.set_provider(None)


def test_unsupported_task_type_rejected(initialized_forge):
    """Conformance item 5: post a task with an unsupported type; expect 4xx."""
    import server

    tc = server.app.test_client()
    env = example_inference_envelope()
    env["task"]["type"] = "data.unsupported.gibberish.42"
    r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
    assert r.status_code in (400, 422)


def test_missing_provider_auth_returns_401(initialized_forge):
    """BYOK invariant: no Authorization header → 401."""
    import server

    tc = server.app.test_client()
    env = example_inference_envelope()
    r = tc.post("/task", json=env)  # no auth header
    assert r.status_code == 401
    body = r.get_json()
    assert body["error"]["code"] == "MISSING_PROVIDER_AUTH"


def test_default_node_id_matches_keypair_identity(monkeypatch):
    """Regression: out-of-the-box init+serve must sign successfully.

    History: FORGE_NODE_ID defaulted to 'llm-forge-local' while
    LLMFORGE_IDENTITY defaulted to 'llm-forge', so a fresh user running
    `python -m llm_forge init && python -m llm_forge serve` then posting a
    task would crash at signing time with
    'no brine key stored for identity llm-forge-local'.

    This test reproduces the out-of-the-box invocation by setting NO
    FORGE_NODE_ID override and asserting the signing chain produces a real
    receipt signature. It guards the (server.py defaults) → (envelope.py
    signing path) wiring against future drift.
    """
    import importlib
    import sys
    import uuid as _uuid

    # Fresh keystore namespace, default identity, NO FORGE_NODE_ID override.
    service = f"seamount.llmforge.test-defaults-{_uuid.uuid4()}"
    monkeypatch.setenv("LLMFORGE_KEYRING_SERVICE", service)
    monkeypatch.delenv("LLMFORGE_IDENTITY", raising=False)
    monkeypatch.delenv("FORGE_NODE_ID", raising=False)

    from thermocline.identity import BrineProvider

    provider = BrineProvider(keyring_service=service)
    # Generate keypair under the DEFAULT identity (no override) — must match
    # whatever the server's FORGE_NODE_ID default resolves to.
    default_identity = "llm-forge"
    provider.generate(identity=default_identity)

    for mod in ("forge_identity", "server"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    import server  # noqa: E402

    # The server module's FORGE_NODE_ID must equal the identity we generated under.
    assert server.FORGE_NODE_ID == default_identity, (
        f"FORGE_NODE_ID default ({server.FORGE_NODE_ID!r}) does not match "
        f"LLMFORGE_IDENTITY default ({default_identity!r}) — out-of-the-box "
        f"init+serve would fail at signing."
    )

    server.set_provider(MockLLMProvider(response_text="ok"))
    try:
        tc = server.app.test_client()
        env = example_inference_envelope()
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake"})
        assert r.status_code == 200, (
            f"expected 200 from default-config /task, got {r.status_code}: "
            f"{r.get_data(as_text=True)}"
        )
        body = r.get_json()
        assert body["receipt_signature"]["key_scheme"] == "brine"
        sig = body["receipt_signature"]["sig"]
        assert isinstance(sig, str) and len(sig) == 128, "expected real 64-byte sig"
        int(sig, 16)  # valid hex
    finally:
        server.set_provider(None)
        # Cleanup the test keypair.
        import keyring as _keyring
        try:
            _keyring.delete_password(service, default_identity)
        except Exception:
            pass
