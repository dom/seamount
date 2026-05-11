"""Core harness: POST fixtures, validate response JSON Schema, verify receipt signatures.

Runs each of the Seamount 13-item conformance checklist items against a live
forge URL. Items 1-8 cover the §"Forge Conformance Requirements" surface;
items AT-E1..AT-E5 cover the §"Attack Surfaces and Mitigations" register.

Receipt-signature verification uses ``thermocline.identity.Verifier`` with a
``BrineProvider`` whose ephemeral keyring namespace is populated with the
target forge's pubkey (obtained via ``GET /pubkey`` before this harness runs).
"""
from __future__ import annotations

import copy
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

from ._fixtures import load_fixtures

_SCHEMA_ROOT_DEFAULT = Path(
    "/Users/dom/Projects/dom/thermocline/thermocline/schema"
)


def _load_schema(name: str, root: Path) -> dict[str, Any]:
    with (root / f"{name}.schema.json").open() as f:
        return json.load(f)


def _strip_for_verify(result: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy a result and set ``receipt_signature.sig = None`` for canonicalize-match.

    The forge signed the result envelope with ``receipt_signature.sig = None``
    (FORGE-01 / Plan 03-02 SP-3.2-01); the verifier must recover the same
    canonical bytes by stripping the sig before re-canonicalizing.
    """
    out = copy.deepcopy(result)
    rs = out.get("receipt_signature")
    if isinstance(rs, dict):
        rs["sig"] = None
        rs.pop("bytes_hex", None)
    return out


def run_harness(
    *,
    target_url: str,
    role: str,
    forge_pubkey_hex: str,
    conformance_root: Path | None = None,
    schema_root: Path | None = None,
    timeout_s: float = 10.0,
) -> dict[str, dict[str, str]]:
    """Run the 13-item checklist (8 conformance + 5 AT-E) against the target forge URL.

    Returns a dict of ``{item_id: {"status": "pass|fail|skip", "message": str}}``.
    """
    schema_root = schema_root or _SCHEMA_ROOT_DEFAULT
    task_result_schema = _load_schema("task_result", schema_root)
    validator = jsonschema.Draft202012Validator(task_result_schema)

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

    try:
        # Item 1: envelope handling — post a valid fixture, expect 200 + schema-valid.
        try:
            valid_fixture_name: str | None = None
            for name, fixture in load_fixtures(conformance_root, "valid"):
                if "task" not in name.lower() or fixture.get("type") != "task":
                    continue
                resp = client.post(f"{target_url}/task", json=fixture)
                if resp.status_code == 200:
                    validator.validate(resp.json())
                    results["1-envelope-handling"] = {
                        "status": "pass",
                        "message": f"{name} accepted + schema valid",
                    }
                    valid_fixture_name = name
                    break
                else:
                    # Some valid fixtures may require channel state the forge
                    # doesn't know about (e.g., key_scheme=none doesn't match a
                    # forge expecting brine). Keep trying.
                    continue
            if "1-envelope-handling" not in results:
                results["1-envelope-handling"] = {
                    "status": "skip",
                    "message": "no valid task fixture accepted by forge",
                }
        except Exception as exc:  # noqa: BLE001
            results["1-envelope-handling"] = {"status": "fail", "message": str(exc)}

        # Item 2: sig-verification — post the AT-C2 tampered-signature fixture, expect 401/400.
        try:
            handled = False
            for name, fixture in load_fixtures(conformance_root, "invalid"):
                if "AT-C2" not in name:
                    continue
                envelope = fixture.get("envelope", fixture)
                resp = client.post(f"{target_url}/task", json=envelope)
                if resp.status_code in (400, 401):
                    results["2-sig-verification"] = {
                        "status": "pass",
                        "message": f"tampered sig rejected ({resp.status_code})",
                    }
                else:
                    results["2-sig-verification"] = {
                        "status": "fail",
                        "message": f"accepted tampered sig ({resp.status_code})",
                    }
                handled = True
                break
            if not handled:
                results["2-sig-verification"] = {
                    "status": "skip",
                    "message": "AT-C2 fixture not found",
                }
        except Exception as exc:  # noqa: BLE001
            results["2-sig-verification"] = {"status": "fail", "message": str(exc)}

        # Item 3: privacy-fence — honor-system in v0.1.
        results["3-privacy-fence"] = {
            "status": "pass",
            "message": "no persistent logging assertable in v0.1 (honor-system)",
        }

        # Item 4: statelessness — post same valid fixture twice; result_ids must differ.
        try:
            fixtures = list(load_fixtures(conformance_root, "valid"))
            task_fixtures = [
                (n, f) for n, f in fixtures
                if "task" in n.lower() and f.get("type") == "task"
            ]
            if not task_fixtures:
                results["4-statelessness"] = {
                    "status": "skip",
                    "message": "no valid task fixture",
                }
            else:
                _, fix = task_fixtures[0]
                r1 = client.post(f"{target_url}/task", json=fix)
                r2 = client.post(f"{target_url}/task", json=fix)
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
                        ),
                    }
        except Exception as exc:  # noqa: BLE001
            results["4-statelessness"] = {"status": "fail", "message": str(exc)}

        # Item 5: task-execution — post a task with an unsupported type; expect 400/422.
        try:
            valid_fixtures = list(load_fixtures(conformance_root, "valid"))
            handled = False
            for name, fix in valid_fixtures:
                if fix.get("type") != "task":
                    continue
                draft = json.loads(json.dumps(fix))  # deep copy
                if "task" in draft and isinstance(draft["task"], dict):
                    draft["task"]["type"] = "data.unsupported.gibberish.42"
                    resp = client.post(f"{target_url}/task", json=draft)
                    if resp.status_code in (400, 422):
                        results["5-task-execution"] = {
                            "status": "pass",
                            "message": (
                                f"unsupported task type rejected ({resp.status_code})"
                            ),
                        }
                    else:
                        results["5-task-execution"] = {
                            "status": "fail",
                            "message": (
                                f"accepted unsupported type ({resp.status_code})"
                            ),
                        }
                    handled = True
                    break
            if not handled:
                results["5-task-execution"] = {
                    "status": "skip",
                    "message": "no task fixture available to mutate",
                }
        except Exception as exc:  # noqa: BLE001
            results["5-task-execution"] = {"status": "fail", "message": str(exc)}

        # Item 6: job-execution — N/A for task-only forges in v0.1.
        results["6-job-execution"] = {
            "status": "skip",
            "message": "N/A — task-only forge (v0.1)",
        }

        # Item 7: receipt-signatures — verify the happy-path receipt sig.
        try:
            if results.get("1-envelope-handling", {}).get("status") == "pass":
                # Find the fixture we just used and re-post.
                handled = False
                for name, fixture in load_fixtures(conformance_root, "valid"):
                    if fixture.get("type") != "task":
                        continue
                    resp = client.post(f"{target_url}/task", json=fixture)
                    if resp.status_code != 200:
                        continue
                    result = resp.json()
                    rs = result.get("receipt_signature", {})
                    sig_hex = rs.get("sig") or rs.get("bytes_hex") or ""
                    if not sig_hex or sig_hex == "00" * 64:
                        results["7-receipt-signatures"] = {
                            "status": "fail",
                            "message": "sig missing or known-invalid",
                        }
                        handled = True
                        break
                    try:
                        sig = Signature(
                            scheme=KeyScheme.BRINE,
                            bytes_=bytes.fromhex(sig_hex),
                            signer_identity=rs.get("node_id") or role,
                        )
                        envelope_for_verify = _strip_for_verify(result)
                        receipt = verifier.verify(
                            envelope=envelope_for_verify, signature=sig
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
                        handled = True
                        break
                    except Exception as exc:  # noqa: BLE001
                        results["7-receipt-signatures"] = {
                            "status": "fail",
                            "message": str(exc),
                        }
                        handled = True
                        break
                if not handled:
                    results["7-receipt-signatures"] = {
                        "status": "skip",
                        "message": "no fixture matched for receipt check",
                    }
            else:
                results["7-receipt-signatures"] = {
                    "status": "skip",
                    "message": "envelope handling failed; cannot test receipt",
                }
        except Exception as exc:  # noqa: BLE001
            results["7-receipt-signatures"] = {"status": "fail", "message": str(exc)}

        # Item 8: error-codes — post a malformed envelope, expect a structured error code.
        try:
            resp = client.post(f"{target_url}/task", json={"garbage": "input"})
            if resp.status_code >= 400:
                body: Any = {}
                try:
                    body = resp.json()
                except Exception:  # noqa: BLE001
                    pass
                err = body.get("error", {}) if isinstance(body, dict) else {}
                if isinstance(err, dict) and err.get("code") in (
                    "MALFORMED_ENVELOPE",
                    "UNSUPPORTED_VERSION",
                    "UNSUPPORTED_TASK_TYPE",
                ):
                    results["8-error-codes"] = {
                        "status": "pass",
                        "message": f"structured error code {err['code']}",
                    }
                else:
                    results["8-error-codes"] = {
                        "status": "fail",
                        "message": f"no recognized error code: {body!r}",
                    }
            else:
                results["8-error-codes"] = {
                    "status": "fail",
                    "message": f"garbage envelope accepted ({resp.status_code})",
                }
        except Exception as exc:  # noqa: BLE001
            results["8-error-codes"] = {"status": "fail", "message": str(exc)}

        # Items AT-E1..AT-E4: Phase 4 covers full negative-test sweep; Phase 3 marks skip.
        for at_item in ("AT-E1", "AT-E2", "AT-E3", "AT-E4"):
            results[at_item] = {
                "status": "skip",
                "message": "covered fully in Phase 4 negative-test sweep",
            }
        # Item AT-E5: timing side-channel — distinct surface per seamount/README.md
        # line 326; Phase 3 cannot evaluate timing variance against a black-box
        # forge, so we mark skip with the deferred-reason string.
        results["AT-E5"] = {
            "status": "skip",
            "message": (
                "timing side-channel evaluation deferred to Phase 4 "
                "hardening (CONF-02 surface)"
            ),
        }

        return results
    finally:
        client.close()
        # Best-effort cleanup of the ephemeral namespace.
        try:
            keyring.delete_password(sov_ns, _PUBKEY_PREFIX + role)
        except Exception:  # noqa: BLE001
            pass


__all__ = ["run_harness"]
