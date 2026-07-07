"""
llm-forge — Thermocline-compliant reference forge for OpenAI-compatible inference.

Wraps a chat-completion call to any OpenAI-compatible endpoint (0G Private
Computer, OpenAI, OpenRouter, vLLM, ...) and returns a brine-signed
Thermocline task_result envelope around the response.

Wire shape:
    POST /task     -> task_result envelope (or task_error)
    GET  /pubkey   -> {"identity": ..., "key_scheme": "brine", "pubkey": <hex>}
    GET  /health   -> liveness + config snapshot
    GET  /models   -> the configured backend's catalog (operator-supplied)

Env vars:
    FORGE_NODE_ID              (default "llm-forge-local")
    FORGE_KEY_SCHEME           (default "brine"; "none" disables signing)
    FORGE_PORT                 (default 5101)
    FORGE_BIND_HOST            (default 127.0.0.1)
    LLMFORGE_KEYRING_SERVICE   (default "seamount.llmforge")
    LLMFORGE_IDENTITY          (default "llm-forge")
    LLM_FORGE_BASE_URL         (e.g. https://pc.0g.ai/api/v1, https://api.openai.com/v1)
    LLM_FORGE_PROVIDER_LABEL   (e.g. "0g-pc", "openai") — recorded in outputs.provider
    LLM_FORGE_MODELS_JSON      (optional JSON list shown by /models)
    LLM_FORGE_ATTESTATION_JSON (optional JSON object appended to outputs.provider_attestation)

Receipt-signature semantics (LOAD-BEARING — see README):
    The brine signature attests RELAY FIDELITY ("I forwarded these messages
    to provider X and received this verbatim response"), NOT LLM correctness
    or provider trustworthiness.
"""
import json
import os

from flask import Flask, request, jsonify

from envelope import (
    EnvelopeError,
    build_error_envelope,
    build_task_result,
    validate_task_envelope,
)
from forge_identity import (
    FORGE_IDENTITY,
    FORGE_KEYRING_SERVICE,
    get_provider,
)
from providers import OpenAICompatibleProvider
from shadows import shadow_messages, shadow_response, shadow_to_dict

app = Flask(__name__)

# FORGE_NODE_ID is the responder identity stamped on receipts AND the
# keystore-lookup key when signing. It MUST match LLMFORGE_IDENTITY so the
# signing path can find the keypair generated under that identity. Default
# to LLMFORGE_IDENTITY (default "llm-forge") so init+serve with no env
# overrides works out of the box.
FORGE_NODE_ID = os.environ.get("FORGE_NODE_ID") or os.environ.get(
    "LLMFORGE_IDENTITY", "llm-forge"
)
FORGE_KEY_SCHEME = os.environ.get("FORGE_KEY_SCHEME", "brine")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# HIGH-severity review fix: a forge keyed for brine REQUIRES a verified brine
# dispatch_signature on every envelope. Envelope content (missing block,
# key_scheme=none) can no longer select an unauthenticated path. Explicit
# FORGE_REQUIRE_DISPATCH_SIG=0 is the dev-mode opt-out.
FORGE_REQUIRE_DISPATCH_SIG = _env_flag(
    "FORGE_REQUIRE_DISPATCH_SIG", FORGE_KEY_SCHEME == "brine"
)
FORGE_PORT = int(os.environ.get("FORGE_PORT", "5101"))
THERMOCLINE_VERSION = "0.3.1"


def _current_keyring_service() -> str:
    return os.environ.get("LLMFORGE_KEYRING_SERVICE", FORGE_KEYRING_SERVICE)


def _current_identity() -> str:
    return os.environ.get("LLMFORGE_IDENTITY", FORGE_IDENTITY)


def _current_base_url() -> str:
    return os.environ.get("LLM_FORGE_BASE_URL", "")


def _current_provider_label() -> str:
    return os.environ.get("LLM_FORGE_PROVIDER_LABEL", "unknown")


def _current_models() -> list:
    raw = os.environ.get("LLM_FORGE_MODELS_JSON", "")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _current_attestation() -> dict | None:
    raw = os.environ.get("LLM_FORGE_ATTESTATION_JSON", "")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


# Indirection so tests can inject a MockLLMProvider without monkeypatching
# httpx. Default factory builds the configured OpenAI-compatible client.
def _build_provider():
    base_url = _current_base_url()
    if not base_url:
        return None
    return OpenAICompatibleProvider(base_url=base_url)


# Test-injection seam: assign a provider to override _build_provider().
_provider_override = None


def set_provider(provider) -> None:
    """Override the provider factory (test fixtures use this)."""
    global _provider_override
    _provider_override = provider


def _resolve_provider():
    return _provider_override if _provider_override is not None else _build_provider()


@app.post("/task")
def handle_task():
    if not request.is_json:
        return jsonify(build_error_envelope(
            None, "MALFORMED_ENVELOPE",
            "Content-Type must be application/json",
        )), 415

    try:
        body = request.get_json(force=True)
    except Exception:
        return jsonify(build_error_envelope(
            None, "MALFORMED_ENVELOPE",
            "Request body is not valid JSON",
        )), 400

    service = _current_keyring_service()

    try:
        envelope_id = validate_task_envelope(
            body,
            THERMOCLINE_VERSION,
            keyring_service=service,
            require_dispatch_sig=FORGE_REQUIRE_DISPATCH_SIG,
        )
    except EnvelopeError as e:
        return jsonify(build_error_envelope(
            body.get("envelope_id") if isinstance(body, dict) else None,
            e.code, e.message,
        )), e.http_status

    params = body.get("task", {}).get("parameters", {})
    model = params.get("model")
    messages = params.get("messages")
    max_tokens = params.get("max_tokens")
    temperature = params.get("temperature")
    privacy_mode = params.get("privacy_mode", "verbatim")

    if not isinstance(model, str) or not model:
        return jsonify(build_error_envelope(
            envelope_id, "INVALID_PARAMETERS",
            "Missing required parameter: model (string)",
        )), 422
    if not isinstance(messages, list) or not messages:
        return jsonify(build_error_envelope(
            envelope_id, "INVALID_PARAMETERS",
            "Missing required parameter: messages (non-empty list)",
        )), 422
    if privacy_mode not in ("verbatim", "shadowed"):
        return jsonify(build_error_envelope(
            envelope_id, "INVALID_PARAMETERS",
            f"privacy_mode must be 'verbatim' or 'shadowed', got {privacy_mode!r}",
        )), 422

    # BYOK: the caller's Authorization header carries the provider key. The
    # forge never persists it; httpx forwards it on the upstream POST and the
    # local string goes out of scope when this request returns.
    auth_header = request.headers.get("authorization") or ""
    if not auth_header.lower().startswith("bearer "):
        return jsonify(build_error_envelope(
            envelope_id, "MISSING_PROVIDER_AUTH",
            "llm-forge requires Authorization: Bearer <provider-api-key> "
            "(BYOK — forge never persists keys)",
        )), 401
    api_key = auth_header.split(" ", 1)[1].strip()

    provider = _resolve_provider()
    if provider is None:
        return jsonify(build_error_envelope(
            envelope_id, "FORGE_MISCONFIGURED",
            "LLM_FORGE_BASE_URL not set; cannot reach an upstream provider",
        )), 503

    try:
        result = provider.complete(
            model=model,
            messages=messages,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as exc:
        return jsonify(build_error_envelope(
            envelope_id, "UPSTREAM_PROVIDER_ERROR",
            f"upstream provider call failed: {exc}",
        )), 502

    # Build outputs per the privacy mode the caller selected.
    outputs: dict = {
        "model": result.model,
        "finish_reason": result.finish_reason,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "provider": _current_provider_label(),
        "provider_request_id": result.provider_request_id,
    }
    attestation = _current_attestation()
    if attestation is not None:
        outputs["provider_attestation"] = attestation

    if privacy_mode == "verbatim":
        outputs["response"] = result.response_text
    else:  # shadowed
        # SHADOW-04: ShadowIrreversibilityError aborts dispatch — bubbles up
        # as 500 via Flask, which is correct (privacy invariant violated;
        # caller MUST NOT receive any envelope).
        outputs["prompt_shadow"] = shadow_to_dict(shadow_messages(messages))
        outputs["response_shadow"] = shadow_to_dict(shadow_response(result.response_text))

    receipt = build_task_result(
        envelope_id=envelope_id,
        responder=FORGE_NODE_ID,
        key_scheme=FORGE_KEY_SCHEME,
        outputs=outputs,
        shadows_received=[
            s["shadow"]["shadow_id"]
            for c in body.get("context", [])
            if c.get("tier") == 1 and "shadow" in c
            for s in [c]
        ],
        tiers_present=sorted({c.get("tier") for c in body.get("context", []) if "tier" in c}),
        keyring_service=service,
    )
    return jsonify(receipt), 200


@app.get("/pubkey")
def pubkey():
    """TOFU bootstrap. Returns the forge's identity + ed25519 verify key."""
    service = _current_keyring_service()
    identity = _current_identity()
    provider = get_provider(service)
    try:
        pub_bytes = provider.public_key(identity=identity)
    except Exception as exc:
        return jsonify({
            "error": "FORGE_NOT_INITIALIZED",
            "message": f"forge keypair not found; run `llm-forge init` first: {exc}",
        }), 503
    return jsonify({
        "identity": identity,
        "key_scheme": "brine",
        "pubkey": pub_bytes.hex(),
    }), 200


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "forge": "llm-forge",
        "thermocline_version": THERMOCLINE_VERSION,
        "node_id": FORGE_NODE_ID,
        "key_scheme": FORGE_KEY_SCHEME,
        "require_dispatch_sig": FORGE_REQUIRE_DISPATCH_SIG,
        "provider_label": _current_provider_label(),
        "base_url_configured": bool(_current_base_url()),
    })


@app.get("/models")
def models():
    """Return the operator-configured model catalog (LLM_FORGE_MODELS_JSON).

    Per-forge documentation: llm-forge does NOT auto-probe upstream `/models`
    because that would require auth and would couple the response to a
    specific provider's CLI. Operators publish what they expose.
    """
    return jsonify({"models": _current_models()})


if __name__ == "__main__":
    print(f"llm-forge listening on 127.0.0.1:{FORGE_PORT}")
    print(f"  node_id        : {FORGE_NODE_ID}")
    print(f"  key_scheme     : {FORGE_KEY_SCHEME}")
    print(f"  provider_label : {_current_provider_label()}")
    print(f"  base_url       : {_current_base_url() or '(unset)'}")
    app.run(host=os.environ.get("FORGE_BIND_HOST", "127.0.0.1"), port=FORGE_PORT)
