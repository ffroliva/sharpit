"""A10: failed statements keep the resolved dialect and render through the facade."""

from __future__ import annotations

import re

import pytest
from tests.masking.a10.conftest import a10_surface, fixture_rows

from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect, Shape

pytestmark = pytest.mark.needs_sqlalchemy


def test_each_fixture_error_is_recorded_with_its_family() -> None:
    masker = Masker(Exposure.MASKED, True, None)

    def drive():
        for _, family, error, raw in fixture_rows():
            recorder = SqlTraceRecorder(masker, capture_call_site=False)
            recorder.record(
                "SELECT 'A10VALUE'",
                duration_ns=1,
                thread="a10",
                connection_id=None,
                dialect=family,
                error=error,
            )
            shape = recorder.rows()[0]["shape"]
            assert isinstance(shape, Shape)
            known_word = next(word for word in re.findall(r"[A-Za-z]+", raw) if len(word) > 2)
            yield "source_chain", family, shape.dialect, recorder.rows()[0]["errorMessage"], known_word

    report = a10_surface("recorder", drive)
    assert report.counts["source_chain"] == len(fixture_rows())


def test_a_recorded_error_with_a_chain_conflict_hides() -> None:
    from sharpit.engine.masking import Exposure, Masker

    sqlite_error = type("SqliteFailure", (Exception,), {"__module__": "sqlite3"})("sqlite failure")
    postgres_error = type("PostgresFailure", (Exception,), {"__module__": "psycopg.errors"})(
        "failure\n[SQL: SELECT 'A10VALUE']"
    )
    postgres_error.__cause__ = sqlite_error
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, None), capture_call_site=False)
    recorder.record(
        "SELECT 'A10VALUE'",
        duration_ns=1,
        thread="a10",
        connection_id=None,
        dialect=Dialect.UNSUPPORTED,
        error=postgres_error,
    )

    row = recorder.rows()[0]
    assert isinstance(row["shape"], Shape)
    assert row["shape"].dialect is Dialect.UNSUPPORTED
    assert "A10VALUE" not in row["errorMessage"]
