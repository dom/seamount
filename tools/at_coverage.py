#!/usr/bin/env python3
"""AT-E* coverage gate for seamount (AT-E1..E5).

Globs seamount/conformance/at_negative/test_at_e*.py and asserts
all five AT-E surfaces have at least one test file.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

EXPECTED: frozenset[str] = frozenset({"AT-E1", "AT-E2", "AT-E3", "AT-E4", "AT-E5"})
PATTERN = re.compile(r"^test_at_e(\d+)_")
ROOT = Path(__file__).resolve().parents[1] / "conformance" / "at_negative"


def main() -> int:
    if not ROOT.is_dir():
        print(f"FAIL: {ROOT} does not exist", file=sys.stderr)
        return 1
    found: set[str] = set()
    for p in sorted(ROOT.glob("test_at_*.py")):
        m = PATTERN.match(p.name.lower())
        if m:
            found.add(f"AT-E{m.group(1)}")
    missing = EXPECTED - found
    if missing:
        print(f"FAIL: missing AT-E coverage: {sorted(missing)}", file=sys.stderr)
        return 1
    print(f"ok: AT-E coverage complete ({len(found)}/5).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
