"""Privacy invariant: in shadowed mode, no prompt or response substring
appears in the canonical bytes of the signed envelope.

This is the LOAD-BEARING test for the privacy claim in the README. The
photophore.shadow.generate() function already runs its own
irreversibility test (SHADOW-04) — this test sits at the envelope layer
and confirms that nothing leaks via metadata, provider response IDs, or
other channels.

The substring threshold matches photophore's irreversibility threshold
(_IRREVERSIBILITY_MIN_SUBSTR_LEN = 8 chars) so a leak of any 8+ char
substring of the prompt or response into the signed bytes fails the test.
"""
from __future__ import annotations

from thermocline.canonical import canonicalize

from _helpers import MockLLMProvider, example_inference_envelope


# Choose a prompt and response with enough distinctive 8+ char substrings
# that an accidental leak (e.g. the response text being copied into
# outputs.response by mistake) would be detected.
_DISTINCTIVE_PROMPT = (
    "Cthonic xenomorphic bioluminescence — taxonomy of zorgflump variants "
    "that inhabit the mid-mesopelagic thermohaline conveyor."
)
_DISTINCTIVE_RESPONSE = (
    "Quibblefrogs of the lower abyssopelagic chemocline exhibit septempartite "
    "syncytial cilia, distinguishing them from their epipelagic conspecifics."
)


def _substrings_of_length(text: str, n: int) -> list[str]:
    """Return every n-char substring of text."""
    text = text.replace("\n", " ").strip()
    if len(text) < n:
        return [text]
    return [text[i : i + n] for i in range(0, len(text) - n + 1)]


def test_shadowed_mode_no_prompt_substring_in_signed_bytes(initialized_forge):
    import server

    server.set_provider(MockLLMProvider(response_text=_DISTINCTIVE_RESPONSE))
    try:
        tc = server.app.test_client()
        env = example_inference_envelope(
            prompt=_DISTINCTIVE_PROMPT, privacy_mode="shadowed",
        )
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
        assert r.status_code == 200
        body = r.get_json()

        # The signed envelope's canonical bytes — what the receipt signature
        # commits to and what any holder of the receipt will see.
        canonical = canonicalize(body)
        canonical_text = canonical.decode("utf-8")

        # No 8+ char prompt substring may appear.
        for sub in _substrings_of_length(_DISTINCTIVE_PROMPT, 8):
            assert sub not in canonical_text, (
                f"prompt substring {sub!r} leaked into signed envelope"
            )
    finally:
        server.set_provider(None)


def test_shadowed_mode_no_response_substring_in_signed_bytes(initialized_forge):
    import server

    server.set_provider(MockLLMProvider(response_text=_DISTINCTIVE_RESPONSE))
    try:
        tc = server.app.test_client()
        env = example_inference_envelope(
            prompt=_DISTINCTIVE_PROMPT, privacy_mode="shadowed",
        )
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
        assert r.status_code == 200
        body = r.get_json()

        canonical = canonicalize(body)
        canonical_text = canonical.decode("utf-8")

        for sub in _substrings_of_length(_DISTINCTIVE_RESPONSE, 8):
            assert sub not in canonical_text, (
                f"response substring {sub!r} leaked into signed envelope"
            )
    finally:
        server.set_provider(None)


def test_shadowed_outputs_only_carry_shadow_dicts(initialized_forge):
    import server

    server.set_provider(MockLLMProvider(response_text=_DISTINCTIVE_RESPONSE))
    try:
        tc = server.app.test_client()
        env = example_inference_envelope(
            prompt=_DISTINCTIVE_PROMPT, privacy_mode="shadowed",
        )
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
        body = r.get_json()
        outputs = body["outputs"]
        assert "response" not in outputs
        assert "prompt" not in outputs
        assert "prompt_shadow" in outputs
        assert "response_shadow" in outputs
        for key in ("prompt_shadow", "response_shadow"):
            shadow = outputs[key]
            assert set(shadow.keys()) == {
                "shadow_id", "content_type", "abstraction", "relevance",
            }
            assert shadow["content_type"] == "conversation"
            assert shadow["relevance"] == 0.5
    finally:
        server.set_provider(None)


def test_verbatim_mode_does_leak_response_text(initialized_forge):
    """Negative control: verbatim mode SHOULD include the response text.

    This proves the shadowed-mode tests are actually catching a real
    difference, not just a trivially-passing assertion against an envelope
    that never contained the text in the first place.
    """
    import server

    server.set_provider(MockLLMProvider(response_text=_DISTINCTIVE_RESPONSE))
    try:
        tc = server.app.test_client()
        env = example_inference_envelope(
            prompt=_DISTINCTIVE_PROMPT, privacy_mode="verbatim",
        )
        r = tc.post("/task", json=env, headers={"authorization": "Bearer fake-key"})
        body = r.get_json()
        canonical_text = canonicalize(body).decode("utf-8")
        # In verbatim mode, the response IS present.
        assert _DISTINCTIVE_RESPONSE[:30] in canonical_text
    finally:
        server.set_provider(None)
