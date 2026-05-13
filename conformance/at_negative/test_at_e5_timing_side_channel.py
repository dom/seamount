"""AT-E5: Timing side channels — forges MUST use coarse-grained logging only.

Failure mode: an adversary measures forge response latency to infer
properties of the input (e.g., dictionary size, key prefix). Mitigation:
forges log only coarse-grained timing (>=ms), never nanosecond timers
that could leak fine-grained signal.
"""
# AT-SURFACE: AT-E5
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest


_SUITE_ROOT = Path(
    os.environ.get(
        "THERMOCLINE_SUITE_ROOT",
        str(Path.home() / "Projects" / "dom"),
    )
)
_SEAMOUNT_ROOT = _SUITE_ROOT / "seamount"
_FORBIDDEN_TIMERS = {
    "perf_counter_ns",
    "monotonic_ns",
    "process_time_ns",
    "time_ns",
}


def _scan_forge_for_timers(forge: str) -> list[tuple[str, int, str]]:
    """AST-walk forge .py files; return (path, lineno, attribute) of fine timers."""
    findings: list[tuple[str, int, str]] = []
    forge_dir = _SEAMOUNT_ROOT / forge
    for py in forge_dir.rglob("*.py"):
        # Skip vendored / tests
        s = py.as_posix()
        if "/.venv/" in s or "/site-packages/" in s or "/tests/" in s:
            continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_TIMERS:
                findings.append((str(py), node.lineno, node.attr))
    return findings


@pytest.mark.at_surface("AT-E5")
@pytest.mark.documents_only
def test_pi_forge_no_fine_grained_timing() -> None:
    """pi-forge uses no nanosecond timers (perf_counter_ns, monotonic_ns, etc.)."""
    findings = _scan_forge_for_timers("pi-forge")
    assert not findings, (
        f"AT-E5: pi-forge uses fine-grained timers: {findings!r}"
    )


@pytest.mark.at_surface("AT-E5")
@pytest.mark.documents_only
def test_describe_forge_no_fine_grained_timing() -> None:
    """describe-forge uses no nanosecond timers."""
    findings = _scan_forge_for_timers("describe-forge")
    assert not findings, (
        f"AT-E5: describe-forge uses fine-grained timers: {findings!r}"
    )
