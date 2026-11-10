"""BootUI golden loader (spec §4.4, §6.1 item 1, council R9).

``assert_parity(sharpit_id, name, payload, fixture_version='2.2.0')`` checks ``payload`` against
the first of, under ``fixtures/bootui/<fixture_version>/<sharpit_id>/``:
``<name>.captured.json``, ``<name>.provisional.json``, ``captured.json``, ``provisional.json``
(a provisional one emits :class:`UnverifiedParityWarning`: merges, counted unverified).

Legacy default ``fixture_version='2.2.0'``. For 2.3.0 parity and matched rows, pass
``fixture_version='2.3.0'`` and ``matched=True`` (spec §4.4).

Every golden key (and catalog field, when specified) must be present with a compatible JSON type;
extra payload keys are allowed. A non-empty golden list requires a non-empty payload list.
A golden list keeps one item per distinct shape: a payload item passes when it matches any of them.
At a path (list items as ``items[].key``) a payload ``null`` passes when any golden item is ``null``
there or ``nullable.json`` (``{"<path>": "<reason>"}``) lists it with a non-empty reason, and any type
a golden item has there is accepted. A golden ``null`` accepts any type.
Wherever ``enums.json`` is present, enum values are verified.
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


class UnverifiedParityWarning(UserWarning):
    """A payload was checked against a provisional fixture: it merges, but counts as unverified, not parity."""


def _folder(sharpit_id: str, fixture_version: str) -> Path:
    if (ROOT / fixture_version).is_dir():
        base_dir = ROOT / fixture_version
    elif fixture_version == DEFAULT_FIXTURE_VERSION and (sharpit_id and (ROOT / sharpit_id).is_dir()):
        base_dir = ROOT
    elif ROOT != BOOTUI_FIXTURES_DIR / DEFAULT_FIXTURE_VERSION:
        base_dir = ROOT / fixture_version
    else:
        base_dir = BOOTUI_FIXTURES_DIR / fixture_version
    return base_dir / sharpit_id if sharpit_id else base_dir


def bootui_ids(fixture_version: str = DEFAULT_FIXTURE_VERSION) -> dict[str, str]:
    """BootUI panel id -> sharpit panel id (``ids.json``)."""
    ids_file = ROOT / "ids.json"
    if not ids_file.is_file():
        ids_file = BOOTUI_FIXTURES_DIR / fixture_version / "ids.json"
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
    catalog_fields: set[str] = field(default_factory=set[str])


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
    prefix = f"{path}." if path else ""
    for field_name in check.catalog_fields:
        if path and field_name.startswith(prefix):
            remainder = field_name[len(prefix) :]
            expected_keys.add(remainder.split(".")[0].split("[]")[0])
        elif not path:
            expected_keys.add(field_name.split(".")[0].split("[]")[0])

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
    # §4.4: a non-empty golden list of shapes requires a non-empty payload list
    if any(isinstance(shape, Mapping) for shape in shapes) and not actual:
        label = path or "<root>"
        check.errors.append(f"{label}: non-empty golden list requires a non-empty payload list")
        return
    for item in actual:
        tries: list[list[str]] = []
        for shape in shapes:
            attempt = _Check(check.nullable, check.kinds, catalog_fields=check.catalog_fields)
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


def _load_catalog_fields(folder: Path, catalog_fields: Iterable[str] | None) -> set[str]:
    catalog_set = set(catalog_fields) if catalog_fields else set()
    catalog_path = folder / "catalog.json"
    if catalog_path.is_file():
        cat_data = _load(catalog_path)
        if isinstance(cat_data, list):
            catalog_set |= set(cat_data)
        elif isinstance(cat_data, Mapping):
            catalog_set |= set(cat_data.get("requiredFields", cat_data.keys()))
    return catalog_set


def _check_enums(folder: Path, payload: Mapping[str, Any]) -> list[str]:
    enums_path = folder / "enums.json"
    if not enums_path.is_file():
        return []
    enums: dict[str, list[Any]] = _load(enums_path)
    leaves = _leaves(payload, "", [])
    return [f"{at}: {value!r} not in {enums[at]}" for at, value in leaves if at in enums and value not in enums[at]]


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
    check_enums: bool = True,
    version: str | None = None,
) -> None:
    """Check ``payload`` against BootUI golden fixture for ``sharpit_id``/``name``.

    Legacy default ``fixture_version='2.2.0'``. For 2.3.0 parity and matched rows,
    pass ``fixture_version='2.3.0'`` and ``matched=True`` (spec §4.4).
    """
    chosen_version = version if version is not None else fixture_version

    if matched and chosen_version != "2.3.0":
        raise AssertionError(
            f"{sharpit_id}/{name}: 2.2.0 fixture cannot satisfy 'matched' parity; "
            "version 2.3.0 golden required (spec §4.4)"
        )

    folder = _folder(sharpit_id, chosen_version)
    path, captured = _fixture(folder, name)
    nullable, errors = _validate_nullable(folder)
    expected = _load(path)
    catalog_set = _load_catalog_fields(folder, catalog_fields)

    check = _Check(nullable, _kinds(expected, "", {}), errors, catalog_fields=catalog_set)
    _compare(expected, payload, "", check)

    if check_enums:
        errors.extend(_check_enums(folder, payload))

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
