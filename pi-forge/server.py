"""
pi-forge — Thermocline-compliant reference forge.

Computes pi to N digits (1-999) from a Thermocline task envelope. Real
ed25519 brine sign/verify via thermocline-py since v0.1.1; the previous
``__brine_sig_stub__`` and ``TODO: implement real brine`` paths are retired
in envelope.py.

Wire shape:
    POST /task     -> task_result envelope (or task_error)
    GET  /pubkey   -> {"identity": <FORGE_IDENTITY>, "key_scheme": "brine",
                       "pubkey": <hex>}   (D-01 bootstrap)
    GET  /health   -> liveness + config snapshot

Env vars:
    FORGE_NODE_ID          (default "pi-forge-local")
    FORGE_KEY_SCHEME       (default "brine"; FORGE_KEY_SCHEME=none retains
                            dev-mode behavior with null sigs)
    FORGE_PORT             (default 5100)
    PIFORGE_KEYRING_SERVICE (default "seamount.piforge")
    PIFORGE_IDENTITY        (default "pi-forge")
"""

import os
from flask import Flask, request, jsonify

from pi import compute_pi
from envelope import (
    validate_task_envelope,
    build_task_result,
    build_error_envelope,
    EnvelopeError,
)
from forge_identity import (
    FORGE_KEYRING_SERVICE,
    FORGE_IDENTITY,
    get_provider,
)

app = Flask(__name__)

FORGE_NODE_ID = os.environ.get("FORGE_NODE_ID", "pi-forge-local")
# CONTEXT D-01: default flipped from "none" -> "brine". FORGE_KEY_SCHEME=none
# is still supported for dev/regression replay (envelope.py's _sign_receipt
# leaves sig=None in that mode).
FORGE_KEY_SCHEME = os.environ.get("FORGE_KEY_SCHEME", "brine")
FORGE_PORT = int(os.environ.get("FORGE_PORT", "5100"))
MAX_DIGITS = 999
THERMOCLINE_VERSION = "0.3.1"


def _current_keyring_service() -> str:
    """Read PIFORGE_KEYRING_SERVICE each call so test fixtures can swap it."""
    return os.environ.get("PIFORGE_KEYRING_SERVICE", FORGE_KEYRING_SERVICE)


def _current_identity() -> str:
    return os.environ.get("PIFORGE_IDENTITY", FORGE_IDENTITY)


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

    # Validate envelope structure (verifies dispatch_signature when present).
    try:
        envelope_id = validate_task_envelope(
            body, THERMOCLINE_VERSION, keyring_service=service
        )
    except EnvelopeError as e:
        return jsonify(build_error_envelope(
            body.get("envelope_id"), e.code, e.message
        )), e.http_status

    # Extract and validate parameters.
    params = body.get("task", {}).get("parameters", {})
    digits = params.get("digits")

    if digits is None:
        return jsonify(build_error_envelope(
            envelope_id, "INVALID_PARAMETERS",
            "Missing required parameter: digits"
        )), 422

    if not isinstance(digits, int) or isinstance(digits, bool):
        return jsonify(build_error_envelope(
            envelope_id, "INVALID_PARAMETERS",
            "digits must be an integer"
        )), 422

    if not (1 <= digits <= MAX_DIGITS):
        return jsonify(build_error_envelope(
            envelope_id, "INVALID_PARAMETERS",
            f"digits must be between 1 and {MAX_DIGITS}"
        )), 422

    pi_str = compute_pi(digits)

    outputs = {
        "pi": pi_str,
        "digits_computed": digits,
        "algorithm": "mpmath",
    }

    result = build_task_result(
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

    return jsonify(result), 200


@app.get("/pubkey")
def pubkey():
    """D-01 bootstrap endpoint. Returns the forge's identity + Ed25519 verify key.

    Sovereign nodes consume this on ``channel new`` to register the forge
    identity in their own trust store (TOFU). NEVER returns private key
    material. Returns 503 if the forge keypair has not been initialized.
    """
    service = _current_keyring_service()
    identity = _current_identity()
    provider = get_provider(service)
    try:
        pub_bytes = provider.public_key(identity=identity)
    except Exception as exc:
        return jsonify({
            "error": "FORGE_NOT_INITIALIZED",
            "message": f"forge keypair not found; run `pi-forge init` first: {exc}",
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
        "forge": "pi-forge",
        "thermocline_version": THERMOCLINE_VERSION,
        "node_id": FORGE_NODE_ID,
        "key_scheme": FORGE_KEY_SCHEME,
        "max_digits": MAX_DIGITS,
    })


if __name__ == "__main__":
    print(f"pi-forge listening on 127.0.0.1:{FORGE_PORT}")
    print(f"  node_id    : {FORGE_NODE_ID}")
    print(f"  key_scheme : {FORGE_KEY_SCHEME}")
    app.run(host="0.0.0.0", port=FORGE_PORT)
