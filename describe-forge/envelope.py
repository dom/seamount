"""describe-forge envelope handling — adapted from pi-forge post-FORGE-01 upgrade.

Key differences from pi-forge envelope.py:
- ``SUPPORTED_TASK_TYPES = {"shadow.describe", "data.compute"}``: both shapes
  are accepted; conformance can narrow this if cross-impl runs surface only
  one (per 03-RESEARCH cross-impl spec-patch pattern).
- ``build_task_result`` builds the describe-forge response shape:
  ``outputs = {"descriptions": [...], "note": <str or None>}``.
- Mandatory-shadow check lives on the server side (see server.py); envelope.py
  only validates schema shape.

Real ed25519 brine sign/verify via thermocline-py; canonical-JSON signing input
via thermocline.canonical.canonicalize. No stubs; non-canonical JSON is never
used in the signing path (DISP-04 invariant).
"""

import copy
import datetime
import uuid
from typing import Any, Optional

SUPPORTED_VERSIONS = {"0.3.0", "0.3.1"}
SUPPORTED_TASK_TYPES = {"shadow.describe", "data.compute"}


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

    Returns the envelope_id on success. Validates per-shadow well-formedness
    for any tier-1 shadow blocks present: missing shadow_id / content_type /
    relevance fields raise MALFORMED_ENVELOPE.

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
            f"Supported: {sorted(SUPPORTED_VERSIONS)}"
        )

    if body.get("type") != "task":
        raise EnvelopeError(
            "UNSUPPORTED_TASK_TYPE",
            f"Expected envelope type 'task', got {body.get('type')!r}"
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
            f"describe-forge accepts: {sorted(SUPPORTED_TASK_TYPES)}"
        )

    # Validate shadow blocks (any tier-1 block with a 'shadow' dict must have
    # the required fields; missing fields surface as MALFORMED_ENVELOPE).
    context = body.get("context", []) or []
    if not isinstance(context, list):
        raise EnvelopeError("MALFORMED_ENVELOPE", "context must be a list")
    for idx, block in enumerate(context):
        if not isinstance(block, dict):
            continue
        if block.get("tier") == 1 and isinstance(block.get("shadow"), dict):
            shadow = block["shadow"]
            for required in ("shadow_id", "content_type", "relevance"):
                if required not in shadow:
                    raise EnvelopeError(
                        "MALFORMED_ENVELOPE",
                        f"context[{idx}].shadow missing required field: {required!r}",
                    )

    # Dispatch signature verification. The forge's configuration, not the
    # envelope, decides whether a signature is required; envelope content
    # must never select an unauthenticated path.
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


def build_task_result(
    *,
    envelope_id: str,
    responder: str,
    key_scheme: str,
    descriptions: list,
    note: Optional[str],
    tiers_present: list,
    keyring_service: Optional[str] = None,
) -> dict:
    """Build the describe-forge task_result envelope.

    Output shape:
        outputs = {
            "descriptions": [<ShadowDescription>, ...],
            "note": <str or None>,
        }
    Where ShadowDescription is the dict returned by describe.describe_one_shadow.

    provenance.local_tiers_present is always False (tier-0 never crosses the
    wire per Photophore privacy contract — invariant Test 6 of Task 3 plan).
    """
    now = _now()
    result_id = str(uuid.uuid4())
    outputs = {
        "descriptions": descriptions,
        "note": note,
    }
    partial_result = {
        "thermocline": "0.3.1",
        "type": "task_result",
        "envelope_id": envelope_id,
        "result_id": result_id,
        "completed_at": now,
        "responder": responder,
        "outputs": outputs,
        "provenance": {
            "shadows_received": [d["shadow_id"] for d in descriptions],
            "tiers_present": tiers_present,
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
    """Build a receipt_signature block via BrineProvider.sign over canonical-JSON."""
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
