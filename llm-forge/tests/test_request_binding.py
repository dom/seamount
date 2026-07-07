"""MEDIUM review fix: the relay receipt must bind the request, not just the output.

Before this fix the receipt signed only outputs + envelope_id, so the same
signed response could be presented as the answer to a different question.
``outputs.request_digest`` commits the signed receipt to the exact request
(model, messages, params, privacy_mode) the forge relayed.

Placement note: the digest lives in ``outputs`` (free-form, covered by the
receipt signature), not ``provenance``: thermocline's ``_Provenance`` model
is ``extra="forbid"``, so a provenance field would break
``TaskResult.parse_strict`` for every consumer.
"""
from __future__ import annotations

from _helpers import MockLLMProvider, example_inference_envelope

from envelope import compute_request_digest


def test_receipt_carries_request_digest(initialized_forge):
    import server

    server.set_provider(MockLLMProvider(response_text="ok"))
    try:
        tc = server.app.test_client()
        env = example_inference_envelope(prompt="What is the capital of France?")
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
        assert r.status_code == 200
        body = r.get_json()
        params = env["task"]["parameters"]
        expected = compute_request_digest(
            model=params["model"],
            messages=params["messages"],
            max_tokens=params["max_tokens"],
            temperature=params["temperature"],
            privacy_mode="verbatim",
        )
        assert body["outputs"]["request_digest"] == expected
        assert expected.startswith("sha256:")
    finally:
        server.set_provider(None)


def test_request_digest_differs_across_requests(initialized_forge):
    import server

    server.set_provider(MockLLMProvider(response_text="ok"))
    try:
        tc = server.app.test_client()
        digests = []
        for prompt in ("first question", "second question"):
            env = example_inference_envelope(prompt=prompt)
            r = tc.post(
                "/task", json=env, headers={"authorization": "Bearer fake-key"}
            )
            assert r.status_code == 200
            digests.append(r.get_json()["outputs"]["request_digest"])
        assert digests[0] != digests[1]
    finally:
        server.set_provider(None)


def test_request_digest_present_in_shadowed_mode(initialized_forge):
    import server

    server.set_provider(MockLLMProvider(response_text="a summary"))
    try:
        tc = server.app.test_client()
        env = example_inference_envelope(
            prompt="summarize the confidential report", privacy_mode="shadowed"
        )
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
        assert r.status_code == 200
        outputs = r.get_json()["outputs"]
        assert "response" not in outputs
        assert outputs["request_digest"].startswith("sha256:")
    finally:
        server.set_provider(None)


def test_receipt_signature_covers_request_digest(initialized_forge):
    """Mutating request_digest after signing must invalidate the receipt sig."""
    import server
    from thermocline.identity import BrineProvider, Signature
    from thermocline.schemes import KeyScheme

    service, identity, _ = initialized_forge
    provider = BrineProvider(keyring_service=service)

    server.set_provider(MockLLMProvider(response_text="ok"))
    try:
        tc = server.app.test_client()
        env = example_inference_envelope()
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
        assert r.status_code == 200
        result = r.get_json()

        def verify(result_envelope: dict) -> object:
            signing_input = {
                k: v for k, v in result_envelope.items() if k != "receipt_signature"
            }
            signing_input["receipt_signature"] = {
                **result_envelope["receipt_signature"],
                "sig": None,
            }
            sig = Signature(
                scheme=KeyScheme.BRINE,
                bytes_=bytes.fromhex(result_envelope["receipt_signature"]["sig"]),
                signer_identity=identity,
            )
            return provider.verify(envelope=signing_input, signature=sig)

        assert verify(result) is not None, "genuine receipt must verify"
        tampered = {**result, "outputs": {**result["outputs"]}}
        tampered["outputs"]["request_digest"] = "sha256:" + "0" * 64
        assert verify(tampered) is None, (
            "receipt with a swapped request_digest must NOT verify"
        )
    finally:
        server.set_provider(None)
