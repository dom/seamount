"""pi-forge CLI: ``init`` + ``serve`` subcommands (CONTEXT D-01).

Wire shape:

    python -m pi_forge init   [--keyring-service NS] [--identity ID]
    python -m pi_forge serve  [--keyring-service NS] [--port PORT]

Idempotency: re-running ``init`` with the same identity in the same namespace
exits 0 with "no-op" message. Running ``init --identity X`` against a namespace
that already holds a different identity exits 2 (refuses overwrite).
"""
from __future__ import annotations

import argparse
import os
import sys

# Flat-layout pi-forge ships modules at the project root next to this package.
# Make them importable so callers can `python -m pi_forge` without setting
# PYTHONPATH manually. (Editable install registers the package; this adds the
# sibling flat modules.)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def cmd_init(args: argparse.Namespace) -> int:
    """Create the forge keypair in the configured keystore namespace (D-01)."""
    from thermocline.identity import IdentityError
    from forge_identity import FORGE_KEYRING_SERVICE, FORGE_IDENTITY, get_provider

    service = args.keyring_service or os.environ.get(
        "PIFORGE_KEYRING_SERVICE", FORGE_KEYRING_SERVICE
    )
    identity = args.identity or os.environ.get(
        "PIFORGE_IDENTITY", FORGE_IDENTITY
    )
    provider = get_provider(service)
    try:
        provider.generate(identity=identity)
    except IdentityError as exc:
        if exc.code == "IDENTITY_ALREADY_EXISTS":
            # Idempotency: a key already lives under (service, identity).
            # Probe to confirm the requested identity matches the existing one;
            # if the keystore entry for *this* identity is readable, treat as
            # no-op. The only failure mode is "different identity under same
            # service" — surface as exit 2 to the caller.
            try:
                provider.public_key(identity=identity)
            except Exception:
                print(
                    f"ERROR: a different identity exists in {service!r}; "
                    f"refusing to overwrite. Delete the existing entry first.",
                    file=sys.stderr,
                )
                return 2
            print(f"Keypair already exists for {identity!r} (no-op).")
            return 0
        raise

    print(f"Keypair created for {identity!r} in keystore {service!r}.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the Flask app and print the ready marker for subprocess fixtures."""
    if args.keyring_service:
        os.environ["PIFORGE_KEYRING_SERVICE"] = args.keyring_service
    from server import app

    port = args.port or int(os.environ.get("FORGE_PORT", "5100"))
    print(f"PIFORGE_READY port={port}", flush=True)
    app.run(host="0.0.0.0", port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pi-forge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Create the forge keypair (idempotent).")
    p_init.add_argument("--keyring-service", default=None)
    p_init.add_argument("--identity", default=None)
    p_init.set_defaults(func=cmd_init)

    p_serve = sub.add_parser("serve", help="Run the forge HTTP server.")
    p_serve.add_argument("--keyring-service", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
