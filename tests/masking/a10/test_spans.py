"""A10: spans derive SQL dialect evidence from the span event."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from tests.masking.a10.conftest import plant_fails, scratch_package

from sharpit.engine.capture.traces import SpanBuffer
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqla.inspect import EngineRegistry
from sharpit.engine.sqltext import Dialect

pytestmark = pytest.mark.needs_sqlalchemy

VALUE = "A10" + "VALUE"
TRACE_ID = 1


def _span(attributes: dict[str, Any]) -> Any:
    return SimpleNamespace(
        context=SimpleNamespace(trace_id=TRACE_ID, span_id=1),
        parent=None,
        name="query",
        kind=SimpleNamespace(name="CLIENT"),
        resource=SimpleNamespace(attributes={}),
        instrumentation_scope=SimpleNamespace(name="a10"),
        start_time=1,
        end_time=2,
        status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET"), description=None),
        attributes=attributes,
        events=[],
    )


def _application(*urls: str) -> tuple[Callable[[], Dialect | None], list[Any]]:
    from sqlalchemy import create_engine

    registry = EngineRegistry(Masker(Exposure.MASKED, True, None))
    engines = [create_engine(url) for url in urls]
    for engine in engines:
        registry.add(engine)
    return registry.family, engines


def _statement(attributes: dict[str, Any], application: Callable[[], Dialect | None] | None = None) -> str | None:
    span = _span({**attributes, "db.statement": f'SELECT "{VALUE}"'})
    buffer = SpanBuffer(Masker(Exposure.MASKED, True, None), application=application or (lambda: None))
    buffer.add(span)
    detail = buffer.detail(f"{TRACE_ID:032x}")
    assert detail is not None
    return next(item["value"] for item in detail["spans"][0]["attributes"] if item["key"] == "db.statement")


def test_span_rows_read_names_and_application_evidence() -> None:
    assert _statement({"db.system": "postgresql"}) == f'SELECT "{VALUE}"'
    assert _statement({"db.system.name": "mysql"}) == "SELECT ?"
    assert _statement({"db.system": "postgresql", "db.system.name": "postgresql"}) == f'SELECT "{VALUE}"'
    assert (
        _statement({"db.system": "postgresql", "db.system.name": "mysql"}) == "[statement hidden: unsupported database]"
    )
    assert _statement({"db.system": "mysql", "db.system.name": "redis"}) == "[statement hidden: unsupported database]"
    one_family, _ = _application("mysql+pymysql://")
    assert _statement({}, one_family) == "SELECT ?"
    mixed_family, _ = _application("mysql+pymysql://", "postgresql+psycopg://")
    assert _statement({}, mixed_family) == "[statement hidden: unsupported database]"
    assert _statement({"db.system": "redis"}) == "[statement hidden: unsupported database]"
    assert _statement({"db.system.name": "mongodb"}) == "[statement hidden: unsupported database]"


def test_a_span_conflict_hides() -> None:
    shown = _statement({"db.system": "postgresql", "db.system.name": "redis"})
    assert shown is not None
    assert VALUE not in shown


def test_a_span_conflict_hides_when_unsupported_statement_guard_is_removed(tmp_path) -> None:
    package = scratch_package(tmp_path)
    plant_fails(
        package,
        "tests/masking/a10/test_spans.py::test_a_span_conflict_hides",
        "engine/capture/traces.py",
        "if key in _SQL_KEYS and dialect is Dialect.UNSUPPORTED:",
        "if False:",
    )
