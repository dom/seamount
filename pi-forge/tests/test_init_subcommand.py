"""CLI-level smoke test for `python -m pi_forge init` (Task 2 Test 7)."""
from __future__ import annotations

import subprocess
import sys
import uuid

import keyring
import pytest


def test_init_subcommand_creates_keystore_entry():
    """`python -m pi_forge init` exits 0 and creates a keypair under the namespace."""
    service = f"seamount.piforge.test-{uuid.uuid4()}"
    rc = subprocess.run(
        [sys.executable, "-m", "pi_forge", "init",
         "--keyring-service", service, "--identity", "pi-forge"],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0, f"init failed: {rc.stderr}"
    assert "Keypair created" in rc.stdout
    # Verify the entry actually exists in the keystore.
    from thermocline.identity import BrineProvider
    provider = BrineProvider(keyring_service=service)
    pub = provider.public_key(identity="pi-forge")
    assert len(pub) == 32
    try:
        keyring.delete_password(service, "pi-forge")
    except Exception:
        pass
