"""forge_conformance test fixtures: subprocess forge spawner (mirrors photophore Plan 03-03).

Self-contained fixture so the harness tests can run against real pi-forge and
describe-forge processes on ephemeral ports + isolated keystore namespaces,
without depending on photophore's tests/ tree.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Generator, Tuple

import httpx
import keyring
import pytest


_SUITE_ROOT = Path(
    os.environ.get(
        "THERMOCLINE_SUITE_ROOT",
        str(Path.home() / "Projects" / "dom"),
    )
)
_SEAMOUNT_ROOT = _SUITE_ROOT / "seamount"
_FORGE_PATHS: dict[str, dict[str, str]] = {
    "pi-forge": {
        "dir": str(_SEAMOUNT_ROOT / "pi-forge"),
        "module": "pi_forge",
        "namespace_prefix": "seamount.piforge",
        "identity": "pi-forge",
        "env_prefix": "PIFORGE",
    },
    "describe-forge": {
        "dir": str(_SEAMOUNT_ROOT / "describe-forge"),
        "module": "describe_forge",
        "namespace_prefix": "seamount.describeforge",
        "identity": "describe-forge",
        "env_prefix": "DESCRIBEFORGE",
    },
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return int(s.getsockname()[1])


class ConformanceForgeHandle:
    """Live forge handle yielded by the ``conformance_forge`` fixture."""

    __slots__ = ("url", "pubkey_hex", "role", "namespace", "identity")

    def __init__(
        self, *, url: str, pubkey_hex: str, role: str, namespace: str, identity: str
    ) -> None:
        self.url = url
        self.pubkey_hex = pubkey_hex
        self.role = role
        self.namespace = namespace
        self.identity = identity


@pytest.fixture
def conformance_forge(
    request: pytest.FixtureRequest,
) -> Generator[ConformanceForgeHandle, None, None]:
    """Spawn a real forge subprocess; yield a :class:`ConformanceForgeHandle`."""
    role = request.param
    assert role in _FORGE_PATHS, f"unknown role {role!r}"
    meta = _FORGE_PATHS[role]
    test_ns = f"{meta['namespace_prefix']}.test-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    forge_dir = Path(meta["dir"])
    # Prefer per-forge .venv (local dev convention); fall back to current
    # interpreter for CI environments that install forges into the runner's
    # site-packages.
    venv_python = forge_dir / ".venv" / "bin" / "python3"
    if not venv_python.exists():
        venv_python = forge_dir / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable)
    env = {**os.environ}
    env[f"{meta['env_prefix']}_KEYRING_SERVICE"] = test_ns
    env[f"{meta['env_prefix']}_IDENTITY"] = meta["identity"]
    env["FORGE_NODE_ID"] = meta["identity"]
    env["FORGE_PORT"] = str(port)
    # Bind to loopback only. Default 0.0.0.0 triggers werkzeug's
    # `socket.gethostbyname(socket.gethostname())` in display_addresses,
    # which hangs ~70s on macOS arm64 GH runners between "Debug mode: off"
    # and "Running on http://...". Harness tests connect via 127.0.0.1.
    env["FORGE_BIND_HOST"] = "127.0.0.1"

    init_result = subprocess.run(
        [
            str(venv_python),
            "-m",
            meta["module"],
            "init",
            "--keyring-service",
            test_ns,
            "--identity",
            meta["identity"],
        ],
        cwd=str(forge_dir),
        env=env,
        check=False,
        timeout=20,
        capture_output=True,
        text=True,
    )
    if init_result.returncode != 0:
        raise RuntimeError(
            f"{role} init failed:\nstdout: {init_result.stdout}\nstderr: {init_result.stderr}"
        )

    # Route subprocess output to a logfile — an undrained PIPE buffer would
    # fill up as Flask logs each request, blocking the forge on write().
    forge_log = forge_dir / f".forge-{uuid.uuid4().hex[:8]}.log"
    proc = subprocess.Popen(
        [
            str(venv_python),
            "-m",
            meta["module"],
            "serve",
            "--keyring-service",
            test_ns,
            "--port",
            str(port),
        ],
        cwd=str(forge_dir),
        env=env,
        stdout=forge_log.open("w"),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    url = f"http://127.0.0.1:{port}"
    # 30s budget accommodates cold macOS arm64 GH-runner starts; locally
    # the forge is ready in <1s.
    deadline = time.monotonic() + 30.0
    pubkey_hex: str | None = None
    def _read_forge_log() -> str:
        try:
            return forge_log.read_text()
        except Exception:  # noqa: BLE001
            return "<no log captured>"

    while time.monotonic() < deadline:
        if proc.poll() is not None:
            try:
                keyring.delete_password(test_ns, meta["identity"])
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(
                f"{role} died during startup; rc={proc.returncode}; output:\n"
                f"{_read_forge_log()}"
            )
        try:
            resp = httpx.get(f"{url}/pubkey", timeout=1.0)
            if resp.status_code == 200:
                pubkey_hex = resp.json()["pubkey"]
                break
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    if pubkey_hex is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            keyring.delete_password(test_ns, meta["identity"])
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(
            f"{role} did not become ready within 30s on port {port}\n"
            f"output: {_read_forge_log()}"
        )
    try:
        yield ConformanceForgeHandle(
            url=url,
            pubkey_hex=pubkey_hex,
            role=role,
            namespace=test_ns,
            identity=meta["identity"],
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        try:
            forge_log.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        try:
            keyring.delete_password(test_ns, meta["identity"])
        except Exception:  # noqa: BLE001
            pass


@pytest.fixture(autouse=True)
def _force_real_keyring_backend() -> Generator[None, None, None]:
    """Force real macOS Keychain so cross-process tests work.

    Necessary because some pytest plugins or stray ``priority`` discoveries
    may install a non-macOS backend in the test process. The forge
    subprocess uses real Keychain; pubkey registrations from the test
    process need to be visible to it.
    """
    import keyring
    from keyring.backends import macOS as _macos_module

    previous = keyring.get_keyring()
    real_backend = _macos_module.Keyring()
    keyring.set_keyring(real_backend)
    try:
        yield
    finally:
        keyring.set_keyring(previous)
