"""Test 10: describe-forge init twice → both exit 0 (idempotent)."""
from __future__ import annotations

import subprocess
import sys
import uuid

import keyring


def test_init_idempotent():
    """describe-forge init twice with same identity → both succeed; second is no-op."""
    service = f"seamount.describeforge.test-{uuid.uuid4()}"
    identity = "describe-forge"
    rc1 = subprocess.run(
        [sys.executable, "-m", "describe_forge", "init",
         "--keyring-service", service, "--identity", identity],
        capture_output=True, text=True,
    )
    assert rc1.returncode == 0, f"first init failed: {rc1.stderr}"
    assert "Keypair created" in rc1.stdout

    rc2 = subprocess.run(
        [sys.executable, "-m", "describe_forge", "init",
         "--keyring-service", service, "--identity", identity],
        capture_output=True, text=True,
    )
    assert rc2.returncode == 0, f"second init failed: {rc2.stderr}"
    assert "already exists" in rc2.stdout or "no-op" in rc2.stdout

    try:
        keyring.delete_password(service, identity)
    except Exception:
        pass
