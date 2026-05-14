"""describe-forge CLI: ``init`` + ``serve`` subcommands.

Mirrors pi-forge's __main__.py with these differences:
    - Default keystore namespace ``seamount.describeforge``
    - Default identity ``describe-forge``
    - Default port 5200
    - Ready marker ``DESCRIBEFORGE_READY port=<n>``
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def cmd_init(args: argparse.Namespace) -> int:
    """Create the forge keypair in the configured keystore namespace (D-01)."""
    from thermocline.identity import IdentityError
    from forge_identity import FORGE_KEYRING_SERVICE, FORGE_IDENTITY, get_provider

    service = args.keyring_service or os.environ.get(
        "DESCRIBEFORGE_KEYRING_SERVICE", FORGE_KEYRING_SERVICE
    )
    identity = args.identity or os.environ.get(
        "DESCRIBEFORGE_IDENTITY", FORGE_IDENTITY
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
    """Run the Flask app and print the ready marker for subprocess fixtures."""
    if args.keyring_service:
        os.environ["DESCRIBEFORGE_KEYRING_SERVICE"] = args.keyring_service
    from server import app

    port = args.port or int(os.environ.get("FORGE_PORT", "5200"))
    # FORGE_BIND_HOST defaults to 0.0.0.0 (production behavior). Set to
    # 127.0.0.1 in test fixtures.
    host = os.environ.get("FORGE_BIND_HOST", "0.0.0.0")
    # Skip slow DNS during Flask startup on macOS arm64 GH runners. Two
    # werkzeug paths call into the resolver: display_addresses does
    # gethostbyname(gethostname()) when host is 0.0.0.0 (~35s on the
    # runner), and HTTPServer.server_bind always calls getfqdn(host)
    # (~35s for reverse-DNS of 127.0.0.1). The forge does not use the
    # resolved server_name anywhere, so stubbing getfqdn is safe.
    import socket as _socket
    _socket.getfqdn = lambda name="": name or "localhost"
    print(f"DESCRIBEFORGE_READY port={port}", flush=True)
    app.run(host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="describe-forge")
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
