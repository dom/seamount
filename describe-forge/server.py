"""describe-forge — Thermocline-compliant reference forge for tier-1 shadows.

Wire shape:
    POST /task    -> task_result with outputs.descriptions + optional outputs.note
    GET  /pubkey  -> {identity, key_scheme: "brine", pubkey: <hex>}
    GET  /health  -> liveness

Hard requirement (D-02): the task envelope MUST carry at least one tier-1
shadow in context[]. A zero-shadow envelope (including context=[]) is refused
with UNSUPPORTED_TASK_TYPE / HTTP 400.

Mixed-tier privacy invariant (T-03-11): inline tier-2/3 content blocks are
COUNTED for the optional outputs.note field but never read; the response body
NEVER contains content from non-shadow blocks. The regression test
test_mixed_tier_ignore_inline.py plants a magic string and asserts absence.
"""
import os
from flask import Flask, request, jsonify

from envelope import (
    validate_task_envelope,
    build_task_result,
    build_error_envelope,
    EnvelopeError,
)
from describe import (
    filter_tier1_shadows,
    describe_shadows,
    collect_tiers_present,
)
from forge_identity import (
    FORGE_IDENTITY,
    FORGE_KEYRING_SERVICE,
    get_provider,
)

app = Flask(__name__)

FORGE_NODE_ID = os.environ.get("FORGE_NODE_ID", "describe-forge-local")
FORGE_KEY_SCHEME = os.environ.get("FORGE_KEY_SCHEME", "brine")
FORGE_PORT = int(os.environ.get("FORGE_PORT", "5200"))
THERMOCLINE_VERSION = "0.3.1"


def _current_keyring_service() -> str:
    return os.environ.get("DESCRIBEFORGE_KEYRING_SERVICE", FORGE_KEYRING_SERVICE)


def _current_identity() -> str:
    return os.environ.get("DESCRIBEFORGE_IDENTITY", FORGE_IDENTITY)


@app.post("/task")
def handle_task():
    if not request.is_json:
        return jsonify(build_error_envelope(None, "MALFORMED_ENVELOPE",
                                            "Content-Type must be application/json")), 415
    try:
        body = request.get_json(force=True)
    except Exception:
        return jsonify(build_error_envelope(None, "MALFORMED_ENVELOPE",
                                            "Request body is not valid JSON")), 400

    service = _current_keyring_service()
    try:
        envelope_id = validate_task_envelope(
            body, THERMOCLINE_VERSION, keyring_service=service
        )
    except EnvelopeError as e:
        return jsonify(build_error_envelope(
            body.get("envelope_id"), e.code, e.message
        )), e.http_status

    context = body.get("context", []) or []
    shadows = filter_tier1_shadows(context)
    if not shadows:
        return jsonify(build_error_envelope(
            envelope_id, "UNSUPPORTED_TASK_TYPE",
            "describe-forge requires at least one tier-1 shadow in context[]"
        )), 400

    descriptions, ignored = describe_shadows(context)
    tiers_present = collect_tiers_present(context)
    note = (
        f"describe-forge operated on {len(descriptions)} shadows; "
        f"{ignored} inline blocks ignored"
        if ignored > 0
        else None
    )
    result = build_task_result(
        envelope_id=envelope_id,
        responder=FORGE_NODE_ID,
        key_scheme=FORGE_KEY_SCHEME,
        descriptions=descriptions,
        note=note,
        tiers_present=tiers_present,
        keyring_service=service,
    )
    return jsonify(result), 200


@app.get("/pubkey")
def pubkey():
    """D-01 bootstrap endpoint. Returns the forge's identity + Ed25519 verify key."""
    service = _current_keyring_service()
    identity = _current_identity()
    provider = get_provider(service)
    try:
        pub_bytes = provider.public_key(identity=identity)
    except Exception as exc:
        return jsonify({
            "error": "FORGE_NOT_INITIALIZED",
            "message": f"forge keypair not found; run `describe-forge init`: {exc}",
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
        "forge": "describe-forge",
        "thermocline_version": THERMOCLINE_VERSION,
        "node_id": FORGE_NODE_ID,
        "key_scheme": FORGE_KEY_SCHEME,
    })


if __name__ == "__main__":
    print(f"describe-forge listening on 127.0.0.1:{FORGE_PORT}")
    print(f"  node_id    : {FORGE_NODE_ID}")
    print(f"  key_scheme : {FORGE_KEY_SCHEME}")
    app.run(host="0.0.0.0", port=FORGE_PORT)
