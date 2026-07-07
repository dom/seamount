"""CLI entry: ``python -m forge_conformance --target URL --role <forge>``.

Roles: ``pi-forge``, ``describe-forge``, ``llm-forge``.

Fetches the target forge's pubkey via ``GET /pubkey``, runs the 13-item
checklist, prints the structured report, and exits 0 (all pass), 1
(any fail), or 2 (bootstrap error — e.g., /pubkey unreachable).

Since forges require verified brine dispatch signatures by default, pass
``--sovereign-register-service <namespace>`` (the forge's keystore
namespace) when the harness runs on the same host as the forge: the
harness generates an ephemeral sovereign keypair, TOFU-registers its
verify key there, and signs the positive-path fixtures. Without it, the
signature-requiring positive items fail with a hint.

For ``--role llm-forge`` the harness sends ``Authorization: Bearer`` with
``--auth-bearer`` (or a placeholder); point the forge at
``python -m forge_conformance._mock_upstream`` for a keyless canned
upstream.
"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

import httpx

from ._harness import run_harness
from ._report import build_report, emit_human, emit_json, now_utc_iso


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge_conformance")
    parser.add_argument(
        "--target",
        required=True,
        help="Forge HTTP URL (e.g., http://127.0.0.1:5100)",
    )
    parser.add_argument(
        "--role",
        required=True,
        choices=["pi-forge", "describe-forge", "llm-forge"],
    )
    parser.add_argument(
        "--output", default="human", choices=["human", "json"]
    )
    parser.add_argument("--conformance-root", default=None)
    parser.add_argument("--schema-root", default=None)
    parser.add_argument(
        "--sovereign-register-service",
        default=None,
        help=(
            "Forge keystore namespace to TOFU-register an ephemeral "
            "sovereign verify key into, enabling signed positive-path "
            "fixtures (same-host runs only)."
        ),
    )
    parser.add_argument(
        "--auth-bearer",
        default=None,
        help="Bearer token sent on /task requests (llm-forge role).",
    )
    args = parser.parse_args(argv)

    # Fetch pubkey for receipt verification.
    try:
        resp = httpx.get(f"{args.target}/pubkey", timeout=10.0)
        resp.raise_for_status()
        pubkey_hex = resp.json()["pubkey"]
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not fetch /pubkey: {exc}", file=sys.stderr)
        return 2

    from pathlib import Path

    conformance_root = (
        Path(args.conformance_root) if args.conformance_root else None
    )
    schema_root = Path(args.schema_root) if args.schema_root else None

    started = now_utc_iso()
    results = run_harness(
        target_url=args.target,
        role=args.role,
        forge_pubkey_hex=pubkey_hex,
        conformance_root=conformance_root,
        schema_root=schema_root,
        sovereign_service=args.sovereign_register_service,
        auth_bearer=args.auth_bearer,
    )
    completed = now_utc_iso()
    report = build_report(
        target_url=args.target,
        role=args.role,
        started_at=started,
        completed_at=completed,
        item_results=results,
    )
    if args.output == "json":
        print(emit_json(report))
    else:
        print(emit_human(report))
    return 0 if report["total_fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
