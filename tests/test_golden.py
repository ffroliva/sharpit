"""Contract of the BootUI 2.2.0 golden loader (``tests/golden.py``) and the id map (spec §6.1 item 1, §6.2)."""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import golden
from conftest import golden as legacy_golden
from golden import UnverifiedParityWarning, assert_enum_values, assert_parity, bootui_ids
from sharpit.engine.panels import PANELS


@pytest.fixture
def fixtures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(golden, "BOOTUI_FIXTURES_DIR", tmp_path)
    return tmp_path


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _parity_error(
    sharpit_id: str,
    name: str,
    payload: Mapping[str, Any],
    *args: Any,
    **kwargs: Any,
) -> str | None:
    try:
        assert_parity(sharpit_id, name, payload, *args, **kwargs)
    except AssertionError as exc:
        return str(exc)
    return None


def test_golden_id_mapping_covers_panel_ids() -> None:
    ids = bootui_ids()
    # the legacy capture predates BootUI 2.3.0's new panels (runtime-insights): those come from the 2.3.0 enumeration
    bootui_23 = json.loads((golden.BOOTUI_FIXTURES_DIR / "2.3.0" / "panels.json").read_text(encoding="utf-8"))
    bootui_panel_ids = {panel["id"] for panel in (*legacy_golden("panels")["panels"], *bootui_23["panels"])}
    assert set(ids.values()) == {panel.id for panel in PANELS}
    assert set(ids) <= bootui_panel_ids
    assert ids["hibernate-statistics"] == "sqlalchemy-statistics"
    assert ids["spring-security"] == "fastapi-security"
    assert ids["spring"] == "fastapi"
    assert ids["flyway"] == "alembic"
    assert ids["postgresql"] == "postgresql"


def test_golden_loader_reads_nullable_reasons(fixtures: Path) -> None:
    _write(fixtures / "2.2.0" / "data" / "captured.json", {"name": "orders", "rows": 3, "items": [{"count": 1}]})
    payload = {"name": "orders", "rows": None, "items": [{"count": None}]}

    no_reason = _parity_error("data", "data", payload)
    assert no_reason is not None
    assert "rows" in no_reason

    _write(fixtures / "2.2.0" / "data" / "nullable.json", {"rows": "no row estimate", "items[].count": "no counter"})
    assert _parity_error("data", "data", payload) is None

    _write(fixtures / "2.2.0" / "data" / "nullable.json", {"rows": "", "items[].count": "no counter"})
    empty_reason = _parity_error("data", "data", payload)
    assert empty_reason is not None
    assert "reason" in empty_reason


def test_provisional_fixture_is_not_counted_as_parity(fixtures: Path) -> None:
    _write(fixtures / "2.2.0" / "traces" / "provisional.json", {"traces": []})
    with warnings.catch_warnings(record=True) as provisional:
        warnings.simplefilter("always")
        assert_parity("traces", "traces", {"traces": []})
    assert [w.category for w in provisional] == [UnverifiedParityWarning]

    _write(fixtures / "2.2.0" / "traces" / "captured.json", {"traces": []})
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        assert_parity("traces", "traces", {"traces": []})
    assert [w.category for w in captured] == []


def test_golden_loader_rejects_missing_key_and_wrong_type(fixtures: Path) -> None:
    _write(
        fixtures / "2.2.0" / "postgresql" / "captured.json", {"version": "16", "sessions": [{"pid": 1, "idle": True}]}
    )

    missing = _parity_error("postgresql", "postgresql", {"sessions": []})
    assert missing is not None
    assert "version" in missing

    wrong_type = _parity_error("postgresql", "postgresql", {"version": "16", "sessions": [{"pid": "1", "idle": True}]})
    assert wrong_type is not None
    assert "sessions[].pid" in wrong_type

    extra_keys = {"version": "16", "sessions": [{"pid": 1, "idle": False, "extra": 2}], "more": 1.5}
    assert _parity_error("postgresql", "postgresql", extra_keys) is None


def test_golden_loader_prefers_named_capture(fixtures: Path) -> None:
    _write(fixtures / "2.2.0" / "postgresql" / "captured.json", {"version": "16"})
    _write(fixtures / "2.2.0" / "postgresql" / "sessions.captured.json", {"sessions": []})

    named = _parity_error("postgresql", "sessions", {"version": "16"})
    assert named is not None
    assert "sessions" in named
    assert _parity_error("postgresql", "postgresql", {"version": "16"}) is None


def test_golden_loader_requires_a_fixture(fixtures: Path) -> None:
    absent = _parity_error("mysql", "mysql", {})
    assert absent is not None
    assert "mysql" in absent


def test_assert_parity_requires_23_golden_for_matched_rows(fixtures: Path) -> None:
    # 1. A 2.2.0 captured golden must NOT satisfy a matched=True assertion
    _write(fixtures / "2.2.0" / "overview" / "captured.json", {"applicationName": "test"})
    err_22_matched = _parity_error(
        "overview", "captured", {"applicationName": "test"}, fixture_version="2.2.0", matched=True
    )
    assert err_22_matched is not None
    assert "2.3.0" in err_22_matched

    # 2. When fixture_version="2.3.0" is requested and no 2.3.0 fixture exists,
    # it must fail with a clear message naming the missing file, and never fall back to 2.2.0
    err_missing_23 = _parity_error("overview", "captured", {"applicationName": "test"}, fixture_version="2.3.0")
    assert err_missing_23 is not None
    assert "2.3.0" in err_missing_23
    assert "captured.json" in err_missing_23

    # 3. When 2.3.0 fixture is provisional and matched=True is asserted,
    # it must raise an error (not just emit UnverifiedParityWarning)
    _write(fixtures / "2.3.0" / "overview" / "provisional.json", {"applicationName": "test"})
    err_prov_matched = _parity_error(
        "overview", "captured", {"applicationName": "test"}, fixture_version="2.3.0", matched=True
    )
    assert err_prov_matched is not None
    assert "provisional" in err_prov_matched

    # 4. When 2.3.0 fixture is captured and valid, matched=True succeeds
    _write(fixtures / "2.3.0" / "overview" / "captured.json", {"applicationName": "test"})
    assert (
        _parity_error("overview", "captured", {"applicationName": "test"}, fixture_version="2.3.0", matched=True)
        is None
    )


def test_bootui_ids_reads_version_own_ids_without_fallback(fixtures: Path) -> None:
    # 2.2.0 ids.json exists, but 2.3.0 is requested: missing 2.3.0 ids.json must error, not fall back
    _write(fixtures / "2.2.0" / "ids.json", {"spring": "fastapi"})
    with pytest.raises(AssertionError, match=r"no ids\.json for fixture version 2\.3\.0"):
        bootui_ids("2.3.0")

    # when 2.3.0 ids.json exists, it reads 2.3.0
    _write(fixtures / "2.3.0" / "ids.json", {"spring": "fastapi-23"})
    assert bootui_ids("2.3.0") == {"spring": "fastapi-23"}


def test_golden_loader_nonempty_payload_rule_only_under_23(fixtures: Path) -> None:
    # 2.3.0 requires non-empty payload for non-empty golden list of objects
    _write(fixtures / "2.3.0" / "data" / "captured.json", {"items": [{"id": 1}]})
    err_obj_23 = _parity_error("data", "data", {"items": []}, fixture_version="2.3.0")
    assert err_obj_23 is not None
    assert "non-empty" in err_obj_23

    # 2.3.0 requires non-empty payload for non-empty golden list of scalars
    _write(fixtures / "2.3.0" / "tags" / "captured.json", {"tags": ["a"]})
    err_scalar_23 = _parity_error("tags", "tags", {"tags": []}, fixture_version="2.3.0")
    assert err_scalar_23 is not None
    assert "non-empty" in err_scalar_23

    # 2.2.0 legacy keeps today's checks: empty payload list is allowed
    _write(fixtures / "2.2.0" / "data" / "captured.json", {"items": [{"id": 1}]})
    assert _parity_error("data", "data", {"items": []}, fixture_version="2.2.0") is None

    _write(fixtures / "2.2.0" / "tags" / "captured.json", {"tags": ["a"]})
    assert _parity_error("tags", "tags", {"tags": []}, fixture_version="2.2.0") is None


def test_golden_loader_checks_catalog_field_union_under_23(fixtures: Path) -> None:
    # 2.3.0 checks catalog_fields union
    _write(fixtures / "2.3.0" / "overview" / "captured.json", {"applicationName": "test"})
    err_23 = _parity_error(
        "overview",
        "overview",
        {"applicationName": "test"},
        fixture_version="2.3.0",
        catalog_fields=["applicationName", "frameworkName"],
    )
    assert err_23 is not None
    assert "frameworkName" in err_23

    # 2.2.0 keeps today's checks: catalog_fields not unioned
    _write(fixtures / "2.2.0" / "overview" / "captured.json", {"applicationName": "test"})
    assert (
        _parity_error(
            "overview",
            "overview",
            {"applicationName": "test"},
            fixture_version="2.2.0",
            catalog_fields=["applicationName", "frameworkName"],
        )
        is None
    )


def test_golden_loader_reads_catalog_json_file(fixtures: Path) -> None:
    # catalog.json as list
    _write(fixtures / "2.3.0" / "overview" / "captured.json", {"applicationName": "test"})
    _write(fixtures / "2.3.0" / "overview" / "catalog.json", ["applicationName", "frameworkName"])
    error_list = _parity_error("overview", "overview", {"applicationName": "test"}, fixture_version="2.3.0")
    assert error_list is not None
    assert "frameworkName" in error_list
    assert (
        _parity_error(
            "overview",
            "overview",
            {"applicationName": "test", "frameworkName": "FastAPI"},
            fixture_version="2.3.0",
        )
        is None
    )

    # catalog.json as mapping with requiredFields
    _write(fixtures / "2.3.0" / "service" / "captured.json", {"serviceName": "auth"})
    _write(fixtures / "2.3.0" / "service" / "catalog.json", {"requiredFields": ["serviceName", "port"]})
    error_map = _parity_error("service", "service", {"serviceName": "auth"}, fixture_version="2.3.0")
    assert error_map is not None
    assert "port" in error_map
    assert (
        _parity_error(
            "service",
            "service",
            {"serviceName": "auth", "port": 8000},
            fixture_version="2.3.0",
        )
        is None
    )


def test_assert_parity_rejects_shapeless_list_when_matched(fixtures: Path) -> None:
    _write(fixtures / "2.3.0" / "data" / "captured.json", {"items": []})
    payload = {"items": [{"id": 1}]}

    # matched=True raises AssertionError
    err_matched = _parity_error("data", "data", payload, fixture_version="2.3.0", matched=True)
    assert err_matched is not None
    assert "has no shape information" in err_matched
    assert "cannot satisfy 2.3.0 'matched' parity" in err_matched

    # matched=False emits warning
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        assert_parity("data", "data", payload, fixture_version="2.3.0", matched=False)
    assert any(issubclass(w.category, UnverifiedParityWarning) for w in recorded)


def test_assert_enum_values_checks_enums(fixtures: Path) -> None:
    _write(fixtures / "2.3.0" / "service" / "enums.json", {"status": ["ACTIVE", "INACTIVE"]})
    with pytest.raises(AssertionError, match=r"status: 'INVALID_STATE' not in \['ACTIVE', 'INACTIVE'\]"):
        assert_enum_values("service", "service", {"status": "INVALID_STATE"}, fixture_version="2.3.0")

    assert_enum_values("service", "service", {"status": "ACTIVE"}, fixture_version="2.3.0")


def test_golden_loader_enforces_value_kinds_equality(fixtures: Path) -> None:
    _write(fixtures / "2.2.0" / "types" / "captured.json", {"flag": True, "count": 10})
    error_bool = _parity_error("types", "types", {"flag": 1, "count": 10})
    assert error_bool is not None
    assert "flag" in error_bool
    assert "boolean" in error_bool

    error_num = _parity_error("types", "types", {"flag": True, "count": "10"})
    assert error_num is not None
    assert "count" in error_num
    assert "number" in error_num


def test_golden_loader_documented_nulls_rejected_without_reason(fixtures: Path) -> None:
    _write(fixtures / "2.2.0" / "data" / "captured.json", {"title": "report"})
    error = _parity_error("data", "data", {"title": None})
    assert error is not None
    assert "nullable.json" in error

    _write(fixtures / "2.2.0" / "data" / "nullable.json", {"title": "   "})
    error_ws = _parity_error("data", "data", {"title": None})
    assert error_ws is not None
    assert "reason" in error_ws


def test_patched_root_still_selects_the_fixture_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(golden, "ROOT", tmp_path)
    _write(tmp_path / "2.2.0" / "x" / "captured.json", {"version": "2.2.0"})
    _write(tmp_path / "2.3.0" / "x" / "captured.json", {"version": "2.3.0"})

    assert golden._folder("x", "2.3.0") == tmp_path / "2.3.0" / "x"
    assert_parity("x", "captured", {"version": "2.3.0"}, fixture_version="2.3.0")
