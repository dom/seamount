"""llm-forge CLI: ``init`` + ``serve`` subcommands.

    python -m llm_forge init   [--keyring-service NS] [--identity ID]
    python -m llm_forge serve  [--keyring-service NS] [--port PORT]

Idempotency: re-running ``init`` with the same identity in the same namespace
exits 0 with "no-op" message. Running ``init --identity X`` against a namespace
that already holds a different identity exits 2 (refuses overwrite).
"""
from __future__ import annotations

import argparse
import os
import sys

# Flat-layout llm-forge ships modules at the project root next to this package.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def cmd_init(args: argparse.Namespace) -> int:
    from thermocline.identity import IdentityError
    from forge_identity import FORGE_KEYRING_SERVICE, FORGE_IDENTITY, get_provider

    service = args.keyring_service or os.environ.get(
        "LLMFORGE_KEYRING_SERVICE", FORGE_KEYRING_SERVICE
    )
    identity = args.identity or os.environ.get(
        "LLMFORGE_IDENTITY", FORGE_IDENTITY
    )
    provider = get_provider(service)
    try:
        provider.generate(identity=identity)
    except IdentityError as exc:
        if exc.code == "IDENTITY_ALREADY_EXISTS":
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
    if args.keyring_service:
        os.environ["LLMFORGE_KEYRING_SERVICE"] = args.keyring_service
    from server import app

    port = args.port or int(os.environ.get("FORGE_PORT", "5101"))
    host = os.environ.get("FORGE_BIND_HOST", "127.0.0.1")
    # Skip slow DNS during Flask startup on macOS (see pi-forge for context).
    import socket as _socket
    _socket.getfqdn = lambda name="": name or "localhost"
    print(f"LLMFORGE_READY port={port}", flush=True)
    app.run(host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llm-forge")
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
