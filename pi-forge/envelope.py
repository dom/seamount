"""
envelope.py — Thermocline envelope utilities for pi-forge.

Validates incoming task envelopes and builds outgoing result/error envelopes.
Signature verification/signing is stubbed for key_scheme="none";
replace sign() and verify() with real ed25519 calls for key_scheme="brine".
"""

import uuid
import datetime
from typing import Any, Optional

SUPPORTED_VERSIONS = {"0.3.0"}
SUPPORTED_TASK_TYPES = {"data.compute"}


class EnvelopeError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def validate_task_envelope(body: Any, expected_version: str) -> str:
    """
    Validate a Thermocline task envelope.
    Returns the envelope_id on success.
    Raises EnvelopeError on any validation failure.
    """
    if not isinstance(body, dict):
        raise EnvelopeError("MALFORMED_ENVELOPE", "Envelope must be a JSON object")

    # Version check
    version = body.get("thermocline")
    if not version:
        raise EnvelopeError("MALFORMED_ENVELOPE", "Missing required field: thermocline")
    if version not in SUPPORTED_VERSIONS:
        raise EnvelopeError(
            "UNSUPPORTED_VERSION",
            f"Unsupported Thermocline version: {version!r}. "
            f"Supported: {sorted(SUPPORTED_VERSIONS)}"
        )

    # Envelope type
    if body.get("type") != "task":
        raise EnvelopeError(
            "UNSUPPORTED_TASK_TYPE",
            f"Expected envelope type 'task', got {body.get('type')!r}"
        )

    # Required fields
    for field in ("envelope_id", "issued_at", "issuer"):
        if not body.get(field):
            raise EnvelopeError("MALFORMED_ENVELOPE", f"Missing required field: {field}")

    # Task block
    task = body.get("task")
    if not isinstance(task, dict):
        raise EnvelopeError("MALFORMED_ENVELOPE", "Missing or invalid task block")

    task_type = task.get("type")
    if task_type not in SUPPORTED_TASK_TYPES:
        raise EnvelopeError(
            "UNSUPPORTED_TASK_TYPE",
            f"Unsupported task type: {task_type!r}. "
            f"pi-forge accepts: {sorted(SUPPORTED_TASK_TYPES)}"
        )

    # Signature verification
    sig_block = body.get("dispatch_signature")
    if sig_block:
        scheme = sig_block.get("key_scheme", "none")
        if scheme == "none":
            pass  # No verification for key_scheme: none
        elif scheme == "brine":
            _verify_brine(body, sig_block)
        else:
            raise EnvelopeError(
                "SIGNATURE_INVALID",
                f"Unrecognized key_scheme: {scheme!r}"
            )

    return body["envelope_id"]


def _verify_brine(body: dict, sig_block: dict) -> None:
    """
    Verify an ed25519 (brine) dispatch signature.
    Stub: replace with real cryptographic verification.
    In production, fetch the public key for sig_block["node_id"] from the
    identity provider and verify sig_block["sig"] over the canonical envelope.
    """
    # TODO: implement real brine signature verification
    if not sig_block.get("sig"):
        raise EnvelopeError(
            "SIGNATURE_INVALID",
            "dispatch_signature.sig is empty for key_scheme=brine"
        )


def build_task_result(
    envelope_id: str,
    responder: str,
    key_scheme: str,
    outputs: dict,
    shadows_received: list,
    tiers_present: list,
) -> dict:
    """Build a Thermocline task_result envelope."""
    now = _now()
    result_id = str(uuid.uuid4())

    receipt_sig = _sign_receipt(
        key_scheme=key_scheme,
        responder=responder,
        envelope_id=envelope_id,
        result_id=result_id,
        timestamp=now,
    )

    return {
        "thermocline": "0.3.0",
        "type": "task_result",
        "envelope_id": envelope_id,
        "result_id": result_id,
        "completed_at": now,
        "responder": responder,
        "outputs": outputs,
        "provenance": {
            "shadows_received": shadows_received,
            "tiers_present": tiers_present or [2],
            "local_tiers_present": False,
        },
        "receipt_signature": receipt_sig,
    }


def _sign_receipt(
    key_scheme: str,
    responder: str,
    envelope_id: str,
    result_id: str,
    timestamp: str,
) -> dict:
    """
    Build a receipt_signature block.
    key_scheme="none": sig is null (honest absence of guarantee).
    key_scheme="brine": stub — replace with real ed25519 signing.
    """
    base = {
        "key_scheme": key_scheme,
        "node_id": responder,
        "envelope_id": envelope_id,
        "result_id": result_id,
        "timestamp": timestamp,
    }
    if key_scheme == "none":
        base["sig"] = None
    elif key_scheme == "brine":
        # TODO: sign canonical receipt with private key from identity provider
        base["sig"] = "__brine_sig_stub__"
    else:
        base["sig"] = None
    return base


def build_error_envelope(
    envelope_id: Optional[str],
    code: str,
    message: str,
) -> dict:
    """Build a Thermocline task_error envelope."""
    return {
        "thermocline": "0.3.0",
        "type": "task_error",
        "envelope_id": envelope_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
