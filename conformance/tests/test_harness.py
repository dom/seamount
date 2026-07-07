"""End-to-end harness tests against real pi-forge + describe-forge subprocesses.

Coverage:
    - test_harness_runs_against_pi_forge
    - test_harness_runs_against_describe_forge
    - test_harness_detects_invalid_receipt_signature
    - test_harness_detects_extra_field (handled via per-fixture invalid corpus)
    - test_cli_exit_code_on_fail (via subprocess invocation)

Forge subprocess setup mirrors photophore/python/tests/integration/conftest.py
via the :mod:`conftest` in this directory.
"""
from __future__ import annotations

import json
import multiprocessing
import socket
import subprocess
import sys
import time
import uuid
from typing import Any

import httpx
import pytest

from forge_conformance._harness import run_harness
from forge_conformance._report import build_report, emit_json, now_utc_iso

from tests.conftest import ConformanceForgeHandle  # type: ignore[import]


# Every live item that must PASS against a properly configured forge.
_REQUIRED_PASS = {
    "1-envelope-handling",  # signed fixture accepted + schema valid
    "2-sig-verification",  # missing sig / none downgrade / tampered sig all rejected
    "3-privacy-fence",  # honor-system always passes
    "4-statelessness",  # result_ids differ
    "5-task-execution",  # unknown task type -> UNSUPPORTED_TASK_TYPE
    "7-receipt-signatures",  # receipt verifies against pinned pubkey
    "8-error-codes",  # garbage + wrong version -> structured codes
    "AT-E1",  # non-object body -> MALFORMED_ENVELOPE
    "AT-E2",  # oversized body -> structured 4xx
    "AT-E4",  # receipt pinned-pubkey verification
}


def _assert_full_conformance(forge: ConformanceForgeHandle) -> None:
    results = run_harness(
        target_url=forge.url,
        role=forge.role,
        forge_pubkey_hex=forge.pubkey_hex,
        sovereign_service=forge.namespace,
    )
    report = build_report(
        target_url=forge.url,
        role=forge.role,
        started_at=now_utc_iso(),
        completed_at=now_utc_iso(),
        item_results=results,
    )
    for entry in report["checklist"]:
        if entry["id"] in _REQUIRED_PASS:
            assert entry["status"] == "pass", (
                f"{entry['id']} expected pass, got "
                f"{entry['status']}: {entry['message']!r}"
            )
    # Documented skips only: job engine (task-only forges), tool escape
    # (no tool surface), timing side channel (black-box harness).
    for at_id in ("6-job-execution", "AT-E3", "AT-E5"):
        entry = next(e for e in report["checklist"] if e["id"] == at_id)
        assert entry["status"] == "skip"
    assert report["total_fail"] == 0


@pytest.mark.parametrize("conformance_forge", ["pi-forge"], indirect=True)
def test_harness_runs_against_pi_forge(
    conformance_forge: ConformanceForgeHandle,
) -> None:
    """Harness end-to-end against pi-forge: all live items pass."""
    _assert_full_conformance(conformance_forge)


@pytest.mark.parametrize("conformance_forge", ["describe-forge"], indirect=True)
def test_harness_runs_against_describe_forge(
    conformance_forge: ConformanceForgeHandle,
) -> None:
    """Harness end-to-end against describe-forge (self-hosted shadow fixture)."""
    _assert_full_conformance(conformance_forge)


@pytest.mark.parametrize("conformance_forge", ["llm-forge"], indirect=True)
def test_harness_runs_against_llm_forge(
    conformance_forge: ConformanceForgeHandle,
) -> None:
    """Harness end-to-end against llm-forge relaying to the mock upstream."""
    _assert_full_conformance(conformance_forge)


@pytest.mark.parametrize("conformance_forge", ["pi-forge"], indirect=True)
def test_required_items_fail_without_signing(
    conformance_forge: ConformanceForgeHandle,
) -> None:
    """Without a sovereign signer, a sig-requiring forge FAILS items 1/7.

    Pins the skip-scores-as-pass regression: required items must surface as
    FAIL (with a remediation hint), never as skip.
    """
    forge = conformance_forge
    results = run_harness(
        target_url=forge.url,
        role=forge.role,
        forge_pubkey_hex=forge.pubkey_hex,
        sovereign_service=None,
    )
    assert results["1-envelope-handling"]["status"] == "fail"
    assert results["7-receipt-signatures"]["status"] == "fail"
    # Negative sig cases need no signer and still pass.
    assert results["2-sig-verification"]["status"] == "pass"


def _forged_receipt_app(port: int) -> None:
    """In-process Flask forge that returns receipt_signature.sig = '00'*64."""
    import os
    import sys

    # Redirect child stdout/stderr to /dev/null so Flask's per-request logging
    # cannot fill pytest's capture buffer (which on macOS arm64 GH runners
    # backs into a pipe with a small buffer; once full, Flask blocks on write
    # and stops handling /pubkey).
    devnull = open(os.devnull, "w")
    sys.stdout = devnull
    sys.stderr = devnull

    # Stub socket.getfqdn — werkzeug's HTTPServer.server_bind calls it on
    # the bound host and reverse-DNS of 127.0.0.1 hangs ~35s on macOS arm64
    # GH runners. server_name isn't used by this fake forge.
    import socket as _socket
    _socket.getfqdn = lambda name="": name or "localhost"

    from flask import Flask, jsonify, request  # local import — child process

    app = Flask(__name__)

    @app.post("/task")
    def fake_task() -> Any:
        body = request.get_json(force=True)
        envelope_id = body.get("envelope_id", "fake-envelope")
        result_id = "0f0f0f0f-0000-4000-8000-00000000000f"
        return jsonify(
            {
                "thermocline": "0.3.1",
                "type": "task_result",
                "envelope_id": envelope_id,
                "result_id": result_id,
                "completed_at": "2026-05-11T00:00:00Z",
                "responder": "pi-forge",
                "outputs": {"pi": "3.14"},
                "provenance": {
                    "shadows_received": [],
                    "tiers_present": [2],
                    "local_tiers_present": False,
                },
                "receipt_signature": {
                    "key_scheme": "brine",
                    "node_id": "pi-forge",
                    "envelope_id": envelope_id,
                    "result_id": result_id,
                    "timestamp": "2026-05-11T00:00:00Z",
                    "sig": "00" * 64,
                },
            }
        ), 200

    @app.get("/pubkey")
    def pubkey() -> Any:
        # Return a random-but-fixed pubkey so the harness can do bootstrap.
        return jsonify(
            {
                "identity": "pi-forge",
                "key_scheme": "brine",
                "pubkey": "ab" * 32,  # 64 hex chars = 32 bytes
            }
        ), 200

    @app.get("/health")
    def health() -> Any:
        return jsonify({"status": "ok"}), 200

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def permissive_forge_results() -> dict[str, dict[str, str]]:
    """Run the harness once against the permissive forged-receipt fake forge.

    The fake forge performs NO dispatch-signature verification (it accepts
    unsigned, none-downgraded, and tampered envelopes with 200) and returns
    a forged ``receipt_signature.sig``. Module-scoped: one subprocess spawn
    plus one harness run feeds every assertion on this hostile profile.
    """
    port = _free_port()
    proc = multiprocessing.Process(
        target=_forged_receipt_app, args=(port,), daemon=True
    )
    proc.start()
    try:
        url = f"http://127.0.0.1:{port}"
        # 60s budget accommodates cold macOS arm64 GH-runner starts; locally
        # the in-process Flask app is ready in <0.5s.
        deadline = time.monotonic() + 60.0
        ready = False
        while time.monotonic() < deadline:
            if not proc.is_alive():
                raise RuntimeError("forged-receipt forge died during startup")
            try:
                resp = httpx.get(f"{url}/pubkey", timeout=0.5)
                if resp.status_code == 200:
                    ready = True
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.1)
        assert ready, "forged-receipt forge did not become ready"
        return run_harness(
            target_url=url, role="pi-forge", forge_pubkey_hex="ab" * 32
        )
    finally:
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2)


def test_harness_detects_invalid_receipt_signature(
    permissive_forge_results: dict[str, dict[str, str]],
) -> None:
    """Test 3: a forge returning sig='00'*64 makes 7-receipt-signatures FAIL."""
    # The pubkey served is "ab"*32 — verifier.verify() returns None
    # (signature mismatch) and the harness marks 7-receipt-signatures FAIL.
    item7 = permissive_forge_results.get(
        "7-receipt-signatures", {"status": "skip"}
    )
    assert item7["status"] == "fail", (
        f"expected 7-receipt-signatures FAIL on forged sig, got {item7!r}"
    )


def test_harness_fails_forge_accepting_unsigned_envelopes(
    permissive_forge_results: dict[str, dict[str, str]],
) -> None:
    """A forge that accepts unsigned/none/tampered dispatches FAILS item 2.

    Pins the core MED hardening claim: the sig-verification checklist item
    runs its three live negative cases and scores acceptance of ANY of them
    as FAIL, never as skip or pass.
    """
    item2 = permissive_forge_results.get(
        "2-sig-verification", {"status": "skip"}
    )
    assert item2["status"] == "fail", (
        f"expected 2-sig-verification FAIL against a forge that accepts "
        f"unsigned envelopes, got {item2!r}"
    )
    # All three negative cases were accepted by the permissive forge, so
    # every one must be named in the failure message.
    for marker in ("missing-sig", "none-downgrade", "tampered-sig"):
        assert marker in item2["message"], (
            f"{marker!r} acceptance not reported in {item2['message']!r}"
        )


def test_cli_exit_code_on_fail() -> None:
    """Test 7: CLI exits non-zero when any checklist item is FAIL.

    Runs the CLI against an unreachable URL; the pubkey fetch fails with
    exit code 2 (bootstrap error), proving the CLI surfaces failures to
    the caller for CI purposes.
    """
    bad_url = f"http://127.0.0.1:{_free_port()}"  # nothing listens here
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "forge_conformance",
            "--target",
            bad_url,
            "--role",
            "pi-forge",
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0, (
        f"CLI exited 0 on unreachable target (expected non-zero); "
        f"stdout: {result.stdout!r}, stderr: {result.stderr!r}"
    )


def test_cli_help_exits_zero_with_required_flags() -> None:
    """Smoke: ``python -m forge_conformance --help`` exits 0 and documents flags."""
    result = subprocess.run(
        [sys.executable, "-m", "forge_conformance", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "--target" in result.stdout
    assert "--role" in result.stdout


@pytest.mark.parametrize("conformance_forge", ["pi-forge"], indirect=True)
def test_cli_json_output_against_pi_forge(
    conformance_forge: ConformanceForgeHandle,
) -> None:
    """End-to-end CLI invocation: JSON report against a live pi-forge."""
    forge = conformance_forge
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "forge_conformance",
            "--target",
            forge.url,
            "--role",
            "pi-forge",
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # exit 0 (all pass) or 1 (some fail) is OK; exit 2 means /pubkey unreachable.
    assert result.returncode in (0, 1), (
        f"CLI failed to bootstrap (rc={result.returncode}); "
        f"stderr: {result.stderr!r}"
    )
    parsed = json.loads(result.stdout)
    assert parsed["role"] == "pi-forge"
    assert parsed["target_url"] == forge.url
    assert len(parsed["checklist"]) == 13
