"""Core harness: POST fixtures, validate response JSON Schema, verify signatures.

Runs the Seamount 13-item conformance checklist against a live forge URL.
Items 1-8 cover the §"Forge Conformance Requirements" surface; items
AT-E1..AT-E5 cover the §"Attack Surfaces and Mitigations" register.

Hardening (review follow-up):

* Items 1, 2, and 7 are REQUIRED: they can never silently skip. If a
  required item cannot be exercised, it is reported as FAIL with a reason.
* Item 2 runs three LIVE negative cases against the forge (missing
  ``dispatch_signature``, ``key_scheme=none`` downgrade, tampered brine
  signature); all three must be rejected with ``SIGNATURE_INVALID``.
  The tampered case is self-hosted (sign-then-flip-a-byte, or a garbage
  signature when no signing keypair is available), so it never depends on
  an external fixture corpus.
* Items 5 and 8 assert the exact error codes for unknown task types and
  unsupported versions; AT-E1 (malformed payload) and AT-E2 (oversized
  payload) run live instead of auto-skipping.

Positive-path items need envelopes the forge will accept. Since the HIGH
hardening fix, a default-configured forge REQUIRES a verified brine
dispatch signature, so the harness can be given ``sovereign_service``: the
forge's keystore namespace, into which the harness registers an ephemeral
sovereign verify key it then signs fixtures with (SP-3.3, thermocline
0.4.0). Without it, positive items fail against a signature-requiring
forge with a message that says how to enable signing.

Receipt-signature verification uses ``thermocline.identity.Verifier`` with
a ``BrineProvider`` whose ephemeral keyring namespace is populated with the
target forge's pubkey (obtained via ``GET /pubkey`` before this harness
runs).
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
import jsonschema
import keyring

from thermocline.identity import BrineProvider, Signature, Verifier, _PUBKEY_PREFIX
from thermocline.schemes import KeyScheme

_SUITE_ROOT = Path(
    os.environ.get(
        "THERMOCLINE_SUITE_ROOT",
        str(Path.home() / "Projects" / "dom"),
    )
)
_SCHEMA_ROOT_DEFAULT = _SUITE_ROOT / "thermocline" / "thermocline" / "schema"

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Self-hosted role fixtures: one accepted task shape per reference forge.
_ROLE_FIXTURES: dict[str, str] = {
    "pi-forge": "task-pi.json",
    "describe-forge": "task-describe.json",
}

# Items that MUST NOT skip: a skip here is scored as FAIL.
_REQUIRED_ITEMS = ("1-envelope-handling", "2-sig-verification", "7-receipt-signatures")

_SOVEREIGN_IDENTITY = "conformance-sovereign"


def _load_schema(name: str, root: Path) -> dict[str, Any]:
    with (root / f"{name}.schema.json").open() as f:
        return json.load(f)


def _load_role_fixture(role: str) -> dict[str, Any]:
    with (_FIXTURES_DIR / _ROLE_FIXTURES[role]).open() as f:
        return json.load(f)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_for_verify(result: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy a result and set ``receipt_signature.sig = None`` for canonicalize-match.

    The forge signed the result envelope with ``receipt_signature.sig = None``
    (FORGE-01); the verifier must recover the same canonical bytes by
    stripping the sig before re-canonicalizing.
    """
    out = copy.deepcopy(result)
    rs = out.get("receipt_signature")
    if isinstance(rs, dict):
        rs["sig"] = None
        rs.pop("bytes_hex", None)
    return out


def _error_code(resp: httpx.Response) -> str | None:
    """Extract error.code from a structured task_error body, else None."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(body, dict):
        return None
    err = body.get("error")
    if isinstance(err, dict) and isinstance(err.get("code"), str):
        return err["code"]
    return None


class _SovereignSigner:
    """Ephemeral sovereign keypair whose verify key is TOFU-registered
    into the target forge's keystore namespace so signed dispatches verify."""

    def __init__(self, register_service: str) -> None:
        self.register_service = register_service
        self._ns = f"thermocline.brine.conformance-sov-{uuid.uuid4().hex[:8]}"
        self._provider = BrineProvider(keyring_service=self._ns)
        self._provider.generate(identity=_SOVEREIGN_IDENTITY)
        pub = self._provider.public_key(identity=_SOVEREIGN_IDENTITY)
        BrineProvider(keyring_service=register_service).register_public_key(
            identity=_SOVEREIGN_IDENTITY, verify_key=pub
        )

    def sign(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Return a signed deep copy per SP-3.3 (sig="" canonicalization)."""
        env = copy.deepcopy(envelope)
        env["dispatch_signature"] = {
            "key_scheme": "brine",
            "node_id": _SOVEREIGN_IDENTITY,
            "policy_hash": None,
            "shadows_generated": [],
            "timestamp": _now_iso(),
            "sig": "",
        }
        sig = self._provider.sign(envelope=env, signer_identity=_SOVEREIGN_IDENTITY)
        env["dispatch_signature"]["sig"] = sig.bytes_.hex()
        return env

    def cleanup(self) -> None:
        for service, key in (
            (self._ns, _SOVEREIGN_IDENTITY),
            (self.register_service, _PUBKEY_PREFIX + _SOVEREIGN_IDENTITY),
        ):
            try:
                keyring.delete_password(service, key)
            except Exception:  # noqa: BLE001
                pass


def run_harness(
    *,
    target_url: str,
    role: str,
    forge_pubkey_hex: str,
    conformance_root: Path | None = None,  # noqa: ARG001 (accepted for CLI compat)
    schema_root: Path | None = None,
    timeout_s: float = 10.0,
    sovereign_service: str | None = None,
) -> dict[str, dict[str, str]]:
    """Run the 13-item checklist (8 conformance + 5 AT-E) against the target forge URL.

    Returns a dict of ``{item_id: {"status": "pass|fail|skip", "message": str}}``.
    """
    schema_root = schema_root or _SCHEMA_ROOT_DEFAULT
    task_result_schema = _load_schema("task_result", schema_root)
    validator = jsonschema.Draft202012Validator(task_result_schema)

    fixture = _load_role_fixture(role)

    headers: dict[str, str] = {}

    signer: _SovereignSigner | None = None
    if sovereign_service:
        signer = _SovereignSigner(sovereign_service)
    _no_signer_hint = (
        "; no sovereign signing keypair configured (pass "
        "--sovereign-register-service <forge keystore namespace> so the "
        "harness can sign dispatches)"
    )

    # Register forge pubkey for receipt verification in an ephemeral namespace.
    sov_ns = f"thermocline.brine.conformance-test-{uuid.uuid4().hex[:8]}"
    sov_provider = BrineProvider(keyring_service=sov_ns)
    sov_provider.register_public_key(
        identity=role, verify_key=bytes.fromhex(forge_pubkey_hex)
    )
    verifier = Verifier()
    verifier.register(sov_provider)

    results: dict[str, dict[str, str]] = {}
    client = httpx.Client(timeout=timeout_s)

    def _post(envelope: Any) -> httpx.Response:
        return client.post(f"{target_url}/task", json=envelope, headers=headers)

    signed_fixture = signer.sign(fixture) if signer else copy.deepcopy(fixture)

    try:
        # Item 1 (REQUIRED): envelope handling. A valid (signed) role fixture
        # must be accepted with 200 and a schema-valid task_result.
        try:
            resp = _post(signed_fixture)
            if resp.status_code == 200:
                validator.validate(resp.json())
                results["1-envelope-handling"] = {
                    "status": "pass",
                    "message": f"{_ROLE_FIXTURES[role]} accepted + schema valid"
                    + ("" if signer else " (unsigned dev-mode dispatch)"),
                }
            else:
                results["1-envelope-handling"] = {
                    "status": "fail",
                    "message": (
                        f"valid fixture rejected ({resp.status_code}, "
                        f"code={_error_code(resp)!r})"
                        + ("" if signer else _no_signer_hint)
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            results["1-envelope-handling"] = {"status": "fail", "message": str(exc)}

        # Item 2 (REQUIRED): dispatch-signature verification. Three live
        # negative cases; every one must be rejected with SIGNATURE_INVALID.
        try:
            failures: list[str] = []

            # (a) Missing dispatch_signature entirely.
            missing = copy.deepcopy(fixture)
            missing.pop("dispatch_signature", None)
            resp = _post(missing)
            if resp.status_code not in (400, 401) or _error_code(resp) != "SIGNATURE_INVALID":
                failures.append(
                    f"missing-sig accepted ({resp.status_code}, code={_error_code(resp)!r})"
                )

            # (b) key_scheme=none downgrade.
            downgrade = copy.deepcopy(fixture)
            downgrade["dispatch_signature"] = {
                "key_scheme": "none",
                "node_id": "conformance-attacker",
                "policy_hash": None,
                "shadows_generated": [],
                "timestamp": _now_iso(),
                "sig": None,
            }
            resp = _post(downgrade)
            if resp.status_code not in (400, 401) or _error_code(resp) != "SIGNATURE_INVALID":
                failures.append(
                    f"none-downgrade accepted ({resp.status_code}, code={_error_code(resp)!r})"
                )

            # (c) Tampered brine signature (self-hosted: sign then flip a
            # byte; garbage bytes when no signer is available).
            if signer:
                tampered = signer.sign(fixture)
                sig_bytes = bytearray(bytes.fromhex(tampered["dispatch_signature"]["sig"]))
                sig_bytes[0] ^= 0xFF
                tampered["dispatch_signature"]["sig"] = bytes(sig_bytes).hex()
            else:
                tampered = copy.deepcopy(fixture)
                tampered["dispatch_signature"] = {
                    "key_scheme": "brine",
                    "node_id": _SOVEREIGN_IDENTITY,
                    "policy_hash": None,
                    "shadows_generated": [],
                    "timestamp": _now_iso(),
                    "sig": "ab" * 64,
                }
            resp = _post(tampered)
            if resp.status_code not in (400, 401) or _error_code(resp) != "SIGNATURE_INVALID":
                failures.append(
                    f"tampered-sig accepted ({resp.status_code}, code={_error_code(resp)!r})"
                )

            if failures:
                results["2-sig-verification"] = {
                    "status": "fail",
                    "message": "; ".join(failures),
                }
            else:
                results["2-sig-verification"] = {
                    "status": "pass",
                    "message": (
                        "missing sig, none downgrade, and tampered sig all "
                        "rejected with SIGNATURE_INVALID"
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            results["2-sig-verification"] = {"status": "fail", "message": str(exc)}

        # Item 3: privacy-fence — honor-system in v0.x.
        results["3-privacy-fence"] = {
            "status": "pass",
            "message": "no persistent logging assertable (honor-system)",
        }

        # Item 4: statelessness — post the same valid fixture twice;
        # result_ids must differ.
        try:
            r1 = _post(signed_fixture)
            r2 = _post(signed_fixture)
            rid1 = r1.json().get("result_id") if r1.status_code == 200 else None
            rid2 = r2.json().get("result_id") if r2.status_code == 200 else None
            if rid1 and rid2 and rid1 != rid2:
                results["4-statelessness"] = {
                    "status": "pass",
                    "message": "result_ids differ across requests",
                }
            elif rid1 == rid2 and rid1 is not None:
                results["4-statelessness"] = {
                    "status": "fail",
                    "message": "result_ids identical across requests",
                }
            else:
                results["4-statelessness"] = {
                    "status": "skip",
                    "message": (
                        f"could not establish baseline "
                        f"({r1.status_code} / {r2.status_code})"
                        + ("" if signer else _no_signer_hint)
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            results["4-statelessness"] = {"status": "fail", "message": str(exc)}

        # Item 5: task-execution — unknown task type must be refused with the
        # documented error code. (Structural checks precede signature checks,
        # so mutating the signed fixture is fine.)
        try:
            draft = copy.deepcopy(signed_fixture)
            draft["task"]["type"] = "data.unsupported.gibberish.42"
            resp = _post(draft)
            code = _error_code(resp)
            if resp.status_code in (400, 422) and code in (
                "UNSUPPORTED_TASK_TYPE",
                "TASK_TYPE_UNAVAILABLE",
            ):
                results["5-task-execution"] = {
                    "status": "pass",
                    "message": f"unknown task type rejected ({resp.status_code}, {code})",
                }
            else:
                results["5-task-execution"] = {
                    "status": "fail",
                    "message": (
                        f"unknown task type not properly rejected "
                        f"({resp.status_code}, code={code!r})"
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            results["5-task-execution"] = {"status": "fail", "message": str(exc)}

        # Item 6: job-execution — N/A for task-only forges.
        results["6-job-execution"] = {
            "status": "skip",
            "message": "N/A — task-only forge",
        }

        # Item 7 (REQUIRED): receipt-signatures — verify the happy-path
        # receipt sig against the pinned pubkey.
        try:
            resp = _post(signed_fixture)
            if resp.status_code != 200:
                results["7-receipt-signatures"] = {
                    "status": "fail",
                    "message": (
                        f"could not obtain a task_result to verify "
                        f"({resp.status_code}, code={_error_code(resp)!r})"
                        + ("" if signer else _no_signer_hint)
                    ),
                }
            else:
                result = resp.json()
                rs = result.get("receipt_signature", {}) or {}
                sig_hex = rs.get("sig") or ""
                if not sig_hex or sig_hex == "00" * 64:
                    results["7-receipt-signatures"] = {
                        "status": "fail",
                        "message": "sig missing or known-invalid",
                    }
                else:
                    sig = Signature(
                        scheme=KeyScheme.BRINE,
                        bytes_=bytes.fromhex(sig_hex),
                        signer_identity=rs.get("node_id") or role,
                    )
                    receipt = verifier.verify(
                        envelope=_strip_for_verify(result), signature=sig
                    )
                    if receipt is None:
                        results["7-receipt-signatures"] = {
                            "status": "fail",
                            "message": "receipt sig failed verification",
                        }
                    else:
                        results["7-receipt-signatures"] = {
                            "status": "pass",
                            "message": "real brine receipt sig verified",
                        }
        except Exception as exc:  # noqa: BLE001
            results["7-receipt-signatures"] = {"status": "fail", "message": str(exc)}

        # Item 8: error-codes — garbage envelope AND wrong version must
        # produce the documented structured codes.
        try:
            problems: list[str] = []
            resp = _post({"garbage": "input"})
            code = _error_code(resp)
            if resp.status_code < 400 or code not in (
                "MALFORMED_ENVELOPE",
                "UNSUPPORTED_VERSION",
                "UNSUPPORTED_TASK_TYPE",
            ):
                problems.append(
                    f"garbage envelope ({resp.status_code}, code={code!r})"
                )

            wrong_version = copy.deepcopy(signed_fixture)
            wrong_version["thermocline"] = "9.9.9"
            resp = _post(wrong_version)
            code = _error_code(resp)
            if resp.status_code != 400 or code != "UNSUPPORTED_VERSION":
                problems.append(
                    f"wrong version ({resp.status_code}, code={code!r})"
                )

            if problems:
                results["8-error-codes"] = {
                    "status": "fail",
                    "message": "; ".join(problems),
                }
            else:
                results["8-error-codes"] = {
                    "status": "pass",
                    "message": (
                        "structured codes for garbage envelope and "
                        "unsupported version"
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            results["8-error-codes"] = {"status": "fail", "message": str(exc)}

        # AT-E1: malicious payload — non-object JSON body must yield a
        # structured error, never an unstructured 5xx.
        try:
            resp = _post([1, 2, 3])
            code = _error_code(resp)
            if 400 <= resp.status_code < 500 and code == "MALFORMED_ENVELOPE":
                results["AT-E1"] = {
                    "status": "pass",
                    "message": "non-object body rejected with MALFORMED_ENVELOPE",
                }
            else:
                results["AT-E1"] = {
                    "status": "fail",
                    "message": (
                        f"non-object body handling ({resp.status_code}, "
                        f"code={code!r})"
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            results["AT-E1"] = {"status": "fail", "message": str(exc)}

        # AT-E2: resource exhaustion — an oversized body must be refused
        # with a structured 4xx before computation.
        try:
            oversized = copy.deepcopy(fixture)
            oversized["task"]["instruction"] = "x" * (2 * 1024 * 1024)
            resp = _post(oversized)
            code = _error_code(resp)
            if 400 <= resp.status_code < 500 and code is not None:
                results["AT-E2"] = {
                    "status": "pass",
                    "message": (
                        f"2 MiB body rejected ({resp.status_code}, {code})"
                    ),
                }
            else:
                results["AT-E2"] = {
                    "status": "fail",
                    "message": (
                        f"oversized body not structurally rejected "
                        f"({resp.status_code}, code={code!r})"
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            results["AT-E2"] = {"status": "fail", "message": str(exc)}

        # AT-E3: tool escape — task-only reference forges expose no tool
        # registry; live behavioral coverage lives in conformance/at_negative.
        results["AT-E3"] = {
            "status": "skip",
            "message": (
                "no tool surface on task-only forges; see "
                "at_negative/test_at_e3_tool_escape.py"
            ),
        }

        # AT-E4: forge impersonation — the receipt signature must verify
        # against the pinned pubkey (the sovereign-side defense). Reuses
        # item 7's live verification result.
        item7 = results.get("7-receipt-signatures", {"status": "fail"})
        if item7["status"] == "pass":
            results["AT-E4"] = {
                "status": "pass",
                "message": "receipt verified against pinned pubkey (see item 7)",
            }
        else:
            results["AT-E4"] = {
                "status": "fail",
                "message": (
                    "receipt could not be verified against the pinned pubkey: "
                    + item7.get("message", "")
                ),
            }

        # AT-E5: timing side-channel — a black-box HTTP harness cannot
        # meaningfully evaluate timing variance; documented surface.
        results["AT-E5"] = {
            "status": "skip",
            "message": (
                "timing side-channel evaluation out of scope for a black-box "
                "harness (CONF-02 surface)"
            ),
        }

        # Required items can never skip: score any residual skip as FAIL.
        for item_id in _REQUIRED_ITEMS:
            entry = results.get(item_id)
            if entry is None or entry.get("status") == "skip":
                results[item_id] = {
                    "status": "fail",
                    "message": "required item did not run: "
                    + (entry or {}).get("message", "no result recorded"),
                }

        return results
    finally:
        client.close()
        if signer:
            signer.cleanup()
        # Best-effort cleanup of the ephemeral namespace.
        try:
            keyring.delete_password(sov_ns, _PUBKEY_PREFIX + role)
        except Exception:  # noqa: BLE001
            pass


__all__ = ["run_harness"]
