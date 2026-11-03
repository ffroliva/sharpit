"""Import-linter contracts reader from pyproject.toml (spec §5.5)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Contract:
    name: str
    contract_type: str  # "layers" | "forbidden"
    layers: tuple[str, ...] = ()
    source_modules: tuple[str, ...] = ()
    forbidden_modules: tuple[str, ...] = ()


def find_pyproject_path(package_root: Path, sys_path: Sequence[object] = ()) -> Path | None:
    """Find pyproject.toml in the sys.path entry holding package_root or its parent (for src/ layout)."""
    del package_root, sys_path
    return None


def read_contracts(package_root: Path, sys_path: Sequence[object] = ()) -> tuple[list[Contract], list[str]]:
    """Skeleton: returns empty contracts and limitations."""
    del package_root, sys_path
    return [], []
