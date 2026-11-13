"""BootUI golden loader (spec §4.4, §6.1 item 1, council R9).

``assert_parity(sharpit_id, name, payload, fixture_version='2.2.0')`` checks ``payload`` against
the first of, under ``fixtures/bootui/<fixture_version>/<sharpit_id>/``:
``<name>.captured.json``, ``<name>.provisional.json``, ``captured.json``, ``provisional.json``
(a provisional one emits :class:`UnverifiedParityWarning`: merges, counted unverified).

Legacy default ``fixture_version='2.2.0'``. For 2.3.0 parity and matched rows, pass
``fixture_version='2.3.0'`` and ``matched=True`` (spec §4.4).

Every golden key (and catalog field under 2.3.0) must be present with a compatible JSON type;
extra payload keys are allowed. Under 2.3.0, a non-empty golden list requires a non-empty payload list.
A golden list keeps one item per distinct shape: a payload item passes when it matches any of them.
At a path (list items as ``items[].key``) a payload ``null`` passes when any golden item is ``null``
there or ``nullable.json`` (``{"<path>": "<reason>"}``) lists it with a non-empty reason, and any type
a golden item has there is accepted. A golden ``null`` accepts any type.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

BOOTUI_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "bootui"
DEFAULT_FIXTURE_VERSION = "2.2.0"
ROOT = BOOTUI_FIXTURES_DIR / DEFAULT_FIXTURE_VERSION
_INITIAL_ROOT = ROOT


class UnverifiedParityWarning(UserWarning):
    """A payload was checked against a provisional fixture: it merges, but counts as unverified, not parity."""


def _folder(sharpit_id: str, fixture_version: str) -> Path:
    if ROOT != _INITIAL_ROOT:
        return ROOT / fixture_version / sharpit_id
    return BOOTUI_FIXTURES_DIR / fixture_version / sharpit_id


def bootui_ids(fixture_version: str = DEFAULT_FIXTURE_VERSION) -> dict[str, str]:
    """BootUI panel id -> sharpit panel id (``ids.json``)."""
    ids_file = BOOTUI_FIXTURES_DIR / fixture_version / "ids.json"
    if not ids_file.is_file():
        raise AssertionError(f"no ids.json for fixture version {fixture_version}: missing file {ids_file}")
    return json.loads(ids_file.read_text(encoding="utf-8"))


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
        for key, value in cast("Mapping[str, Any]", golden).items():
            _kinds(value, f"{path}.{key}" if path else key, out)
    elif isinstance(golden, list):
        for item in cast("list[Any]", golden):
            _kinds(item, f"{path}[]", out)
    return out


@dataclass
class _Check:
    nullable: Mapping[str, str]
    kinds: Mapping[str, set[str]]
    errors: list[str] = field(default_factory=list[str])
    shapeless: list[str] = field(default_factory=list[str])  # golden lists with no item shape: unchecked, warned
    catalog_by_path: Mapping[str, set[str]] = field(default_factory=dict[str, set[str]])
    is_23: bool = False


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
    expected_keys = set(expected.keys())
    if path in check.catalog_by_path:
        expected_keys |= check.catalog_by_path[path]

    for key in sorted(expected_keys):
        child = f"{path}.{key}" if path else key
        if key not in actual:
            check.errors.append(f"{child}: missing from payload")
        elif key in expected:
            _compare(expected[key], actual[key], child, check)


def _compare_list(expected: list[Any], actual: list[Any], path: str, check: _Check) -> None:
    """An item passes when it matches any golden shape; else the closest shape's errors are reported."""
    shapes = [shape for shape in expected if shape is not None]
    if not shapes:  # an empty or null-only golden list says nothing about item shape
        if actual and path not in check.shapeless:
            check.shapeless.append(path)
        return
    # §4.4: a non-empty golden list of shapes requires a non-empty payload list (2.3.0 only)
    if check.is_23 and shapes and not actual:
        label = path or "<root>"
        check.errors.append(f"{label}: non-empty golden list requires a non-empty payload list")
        return
    for item in actual:
        tries: list[list[str]] = []
        for shape in shapes:
            attempt = _Check(check.nullable, check.kinds, catalog_by_path=check.catalog_by_path, is_23=check.is_23)
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
    expected_file = folder / (f"{name}.captured.json" if name != "captured" else "captured.json")
    raise AssertionError(
        f"no golden fixture for {folder.name}/{name}: missing file {expected_file} "
        f"(expected captured.json or provisional.json under {folder})"
    )


def _validate_nullable(folder: Path) -> tuple[dict[str, Any], list[str]]:
    nullable_path = folder / "nullable.json"
    nullable: dict[str, Any] = _load(nullable_path) if nullable_path.is_file() else {}
    errors = [
        f"nullable.json {key}: reason must be a non-empty string"
        for key, why in nullable.items()
        if not (isinstance(why, str) and why.strip())
    ]
    return nullable, errors


def _catalog_from_file(folder: Path) -> list[str]:
    catalog_path = folder / "catalog.json"
    if not catalog_path.is_file():
        return []
    cat_data: Any = _load(catalog_path)
    if isinstance(cat_data, list):
        return [item for item in cast("list[object]", cat_data) if isinstance(item, str)]
    if isinstance(cat_data, Mapping):
        cat_map = cast("Mapping[str, object]", cat_data)
        req = cat_map.get("requiredFields")
        if isinstance(req, list):
            return [item for item in cast("list[object]", req) if isinstance(item, str)]
        return [str(k) for k in cat_map]
    return []


def _load_catalog_fields(folder: Path, catalog_fields: Iterable[str] | None) -> dict[str, set[str]]:
    by_path: dict[str, set[str]] = {}
    raw_fields: list[str] = list(catalog_fields) if catalog_fields is not None else []
    raw_fields.extend(_catalog_from_file(folder))

    for raw in raw_fields:
        clean = raw.strip()
        current_path = ""
        for segment in clean.split("."):
            if segment:
                key = segment.removesuffix("[]")
                by_path.setdefault(current_path, set()).add(key)
                current_path = f"{current_path}.{segment}" if current_path else segment

    return by_path


def _check_warnings_and_parity(
    check: _Check,
    captured: bool,
    sharpit_id: str,
    name: str,
    matched: bool,
) -> None:
    for path_ in check.shapeless:
        message = (
            f"{sharpit_id}/{name}: golden list {path_ or '<root>'} has no shape information; its items are unchecked"
        )
        if matched:
            raise AssertionError(
                f"{sharpit_id}/{name}: golden list {path_ or '<root>'} has no shape information; "
                "cannot satisfy 2.3.0 'matched' parity (spec §4.4)"
            )
        warnings.warn(message, UnverifiedParityWarning, stacklevel=3)

    if not captured:
        if matched:
            raise AssertionError(
                f"{sharpit_id}/{name}: provisional fixture cannot satisfy 2.3.0 'matched' parity (spec §4.4)"
            )
        warnings.warn(f"{sharpit_id}/{name}: provisional fixture, unverified", UnverifiedParityWarning, stacklevel=3)


def assert_parity(
    sharpit_id: str,
    name: str,
    payload: Mapping[str, Any],
    fixture_version: str = DEFAULT_FIXTURE_VERSION,
    *,
    matched: bool = False,
    catalog_fields: Iterable[str] | None = None,
) -> None:
    """Check ``payload`` against BootUI golden fixture for ``sharpit_id``/``name``.

    Legacy default ``fixture_version='2.2.0'``. For 2.3.0 parity and matched rows,
    pass ``fixture_version='2.3.0'`` and ``matched=True`` (spec §4.4).
    """
    is_23 = fixture_version == "2.3.0"
    if matched and not is_23:
        raise AssertionError(
            f"{sharpit_id}/{name}: 2.2.0 fixture cannot satisfy 'matched' parity; "
            "version 2.3.0 golden required (spec §4.4)"
        )

    folder = _folder(sharpit_id, fixture_version)
    path, captured = _fixture(folder, name)
    nullable, errors = _validate_nullable(folder)
    expected = _load(path)
    catalog_by_path = _load_catalog_fields(folder, catalog_fields) if is_23 else {}

    check = _Check(
        nullable=nullable,
        kinds=_kinds(expected, "", {}),
        errors=errors,
        catalog_by_path=catalog_by_path,
        is_23=is_23,
    )
    _compare(expected, payload, "", check)

    if errors:
        raise AssertionError(f"{sharpit_id}/{path.name} parity: " + "; ".join(errors))

    _check_warnings_and_parity(check, captured, sharpit_id, name, matched)


def _leaves(value: Any, path: str, out: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """Every scalar in ``value`` with its path (list items as ``items[].key``, as in ``nullable.json``)."""
    if isinstance(value, Mapping):
        for key, child in cast("Mapping[str, Any]", value).items():
            _leaves(child, f"{path}.{key}" if path else key, out)
    elif isinstance(value, list):
        for item in cast("list[Any]", value):
            _leaves(item, f"{path}[]", out)
    else:
        out.append((path, value))
    return out


def assert_enum_values(
    sharpit_id: str,
    name: str,
    payload: Mapping[str, Any],
    fixture_version: str = DEFAULT_FIXTURE_VERSION,
) -> None:
    """Every value at a path ``<sharpit_id>/enums.json`` (``{"<path>": [allowed, ...]}``) lists is an allowed one.

    ``assert_parity`` checks keys and types only, so a wrong status string (``FAILED`` for ``VIOLATION``) passes it."""
    path = _folder(sharpit_id, fixture_version) / "enums.json"
    if not path.is_file():
        raise AssertionError(f"no enum values for {sharpit_id}/{name}: expected {path.name}")
    enums: dict[str, list[Any]] = _load(path)
    leaves = _leaves(payload, "", [])
    errors = [f"{at}: {value!r} not in {enums[at]}" for at, value in leaves if at in enums and value not in enums[at]]
    if errors:
        raise AssertionError(f"{sharpit_id}/{name} enum values: " + "; ".join(errors))
