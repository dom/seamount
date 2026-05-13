"""Fixture loader: walk thermocline/conformance/{valid,invalid}/ + MANIFEST.yaml."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

import yaml

_SUITE_ROOT = Path(
    os.environ.get(
        "THERMOCLINE_SUITE_ROOT",
        str(Path.home() / "Projects" / "dom"),
    )
)
_CONFORMANCE_ROOT_DEFAULT = (
    _SUITE_ROOT / "thermocline" / "thermocline" / "conformance"
)


def load_fixtures(
    root: Path | None = None, category: str = "valid"
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(fixture_name, fixture_dict)`` tuples for ``category`` in {valid, invalid}."""
    root = root or _CONFORMANCE_ROOT_DEFAULT
    cat_dir = root / category
    if not cat_dir.exists():
        return
    for path in sorted(cat_dir.glob("*.json")):
        with path.open() as f:
            yield (path.name, json.load(f))


def load_manifest(root: Path | None = None) -> dict[str, Any]:
    """Load thermocline/conformance/MANIFEST.yaml."""
    root = root or _CONFORMANCE_ROOT_DEFAULT
    manifest_path = root / "MANIFEST.yaml"
    if not manifest_path.exists():
        return {}
    with manifest_path.open() as f:
        return yaml.safe_load(f) or {}


__all__ = ["load_fixtures", "load_manifest"]
