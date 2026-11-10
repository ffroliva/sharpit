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
from golden import UnverifiedParityWarning, assert_parity, bootui_ids
from sharpit.engine.panels import PANELS


@pytest.fixture
def fixtures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(golden, "ROOT", tmp_path)
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
    except (AssertionError, TypeError) as exc:
        return str(exc)
    return None


def test_golden_id_mapping_covers_panel_ids() -> None:
    ids = bootui_ids()
    bootui_panel_ids = {panel["id"] for panel in legacy_golden("panels")["panels"]}
    assert set(ids.values()) == {panel.id for panel in PANELS}
    assert set(ids) <= bootui_panel_ids
    assert ids["hibernate-statistics"] == "sqlalchemy-statistics"
    assert ids["spring-security"] == "fastapi-security"
    assert ids["spring"] == "fastapi"
    assert ids["flyway"] == "alembic"
    assert ids["postgresql"] == "postgresql"


def test_golden_loader_reads_nullable_reasons(fixtures: Path) -> None:
    _write(fixtures / "data" / "captured.json", {"name": "orders", "rows": 3, "items": [{"count": 1}]})
    payload = {"name": "orders", "rows": None, "items": [{"count": None}]}

    no_reason = _parity_error("data", "data", payload)
    assert no_reason is not None
    assert "rows" in no_reason

    _write(fixtures / "data" / "nullable.json", {"rows": "no row estimate", "items[].count": "no counter"})
    assert _parity_error("data", "data", payload) is None

    _write(fixtures / "data" / "nullable.json", {"rows": "", "items[].count": "no counter"})
    empty_reason = _parity_error("data", "data", payload)
    assert empty_reason is not None
    assert "reason" in empty_reason


def test_provisional_fixture_is_not_counted_as_parity(fixtures: Path) -> None:
    _write(fixtures / "traces" / "provisional.json", {"traces": []})
    with warnings.catch_warnings(record=True) as provisional:
        warnings.simplefilter("always")
        assert_parity("traces", "traces", {"traces": []})
    assert [w.category for w in provisional] == [UnverifiedParityWarning]

    _write(fixtures / "traces" / "captured.json", {"traces": []})
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        assert_parity("traces", "traces", {"traces": []})
    assert [w.category for w in captured] == []


def test_golden_loader_rejects_missing_key_and_wrong_type(fixtures: Path) -> None:
    _write(fixtures / "postgresql" / "captured.json", {"version": "16", "sessions": [{"pid": 1, "idle": True}]})

    missing = _parity_error("postgresql", "postgresql", {"sessions": []})
    assert missing is not None
    assert "version" in missing

    wrong_type = _parity_error("postgresql", "postgresql", {"version": "16", "sessions": [{"pid": "1", "idle": True}]})
    assert wrong_type is not None
    assert "sessions[].pid" in wrong_type

    extra_keys = {"version": "16", "sessions": [{"pid": 1, "idle": False, "extra": 2}], "more": 1.5}
    assert _parity_error("postgresql", "postgresql", extra_keys) is None


def test_golden_loader_prefers_named_capture(fixtures: Path) -> None:
    _write(fixtures / "postgresql" / "captured.json", {"version": "16"})
    _write(fixtures / "postgresql" / "sessions.captured.json", {"sessions": []})

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
    _write(fixtures / "overview" / "captured.json", {"applicationName": "test"})
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


def test_golden_loader_requires_nonempty_payload_for_nonempty_golden_list(fixtures: Path) -> None:
    _write(fixtures / "data" / "captured.json", {"items": [{"id": 1}]})
    error = _parity_error("data", "data", {"items": []})
    assert error is not None
    assert "non-empty" in error


def test_golden_loader_checks_catalog_field_union(fixtures: Path) -> None:
    _write(fixtures / "overview" / "captured.json", {"applicationName": "test"})
    error = _parity_error(
        "overview",
        "overview",
        {"applicationName": "test"},
        catalog_fields=["applicationName", "frameworkName"],
    )
    assert error is not None
    assert "frameworkName" in error


def test_assert_parity_checks_enum_values_when_enums_defined(fixtures: Path) -> None:
    _write(fixtures / "service" / "captured.json", {"status": "ACTIVE"})
    _write(fixtures / "service" / "enums.json", {"status": ["ACTIVE", "INACTIVE"]})
    error = _parity_error("service", "service", {"status": "INVALID_STATE"})
    assert error is not None
    assert "INVALID_STATE" in error


def test_golden_loader_enforces_value_kinds_equality(fixtures: Path) -> None:
    _write(fixtures / "types" / "captured.json", {"flag": True, "count": 10})
    error_bool = _parity_error("types", "types", {"flag": 1, "count": 10})
    assert error_bool is not None
    assert "flag" in error_bool
    assert "boolean" in error_bool

    error_num = _parity_error("types", "types", {"flag": True, "count": "10"})
    assert error_num is not None
    assert "count" in error_num
    assert "number" in error_num


def test_golden_loader_documented_nulls_rejected_without_reason(fixtures: Path) -> None:
    _write(fixtures / "data" / "captured.json", {"title": "report"})
    error = _parity_error("data", "data", {"title": None})
    assert error is not None
    assert "nullable.json" in error

    _write(fixtures / "data" / "nullable.json", {"title": "   "})
    error_ws = _parity_error("data", "data", {"title": None})
    assert error_ws is not None
    assert "reason" in error_ws
