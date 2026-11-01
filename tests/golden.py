"""BootUI 2.2.0 golden loader (spec §6.1 item 1, council R9).

``assert_parity(sharpit_id, name, payload)`` checks ``payload`` against
``fixtures/bootui/2.2.0/<sharpit_id>/<name>.captured.json`` (a multi-endpoint panel), else ``captured.json``, else
``<name>.provisional.json`` / ``provisional.json`` (an :class:`UnverifiedParityWarning`: merges, counted unverified).
Every golden key must be present with a compatible JSON type; extra payload keys are allowed. A payload ``null`` where
the golden has a value passes only when ``nullable.json`` (``{"<path>": "<reason>"}``, list items as ``items[].key``)
lists the path with a non-empty reason. A golden ``null`` accepts any payload type.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent / "fixtures" / "bootui" / "2.2.0"


class UnverifiedParityWarning(UserWarning):
    """A payload was checked against a provisional fixture: it merges, but counts as unverified, not parity."""


def bootui_ids() -> dict[str, str]:
    """BootUI panel id -> sharpit panel id (``ids.json``)."""
    return json.loads((ROOT / "ids.json").read_text(encoding="utf-8"))


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _kind(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "null" if value is None else type(value).__name__


def _compare(expected: Any, actual: Any, path: str, nullable: Mapping[str, str], errors: list[str]) -> None:
    if expected is None:
        return
    label = path or "<root>"
    if actual is None:
        if path not in nullable:
            errors.append(f"{label}: null in payload, golden has {_kind(expected)}; not listed in nullable.json")
        return
    if _kind(expected) != _kind(actual):
        errors.append(f"{label}: payload is {_kind(actual)}, golden is {_kind(expected)}")
        return
    if isinstance(expected, Mapping):
        for key, value in expected.items():
            child = f"{path}.{key}" if path else key
            if key not in actual:
                errors.append(f"{child}: missing from payload")
            else:
                _compare(value, actual[key], child, nullable, errors)
    elif isinstance(expected, list) and expected:
        for item in actual:
            _compare(expected[0], item, f"{path}[]", nullable, errors)


def _fixture(folder: Path, name: str) -> tuple[Path, bool]:
    for candidate in (f"{name}.captured.json", "captured.json"):
        if (folder / candidate).is_file():
            return folder / candidate, True
    for candidate in (f"{name}.provisional.json", "provisional.json"):
        if (folder / candidate).is_file():
            return folder / candidate, False
    raise AssertionError(f"no golden fixture for {folder.name}/{name}: expected captured.json or provisional.json")


def assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None:
    folder = ROOT / sharpit_id
    path, captured = _fixture(folder, name)
    nullable_path = folder / "nullable.json"
    nullable: dict[str, Any] = _load(nullable_path) if nullable_path.is_file() else {}
    errors = [
        f"nullable.json {key}: reason must be a non-empty string"
        for key, why in nullable.items()
        if not (isinstance(why, str) and why.strip())
    ]
    _compare(_load(path), payload, "", nullable, errors)
    if errors:
        raise AssertionError(f"{sharpit_id}/{path.name} parity: " + "; ".join(errors))
    if not captured:
        warnings.warn(f"{sharpit_id}/{name}: provisional fixture, unverified", UnverifiedParityWarning, stacklevel=2)
