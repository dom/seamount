"""envelope.py — Thermocline envelope utilities for llm-forge.

Validates incoming task envelopes (data.inference.text only) and builds
outgoing task_result/task_error envelopes. Real ed25519 brine sign+verify
via :mod:`thermocline.identity`; canonical-JSON signing via
:func:`thermocline.canonical.canonicalize` (called transitively by
BrineProvider.sign).

llm-forge differs from pi-forge in two ways:
  * accepted task type is ``data.inference.text`` (not ``data.compute``)
  * receipt outputs carry relay metadata (provider, provider_request_id,
    provider_attestation) alongside the model response

Receipt signature semantics (LOAD-BEARING): the brine signature attests
*relay fidelity* — that this specific forge forwarded the request to the
configured provider and received this verbatim response. It does NOT attest
LLM output correctness or provider trustworthiness. See README §"What the
signature does and does not attest".
"""
from __future__ import annotations

import copy
import datetime
import uuid
from typing import Any, Optional

# Mirror pi-forge's supported-version set so existing test fixtures load.
SUPPORTED_VERSIONS = {"0.3.0", "0.3.1"}
SUPPORTED_TASK_TYPES = {"data.inference.text"}


class EnvelopeError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def validate_task_envelope(
    body: Any,
    expected_version: str,
    *,
    keyring_service: Optional[str] = None,
) -> str:
    """Validate a Thermocline task envelope.

    Returns the envelope_id on success. Raises EnvelopeError on any
    validation failure.
    """
    if not isinstance(body, dict):
        raise EnvelopeError("MALFORMED_ENVELOPE", "Envelope must be a JSON object")

    version = body.get("thermocline")
    if not version:
        raise EnvelopeError("MALFORMED_ENVELOPE", "Missing required field: thermocline")
    if version not in SUPPORTED_VERSIONS:
        raise EnvelopeError(
            "UNSUPPORTED_VERSION",
            f"Unsupported Thermocline version: {version!r}. "
            f"Supported: {sorted(SUPPORTED_VERSIONS)}",
        )

    if body.get("type") != "task":
        raise EnvelopeError(
            "UNSUPPORTED_TASK_TYPE",
            f"Expected envelope type 'task', got {body.get('type')!r}",
        )

    for field in ("envelope_id", "issued_at", "issuer"):
        if not body.get(field):
            raise EnvelopeError("MALFORMED_ENVELOPE", f"Missing required field: {field}")

    task = body.get("task")
    if not isinstance(task, dict):
        raise EnvelopeError("MALFORMED_ENVELOPE", "Missing or invalid task block")

    task_type = task.get("type")
    if task_type not in SUPPORTED_TASK_TYPES:
        raise EnvelopeError(
            "UNSUPPORTED_TASK_TYPE",
            f"Unsupported task type: {task_type!r}. "
            f"llm-forge accepts: {sorted(SUPPORTED_TASK_TYPES)}",
        )

    sig_block = body.get("dispatch_signature")
    if sig_block:
        scheme = sig_block.get("key_scheme", "none")
        if scheme == "none":
            pass
        elif scheme == "brine":
            _verify_brine(body, sig_block, keyring_service=keyring_service)
        else:
            raise EnvelopeError(
                "SIGNATURE_INVALID",
                f"Unrecognized key_scheme: {scheme!r}",
            )

    return body["envelope_id"]


def _verify_brine(
    body: dict,
    sig_block: dict,
    *,
    keyring_service: Optional[str] = None,
) -> None:
    """Verify an ed25519 (brine) dispatch signature via thermocline.identity."""
    from thermocline.identity import Signature
    from thermocline.schemes import KeyScheme
    from forge_identity import get_verifier

    node_id = sig_block.get("node_id") or sig_block.get("signer_identity") or ""
    sig_hex = sig_block.get("sig") or sig_block.get("bytes_hex") or ""
    if not sig_hex:
        raise EnvelopeError(
            "SIGNATURE_INVALID",
            "dispatch_signature.sig is empty for key_scheme=brine",
            http_status=401,
        )
    try:
        sig_bytes = bytes.fromhex(sig_hex)
    except (TypeError, ValueError) as exc:
        raise EnvelopeError(
            "SIGNATURE_INVALID",
            f"dispatch_signature.sig is not valid hex: {exc}",
            http_status=401,
        ) from exc
    sig = Signature(
        scheme=KeyScheme.BRINE,
        bytes_=sig_bytes,
        signer_identity=node_id,
    )
    verifier = get_verifier(keyring_service)
    body_for_verify = copy.deepcopy(body)
    sig_block_for_verify = body_for_verify.get("dispatch_signature")
    if isinstance(sig_block_for_verify, dict):
        sig_block_for_verify.pop("sig", None)
        sig_block_for_verify.pop("bytes_hex", None)
    try:
        receipt = verifier.verify(envelope=body_for_verify, signature=sig)
    except Exception as exc:
        raise EnvelopeError(
            "SIGNATURE_INVALID",
            f"dispatch_signature verification failed: {exc}",
            http_status=401,
        ) from exc
    if receipt is None:
        raise EnvelopeError(
            "SIGNATURE_INVALID",
            "dispatch_signature verification failed",
            http_status=401,
        )


def build_task_result(
    envelope_id: str,
    responder: str,
    key_scheme: str,
    outputs: dict,
    shadows_received: list,
    tiers_present: list,
    *,
    keyring_service: Optional[str] = None,
) -> dict:
    """Build a Thermocline task_result envelope and sign the receipt.

    The receipt signature is computed over the canonical-JSON of the entire
    result envelope (with ``receipt_signature.sig`` set to None) per DISP-04
    / FORGE-01.
    """
    now = _now()
    result_id = str(uuid.uuid4())
    partial_result = {
        "thermocline": "0.3.1",
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
    }
    receipt_sig = _sign_receipt(
        key_scheme=key_scheme,
        responder=responder,
        envelope_id=envelope_id,
        result_id=result_id,
        timestamp=now,
        result_envelope_for_signing={
            **partial_result,
            "receipt_signature": {
                "key_scheme": key_scheme,
                "node_id": responder,
                "envelope_id": envelope_id,
                "result_id": result_id,
                "timestamp": now,
                "sig": None,
            },
        },
        keyring_service=keyring_service,
    )
    partial_result["receipt_signature"] = receipt_sig
    return partial_result


def _sign_receipt(
    *,
    key_scheme: str,
    responder: str,
    envelope_id: str,
    result_id: str,
    timestamp: str,
    result_envelope_for_signing: Optional[dict] = None,
    keyring_service: Optional[str] = None,
) -> dict:
    base = {
        "key_scheme": key_scheme,
        "node_id": responder,
        "envelope_id": envelope_id,
        "result_id": result_id,
        "timestamp": timestamp,
    }
    if key_scheme == "none":
        base["sig"] = None
        return base
    if key_scheme != "brine":
        base["sig"] = None
        return base

    from forge_identity import get_provider

    provider = get_provider(keyring_service)
    if result_envelope_for_signing is None:
        signing_input_obj = dict(base)
        signing_input_obj["sig"] = None
    else:
        signing_input_obj = copy.deepcopy(result_envelope_for_signing)
        rs = signing_input_obj.get("receipt_signature")
        if isinstance(rs, dict):
            rs["sig"] = None

    sig = provider.sign(envelope=signing_input_obj, signer_identity=responder)
    base["sig"] = sig.bytes_.hex()
    return base


def build_error_envelope(
    envelope_id: Optional[str],
    code: str,
    message: str,
) -> dict:
    """Build a Thermocline task_error envelope."""
    return {
        "thermocline": "0.3.1",
        "type": "task_error",
        "envelope_id": envelope_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
