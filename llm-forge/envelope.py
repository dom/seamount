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
    require_dispatch_sig: bool = True,
) -> str:
    """Validate a Thermocline task envelope.

    Returns the envelope_id on success. Raises EnvelopeError on any
    validation failure.

    ``require_dispatch_sig=True`` (the default) refuses any envelope without
    a verified brine ``dispatch_signature`` (SIGNATURE_INVALID, HTTP 401),
    including the ``key_scheme: none`` downgrade. Pass ``False`` only for
    explicit dev-mode forges (``FORGE_KEY_SCHEME=none``).
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

    # Signature verification. The forge's configuration, not the envelope,
    # decides whether a signature is required; envelope content must never
    # select an unauthenticated path.
    sig_block = body.get("dispatch_signature")
    if require_dispatch_sig:
        if not isinstance(sig_block, dict):
            raise EnvelopeError(
                "SIGNATURE_INVALID",
                "dispatch_signature is required by this forge",
                http_status=401,
            )
        # allow_unsigned=False: thermocline raises SchemeError
        # (UNSIGNED_SCHEME_REJECTED) for key_scheme=none, which maps to
        # SIGNATURE_INVALID below. Unknown schemes and tampered or missing
        # signature bytes are refused the same way.
        _verify_dispatch(body, keyring_service=keyring_service)
    elif isinstance(sig_block, dict):
        scheme = sig_block.get("key_scheme", "none")
        if scheme == "none":
            pass  # dev mode only: unsigned accepted when not required
        else:
            _verify_dispatch(body, keyring_service=keyring_service)

    return body["envelope_id"]


def _verify_dispatch(
    body: dict,
    *,
    keyring_service: Optional[str] = None,
) -> None:
    """Verify the dispatch signature via :func:`thermocline.verify_envelope`.

    SP-3.3 wire protocol (thermocline 0.4.0): the verifier canonicalizes the
    envelope with ``dispatch_signature.sig`` reset to ``""`` and checks the
    ed25519 signature against the signer's registered public key.

    Every failure mode (unsigned scheme, unknown scheme, unregistered
    signer, bad hex, tamper) surfaces as SIGNATURE_INVALID / HTTP 401 with
    a generic message that never echoes envelope-supplied content.
    """
    from thermocline import verify_envelope
    from forge_identity import get_verifier

    verifier = get_verifier(keyring_service)
    try:
        receipt = verify_envelope(body, verifier, allow_unsigned=False)
    except Exception as exc:
        raise EnvelopeError(
            "SIGNATURE_INVALID",
            "dispatch_signature verification failed",
            http_status=401,
        ) from exc
    if receipt is None:
        raise EnvelopeError(
            "SIGNATURE_INVALID",
            "dispatch_signature verification failed",
            http_status=401,
        )


def compute_request_digest(
    *,
    model: str,
    messages: list,
    max_tokens: Optional[int],
    temperature: Optional[float],
    privacy_mode: str,
) -> str:
    """Commit the receipt to the exact request the forge relayed.

    SHA-256 over the canonical JSON (thermocline.canonical.canonicalize) of
    the request parameters. Recorded as ``outputs.request_digest`` so the
    receipt signature covers it: without this binding, a signed response
    could be replayed as the answer to a different question.

    Verifiers recompute the digest from the request they dispatched.
    Deterministic and unsalted by design (the caller must be able to verify
    offline); see README for the confirmation-attack caveat this implies for
    receipt handling in shadowed deployments.

    Placement: ``outputs`` rather than ``provenance``, because thermocline's
    provenance model is ``extra="forbid"`` and a new provenance field would
    break ``TaskResult.parse_strict`` for every consumer.
    """
    import hashlib

    from thermocline.canonical import canonicalize

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "privacy_mode": privacy_mode,
    }
    return "sha256:" + hashlib.sha256(canonicalize(payload)).hexdigest()


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
