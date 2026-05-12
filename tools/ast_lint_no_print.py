#!/usr/bin/env python3
"""AST lint forbidding `print(` in library code (CONF-06 / D-09).

Allows print only in:
  - CLI entry points (click.echo elsewhere; forge init/serve scripts use print)
  - Lint tools and scripts (dev/CI tooling)
  - Test files (tests/)
  - Example files (examples/)
  - Forge entry points (5 contractual sites; PIFORGE_READY / DESCRIBEFORGE_READY)
"""
from __future__ import annotations
import ast
import sys
from pathlib import Path

PROTECTED_FRAGMENTS: tuple[str, ...] = (
    "/src/thermocline/",
    "/src/photophore/",
)
ALLOWED_FRAGMENTS: tuple[str, ...] = (
    "/src/thermocline/scripts/",
    "/src/photophore/cli/",
    "/tests/",
    "/examples/",
)
# CONFLICT-03 (Phase 4 RESEARCH.md): five contractual print() call-sites in the
# forges are allow-listed. They collapse into FOUR unique file paths because
# the startup-banner print is emitted from the same server.py files as the
# PIFORGE_READY / DESCRIBE_FORGE_READY readiness signals:
#   - pi-forge/server.py            (PIFORGE_READY + startup banner)
#   - pi-forge/pi_forge/__main__.py  (CLI entry banner)
#   - describe-forge/server.py       (DESCRIBE_FORGE_READY + startup banner)
#   - describe-forge/describe_forge/__main__.py  (CLI entry banner)
# Keep this list at FOUR entries; the fifth contractual print is co-located
# in pi-forge/server.py (PIFORGE_READY + banner share one allow-listed file).
ALLOWED_FORGE_FRAGMENTS: tuple[str, ...] = (
    "/pi-forge/server.py",
    "/pi-forge/pi_forge/__main__.py",
    "/describe-forge/server.py",
    "/describe-forge/describe_forge/__main__.py",
)
# Skip vendored / installed third-party code. Library-code lint MUST never
# inspect the active virtualenv, build artifacts, or egg-info directories.
SKIP_FRAGMENTS: tuple[str, ...] = (
    "/.venv/",
    "/venv/",
    "/site-packages/",
    "/.tox/",
    "/build/",
    "/dist/",
    "/.eggs/",
    ".egg-info/",
    "/__pycache__/",
    "/.git/",
    "/node_modules/",
)


def is_skipped(path: Path) -> bool:
    s = path.as_posix()
    return any(frag in s for frag in SKIP_FRAGMENTS)


def is_allowed(path: Path) -> bool:
    s = path.as_posix()
    if any(frag in s for frag in ALLOWED_FRAGMENTS):
        return True
    if any(s.endswith(frag) for frag in ALLOWED_FORGE_FRAGMENTS):
        return True
    return False


def is_protected(path: Path) -> bool:
    s = path.as_posix()
    if any(frag in s for frag in PROTECTED_FRAGMENTS):
        return True
    if any(s.endswith(frag) for frag in ALLOWED_FORGE_FRAGMENTS):
        return False  # forges have no /src/, treat as allowed not protected
    # Forge non-allow-listed Python files are still protected (CONF-06 applies
    # to all library code). Match forge package directories by path fragment.
    forge_protected_fragments = (
        "/pi-forge/",
        "/describe-forge/",
    )
    if any(frag in s for frag in forge_protected_fragments):
        return True
    return False


class _PrintVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[int] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self.findings.append(node.lineno)
        self.generic_visit(node)


def check_file(path: Path) -> list[tuple[Path, int]]:
    if is_skipped(path):
        return []
    if is_allowed(path) or not is_protected(path):
        return []
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []
    v = _PrintVisitor()
    v.visit(tree)
    return [(path, ln) for ln in v.findings]


def scan(roots: list[Path]) -> list[tuple[Path, int]]:
    out: list[tuple[Path, int]] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            out.extend(check_file(root))
        elif root.is_dir():
            for p in root.rglob("*.py"):
                if is_skipped(p):
                    continue
                out.extend(check_file(p))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    roots = [Path(a).resolve() for a in argv] if argv else [Path.cwd()]
    findings = scan(roots)
    if findings:
        for path, lineno in findings:
            print(f"FAIL: print( call in {path}:{lineno}", file=sys.stderr)
        return 1
    print("ok: no print( in library code", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
