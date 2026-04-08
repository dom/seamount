"""
pi-forge — Thermocline-compliant reference forge
Computes π to N digits (1–999) from a Thermocline task envelope.
"""

import os
import json
import uuid
import datetime
from flask import Flask, request, jsonify

from pi import compute_pi
from envelope import (
    validate_task_envelope,
    build_task_result,
    build_error_envelope,
    EnvelopeError,
)

app = Flask(__name__)

FORGE_NODE_ID = os.environ.get("FORGE_NODE_ID", "pi-forge-local")
FORGE_KEY_SCHEME = os.environ.get("FORGE_KEY_SCHEME", "none")
FORGE_PORT = int(os.environ.get("FORGE_PORT", "5100"))
MAX_DIGITS = 999
THERMOCLINE_VERSION = "0.3.0"


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

    # ── Validate envelope structure ──────────────────────────────────────
    try:
        envelope_id = validate_task_envelope(body, THERMOCLINE_VERSION)
    except EnvelopeError as e:
        return jsonify(build_error_envelope(
            body.get("envelope_id"), e.code, e.message
        )), e.http_status

    # ── Extract and validate parameters ─────────────────────────────────
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

    # ── Compute ──────────────────────────────────────────────────────────
    pi_str = compute_pi(digits)

    # ── Build result ─────────────────────────────────────────────────────
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
    )

    return jsonify(result), 200


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
