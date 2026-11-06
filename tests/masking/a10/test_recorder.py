"""A10: failed statements keep the resolved dialect and render through the facade."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from tests.masking.a10.conftest import a10_surface, fixture_rows

from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqla.dialect_source import EngineDialectSource, ExceptionDialectSource
from sharpit.engine.sqltext import Dialect, DialectContext, Shape, resolve

pytestmark = pytest.mark.needs_sqlalchemy


def test_each_fixture_error_is_recorded_with_its_resolved_family() -> None:
    masker = Masker(Exposure.MASKED, True, None)
    sources = (ExceptionDialectSource(),)

    def drive():
        for _, family, error in fixture_rows():
            dialect = resolve(error, sources, DialectContext(lambda: None))
            recorder = SqlTraceRecorder(masker, capture_call_site=False)
            recorder.record(
                "SELECT 'A10VALUE'",
                duration_ns=1,
                thread="a10",
                connection_id=None,
                dialect=dialect,
                error=error,
            )
            shape = recorder.rows()[0]["shape"]
            assert isinstance(shape, Shape)
            yield "proved", family, shape.dialect

    report = a10_surface("recorder", drive)
    assert report.counts["proved"] == len(fixture_rows())


def test_a_recorded_error_with_a_chain_conflict_hides() -> None:
    sqlite_error = type("SqliteFailure", (Exception,), {"__module__": "sqlite3"})("sqlite failure")
    postgres_error = type("PostgresFailure", (Exception,), {"__module__": "psycopg.errors"})(
        "failure\n[SQL: SELECT 'A10VALUE']"
    )
    postgres_error.__cause__ = sqlite_error
    event = SimpleNamespace(error=postgres_error, dialect=Dialect.POSTGRESQL)
    dialect = resolve(event, (EngineDialectSource(), ExceptionDialectSource()), DialectContext(lambda: None))
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, None), capture_call_site=False)
    recorder.record(
        "SELECT 'A10VALUE'",
        duration_ns=1,
        thread="a10",
        connection_id=None,
        dialect=dialect,
        error=postgres_error,
    )

    row = recorder.rows()[0]
    assert isinstance(row["shape"], Shape)
    assert row["shape"].dialect is Dialect.UNSUPPORTED
    assert "A10VALUE" not in row["errorMessage"]
