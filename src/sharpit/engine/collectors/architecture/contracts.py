"""Import-linter contracts reader from pyproject.toml (spec §5.5)."""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sharpit.engine.appsource import as_dict, as_str_tuple, find_pyproject_path


@dataclass(frozen=True)
class Contract:
    name: str
    contract_type: str  # "layers" | "forbidden"
    layers: tuple[str, ...] = ()
    source_modules: tuple[str, ...] = ()
    forbidden_modules: tuple[str, ...] = ()


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

    tool = as_dict(data.get("tool"))
    importlinter = as_dict(tool.get("importlinter"))
    raw_contracts = importlinter.get("contracts")
    if not isinstance(raw_contracts, list):
        return [], []

    contracts: list[Contract] = []
    for raw_item in cast("list[object]", raw_contracts):
        if not isinstance(raw_item, dict):
            continue
        raw = as_dict(cast("object", raw_item))
        name = str(raw.get("name", "unnamed"))
        c_type = str(raw.get("type", ""))
        layers = as_str_tuple(raw.get("layers"))
        source_modules = as_str_tuple(raw.get("source_modules"))
        forbidden_modules = as_str_tuple(raw.get("forbidden_modules"))
        contracts.append(Contract(name, c_type, layers, source_modules, forbidden_modules))

    return contracts, []
