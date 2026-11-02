"""BootUI 2.2.0 golden loader (spec §6.1 item 1, council R9).

``assert_parity(sharpit_id, name, payload)`` checks ``payload`` against the first of, under
``fixtures/bootui/2.2.0/<sharpit_id>/``: ``<name>.captured.json``, ``<name>.provisional.json``, ``captured.json``,
``provisional.json`` (a provisional one emits :class:`UnverifiedParityWarning`: merges, counted unverified).
Every golden key must be present with a compatible JSON type; extra payload keys are allowed. A golden list keeps one
item per distinct shape: a payload item passes when it matches any of them. At a path (list items as ``items[].key``)
a payload ``null`` passes when any golden item is ``null`` there or ``nullable.json`` (``{"<path>": "<reason>"}``)
lists it with a non-empty reason, and any type a golden item has there is accepted. A golden ``null`` accepts any type.
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


def _kinds(golden: Any, path: str, out: dict[str, set[str]]) -> dict[str, set[str]]:
    """Every JSON kind the golden holds at each path, across all items of every list (``items[].key``)."""
    out.setdefault(path, set()).add(_kind(golden))
    if isinstance(golden, Mapping):
        for key, value in golden.items():
            _kinds(value, f"{path}.{key}" if path else key, out)
    elif isinstance(golden, list):
        for item in golden:
            _kinds(item, f"{path}[]", out)
    return out


def _compare(  # noqa: C901 - one rule per branch, each documented in the module docstring
    expected: Any, actual: Any, path: str, nullable: Mapping[str, str], kinds: Mapping[str, set[str]], errors: list[str]
) -> None:
    if expected is None:
        return
    label = path or "<root>"
    seen = kinds.get(path, set())
    if actual is None:
        if path not in nullable and "null" not in seen:
            errors.append(f"{label}: null in payload, golden has {_kind(expected)}; not listed in nullable.json")
        return
    if _kind(expected) != _kind(actual):
        if _kind(actual) not in seen:  # another golden item at this path has the payload's type
            errors.append(f"{label}: payload is {_kind(actual)}, golden is {_kind(expected)}")
        return
    if isinstance(expected, Mapping):
        for key, value in expected.items():
            child = f"{path}.{key}" if path else key
            if key not in actual:
                errors.append(f"{child}: missing from payload")
            else:
                _compare(value, actual[key], child, nullable, kinds, errors)
    elif isinstance(expected, list) and expected:
        for item in actual:  # an item passes when it matches any golden shape; else report the closest one
            tries: list[list[str]] = []
            for shape in expected:
                found: list[str] = []
                _compare(shape, item, f"{path}[]", nullable, kinds, found)
                tries.append(found)
            if all(tries):
                errors.extend(min(tries, key=len))


def _fixture(folder: Path, name: str) -> tuple[Path, bool]:
    order = ((f"{name}.captured.json", True), (f"{name}.provisional.json", False))
    order += (("captured.json", True), ("provisional.json", False))  # name-specific first, then the shared pair
    for candidate, captured in order:
        if (folder / candidate).is_file():
            return folder / candidate, captured
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
    expected = _load(path)
    _compare(expected, payload, "", nullable, _kinds(expected, "", {}), errors)
    if errors:
        raise AssertionError(f"{sharpit_id}/{path.name} parity: " + "; ".join(errors))
    if not captured:
        warnings.warn(f"{sharpit_id}/{name}: provisional fixture, unverified", UnverifiedParityWarning, stacklevel=2)
