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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

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


@dataclass
class _Check:
    nullable: Mapping[str, str]
    kinds: Mapping[str, set[str]]
    errors: list[str] = field(default_factory=list[str])
    shapeless: list[str] = field(default_factory=list[str])  # golden lists with no item shape: unchecked, warned


def _compare(expected: Any, actual: Any, path: str, check: _Check) -> None:
    """Null and type rules at one path, then the object or list rules below it."""
    if expected is None:
        return
    label = path or "<root>"
    seen = check.kinds.get(path, set())
    if actual is None:
        if path not in check.nullable and "null" not in seen:
            check.errors.append(f"{label}: null in payload, golden has {_kind(expected)}; not listed in nullable.json")
    elif _kind(expected) != _kind(actual):
        if _kind(actual) not in seen:  # another golden item at this path has the payload's type
            check.errors.append(f"{label}: payload is {_kind(actual)}, golden is {_kind(expected)}")
    elif isinstance(expected, Mapping):
        _compare_object(cast("Mapping[str, Any]", expected), actual, path, check)
    elif isinstance(expected, list):
        _compare_list(cast("list[Any]", expected), actual, path, check)


def _compare_object(expected: Mapping[str, Any], actual: Mapping[str, Any], path: str, check: _Check) -> None:
    for key, value in expected.items():
        child = f"{path}.{key}" if path else key
        if key not in actual:
            check.errors.append(f"{child}: missing from payload")
        else:
            _compare(value, actual[key], child, check)


def _compare_list(expected: list[Any], actual: list[Any], path: str, check: _Check) -> None:
    """An item passes when it matches any golden shape; else the closest shape's errors are reported."""
    shapes = [shape for shape in expected if shape is not None]
    if not shapes:  # an empty or null-only golden list says nothing about item shape
        if actual and path not in check.shapeless:
            check.shapeless.append(path)
        return
    for item in actual:
        tries: list[list[str]] = []
        for shape in shapes:
            attempt = _Check(check.nullable, check.kinds)
            _compare(shape, item, f"{path}[]", attempt)
            tries.append(attempt.errors)
            check.shapeless.extend(p for p in attempt.shapeless if p not in check.shapeless)
        if all(tries):
            check.errors.extend(min(tries, key=len))


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
    check = _Check(nullable, _kinds(expected, "", {}), errors)
    _compare(expected, payload, "", check)
    if errors:
        raise AssertionError(f"{sharpit_id}/{path.name} parity: " + "; ".join(errors))
    for path_ in check.shapeless:
        message = (
            f"{sharpit_id}/{name}: golden list {path_ or '<root>'} has no shape information; its items are unchecked"
        )
        warnings.warn(message, UnverifiedParityWarning, stacklevel=2)
    if not captured:
        warnings.warn(f"{sharpit_id}/{name}: provisional fixture, unverified", UnverifiedParityWarning, stacklevel=2)


def assert_enum_values(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None:
    """Every value at a path ``<sharpit_id>/enums.json`` lists is one of its allowed values (skeleton)."""
