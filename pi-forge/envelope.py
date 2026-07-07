"""
envelope.py, Thermocline envelope utilities for pi-forge.

Validates incoming task envelopes and builds outgoing result/error envelopes.
Dispatch-signature verification routes through :func:`thermocline.verify_envelope`
(SP-3.3 wire protocol, thermocline 0.4.0): the envelope is canonicalized with
``dispatch_signature.sig`` reset to the empty string, and ``key_scheme=none``
is refused unless the caller explicitly opts into the unsigned path.

By default (``require_dispatch_sig=True``) any envelope that lacks a verified
brine ``dispatch_signature`` is rejected with ``SIGNATURE_INVALID``. The
verification path is chosen by forge configuration, never by envelope content:
omitting the block or declaring ``key_scheme: none`` does not bypass it.
``require_dispatch_sig=False`` is the explicit dev-mode opt-out (receipt
``sig`` stays ``null`` under ``key_scheme="none"``, honest absence of
guarantee, as shipped since v0.1).
"""

import copy
import uuid
import datetime
from typing import Any, Optional

# Plan-level note (deviation Rule 1): thermocline-py declares
# ``SUPPORTED_VERSIONS = {"0.3.0", "0.3.1"}``. Restricting pi-forge to
# ``{"0.3.1"}`` would break the FORGE-02 regression replay against
# ``examples/task-100-digits.json`` (which declares ``thermocline=0.3.0``).
# We mirror thermocline-py's set so the regression fixture continues to load.
SUPPORTED_VERSIONS = {"0.3.0", "0.3.1"}
SUPPORTED_TASK_TYPES = {"data.compute"}


class EnvelopeError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _clip(value, limit: int = 64) -> str:
    """Repr a caller-supplied value, truncated to a fixed length.

    LOW review fix: error envelopes reflect attacker input (version,
    task type); cap the reflected length so error responses cannot be
    used as an amplification or log-stuffing vector.
    """
    text = repr(value)
    if len(text) > limit:
        text = text[:limit] + "...(truncated)"
    return text


def validate_task_envelope(
    body: Any,
    expected_version: str,
    *,
    keyring_service: Optional[str] = None,
    require_dispatch_sig: bool = True,
) -> str:
    """
    Validate a Thermocline task envelope.
    Returns the envelope_id on success.
    Raises EnvelopeError on any validation failure.

    ``require_dispatch_sig=True`` (the default) refuses any envelope without
    a verified brine ``dispatch_signature`` (SIGNATURE_INVALID, HTTP 401),
    including the ``key_scheme: none`` downgrade. Pass ``False`` only for
    explicit dev-mode forges (``FORGE_KEY_SCHEME=none``).
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
            f"Unsupported Thermocline version: {_clip(version)}. "
            f"Supported: {sorted(SUPPORTED_VERSIONS)}"
        )

    # Envelope type
    if body.get("type") != "task":
        raise EnvelopeError(
            "UNSUPPORTED_TASK_TYPE",
            f"Expected envelope type 'task', got {_clip(body.get('type'))}"
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
            f"Unsupported task type: {_clip(task_type)}. "
            f"pi-forge accepts: {sorted(SUPPORTED_TASK_TYPES)}"
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

    SP-3.3 wire protocol: the verifier canonicalizes the envelope with
    ``dispatch_signature.sig`` reset to ``""`` and checks the ed25519
    signature against the signer's registered public key. The signer's
    public key MUST already be registered with the forge's BrineProvider
    (bootstrap or channel-new TOFU).

    Every failure mode (unsigned scheme, unknown scheme, unregistered
    signer, bad hex, tamper) surfaces as SIGNATURE_INVALID / HTTP 401.
    The error message is intentionally generic: it must not echo
    envelope-supplied content.
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
    """Build a Thermocline task_result envelope.

    The receipt signature is computed over the canonical-JSON of the entire
    result envelope (sans ``receipt_signature.sig``) per DISP-04 / FORGE-01.
    """
    now = _now()
    result_id = str(uuid.uuid4())
    partial_result = {
        "thermocline": "0.3.1",   # THERMO-07: emit the current spec version on new receipts
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
    """Build a receipt_signature block.

    - ``key_scheme="none"``: ``sig`` is ``None`` (honest absence of guarantee).
    - ``key_scheme="brine"``: real ed25519 signature via
      :meth:`BrineProvider.sign`, which internally canonicalizes the envelope
      dict via :func:`thermocline.canonical.canonicalize` (identity.py line 547).
      The caller does NOT pre-canonicalize.
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
