"""AT-E3: Tool escape — v0.1 forges have no plugin/shell surface."""
# AT-SURFACE: AT-E3
from __future__ import annotations

from pathlib import Path

import pytest


_SEAMOUNT_ROOT = Path("/Users/dom/Projects/dom/seamount")


@pytest.mark.at_surface("AT-E3")
@pytest.mark.documents_only
def test_pi_forge_task_type_whitelist_is_closed() -> None:
    """pi-forge declares a closed task_type whitelist (envelope.py SUPPORTED_TASK_TYPES).

    The actual whitelist lives in pi-forge/envelope.py at
    `SUPPORTED_TASK_TYPES = {"data.compute"}`. We assert the whitelist
    exists, includes data.compute, and excludes obviously-dangerous task
    types that would indicate a plugin-escape regression.
    """
    env = _SEAMOUNT_ROOT / "pi-forge" / "envelope.py"
    assert env.is_file(), f"AT-E3: pi-forge envelope.py missing at {env}"
    txt = env.read_text()
    assert "SUPPORTED_TASK_TYPES" in txt and "data.compute" in txt, (
        "AT-E3: pi-forge must declare SUPPORTED_TASK_TYPES = {'data.compute'}"
    )
    forbidden = {"shell.exec", "eval", "plugin.load", "system.exec"}
    for tok in forbidden:
        assert tok not in txt, (
            f"AT-E3: pi-forge whitelist must not include {tok!r}"
        )


@pytest.mark.at_surface("AT-E3")
@pytest.mark.documents_only
def test_describe_forge_task_type_whitelist_is_closed() -> None:
    """describe-forge declares a closed task_type whitelist (envelope.py SUPPORTED_TASK_TYPES).

    describe-forge currently accepts ``shadow.describe`` and ``data.compute``
    per its envelope.py. The whitelist is a finite set, NOT an open
    plugin-loader contract.
    """
    env = _SEAMOUNT_ROOT / "describe-forge" / "envelope.py"
    assert env.is_file(), f"AT-E3: describe-forge envelope.py missing at {env}"
    txt = env.read_text()
    assert "SUPPORTED_TASK_TYPES" in txt, (
        "AT-E3: describe-forge must declare SUPPORTED_TASK_TYPES"
    )
    forbidden = {"shell.exec", "eval", "plugin.load", "system.exec"}
    for tok in forbidden:
        assert tok not in txt, (
            f"AT-E3: describe-forge whitelist must not include {tok!r}"
        )


@pytest.mark.at_surface("AT-E3")
@pytest.mark.documents_only
def test_forges_have_no_plugin_subprocess_surface() -> None:
    """AT-E3 structural defense: forges import no plugin / subprocess / shell modules."""
    forbidden = {"subprocess", "shlex", "pty", "ctypes.util.find_library", "importlib.util.spec_from_file_location"}
    for forge in ("pi-forge", "describe-forge"):
        src = _SEAMOUNT_ROOT / forge / "server.py"
        txt = src.read_text()
        for tok in forbidden:
            # subprocess imports in tests are fine; we only check server.py.
            assert tok not in txt, (
                f"AT-E3: {forge}/server.py must not import {tok!r}"
            )
