"""Import-linter contracts reader from pyproject.toml (spec §5.5)."""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class Contract:
    name: str
    contract_type: str  # "layers" | "forbidden"
    layers: tuple[str, ...] = ()
    source_modules: tuple[str, ...] = ()
    forbidden_modules: tuple[str, ...] = ()


def find_pyproject_path(package_root: Path, sys_path: Sequence[object] = ()) -> Path | None:
    """The ``pyproject.toml`` of the sys.path entry holding ``package_root``, or that entry's parent for a src/ layout.

    Spec §5.5, §14: nowhere else. The holding entry is the root's own parent directory; an ancestor entry does not
    hold the package, and nothing is read when the holding entry is not on ``sys_path``.
    """
    try:
        holder = package_root.resolve().parent
        on_path = any(isinstance(e, str) and e and Path(e).resolve() == holder for e in sys_path)
    except (OSError, ValueError):
        return None
    if not on_path:
        return None
    candidates = [holder / "pyproject.toml"]
    if holder.name == "src":
        candidates.append(holder.parent / "pyproject.toml")
    return next((c for c in candidates if c.is_file()), None)


def _as_dict(val: object) -> dict[str, object]:
    if isinstance(val, dict):
        d = cast("dict[object, object]", val)
        return {str(k): v for k, v in d.items()}
    return {}


def _as_str_tuple(val: object) -> tuple[str, ...]:
    if isinstance(val, (list, tuple)):
        s = cast("Sequence[object]", val)
        return tuple(str(x) for x in s)
    return ()


def read_contracts(package_root: Path, sys_path: Sequence[object] = ()) -> tuple[list[Contract], list[str]]:
    """Read [tool.importlinter] contracts from pyproject.toml."""
    pyproject_path = find_pyproject_path(package_root, sys_path)
    if pyproject_path is None:
        return [], []

    try:
        with open(pyproject_path, "rb") as handle:
            data = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return [], [f"pyproject.toml: {exc}"]

    tool = _as_dict(data.get("tool"))
    importlinter = _as_dict(tool.get("importlinter"))
    raw_contracts = importlinter.get("contracts")
    if not isinstance(raw_contracts, list):
        return [], []

    contracts: list[Contract] = []
    for raw_item in cast("list[object]", raw_contracts):
        if not isinstance(raw_item, dict):
            continue
        raw = _as_dict(cast("object", raw_item))
        name = str(raw.get("name", "unnamed"))
        c_type = str(raw.get("type", ""))
        layers = _as_str_tuple(raw.get("layers"))
        source_modules = _as_str_tuple(raw.get("source_modules"))
        forbidden_modules = _as_str_tuple(raw.get("forbidden_modules"))
        contracts.append(Contract(name, c_type, layers, source_modules, forbidden_modules))

    return contracts, []
