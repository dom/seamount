"""verify.py — post a task envelope to a running llm-forge and verify the receipt.

End-to-end demo:
  1. GET <forge>/pubkey  → TOFU-pin the forge's brine public key
  2. POST <forge>/task   → receive a signed task_result envelope
  3. Verify the receipt_signature against the pinned pubkey

Usage:
    python examples/verify.py http://127.0.0.1:5101 examples/task-summarize-0g.json
    # auth via env var (NOT recorded in any log line):
    LLM_FORGE_PROVIDER_KEY=sk-... python examples/verify.py ...

This script is the canonical "did the forge produce a valid receipt I can
trust?" check. It does NOT verify LLM correctness or provider trust — the
forge's signature only commits to relay fidelity. See ../README.md
§"What the signature does and does not attest".
"""
from __future__ import annotations

import json
import os
import sys

import httpx

from thermocline.identity import BrineProvider, Signature, Verifier
from thermocline.schemes import KeyScheme


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python verify.py <forge-url> <task-fixture-path>", file=sys.stderr)
        return 2
    forge_url = argv[1].rstrip("/")
    fixture_path = argv[2]

    # 1. Pin the forge's public key (TOFU).
    pub = httpx.get(f"{forge_url}/pubkey", timeout=10).raise_for_status().json()
    print(f"pinned pubkey: identity={pub['identity']!r} scheme={pub['key_scheme']!r}")
    print(f"               pubkey={pub['pubkey']}")

    # 2. Post the task envelope.
    with open(fixture_path) as f:
        envelope = json.load(f)
    api_key = os.environ.get("LLM_FORGE_PROVIDER_KEY", "")
    if not api_key:
        print("ERROR: set LLM_FORGE_PROVIDER_KEY env var (BYOK).", file=sys.stderr)
        return 2
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {api_key}",
    }
    resp = httpx.post(f"{forge_url}/task", json=envelope, headers=headers, timeout=120)
    if resp.status_code != 200:
        print(f"ERROR: /task returned {resp.status_code}: {resp.text}", file=sys.stderr)
        return 3
    result = resp.json()

    # 3. Verify the receipt_signature against the pinned pubkey.
    rs = result.get("receipt_signature") or {}
    if rs.get("key_scheme") != "brine":
        print(f"ERROR: receipt is not brine-signed (got {rs.get('key_scheme')!r})", file=sys.stderr)
        return 4
    sig_hex = rs.get("sig") or ""
    if not sig_hex:
        print("ERROR: receipt_signature.sig is empty", file=sys.stderr)
        return 4

    # Register the pinned pubkey under the forge's identity so the Verifier
    # can resolve it. Uses an in-process BrineProvider with a throwaway
    # keyring namespace.
    import uuid as _uuid
    scratch_ns = f"verify-scratch-{_uuid.uuid4()}"
    provider = BrineProvider(keyring_service=scratch_ns)
    provider.register_public_key(
        identity=pub["identity"], verify_key=bytes.fromhex(pub["pubkey"]),
    )
    verifier = Verifier()
    verifier.register(provider)

    # Reconstruct the signing input: the receipt envelope with sig set to None.
    envelope_for_verify = json.loads(json.dumps(result))
    envelope_for_verify["receipt_signature"]["sig"] = None
    sig = Signature(
        scheme=KeyScheme.BRINE,
        bytes_=bytes.fromhex(sig_hex),
        signer_identity=pub["identity"],
    )
    try:
        receipt = verifier.verify(envelope=envelope_for_verify, signature=sig)
    except Exception as exc:
        print(f"ERROR: receipt verification failed: {exc}", file=sys.stderr)
        return 5

    privacy_mode = envelope["task"]["parameters"].get("privacy_mode", "verbatim")
    outputs = result.get("outputs", {})
    print(f"OK — receipt verified (envelope_id={result.get('envelope_id')})")
    print(f"     privacy_mode={privacy_mode}")
    print(f"     provider={outputs.get('provider')!r}")
    print(f"     model={outputs.get('model')!r}")
    print(f"     tokens_in={outputs.get('tokens_in')} tokens_out={outputs.get('tokens_out')}")
    if privacy_mode == "verbatim":
        snippet = (outputs.get("response") or "")[:120].replace("\n", " ")
        print(f"     response[:120]: {snippet!r}")
    else:
        prompt_sh = outputs.get("prompt_shadow", {})
        resp_sh = outputs.get("response_shadow", {})
        print(f"     prompt_shadow:   {prompt_sh.get('abstraction')!r}")
        print(f"     response_shadow: {resp_sh.get('abstraction')!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
