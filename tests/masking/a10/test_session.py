"""A10: the test-session sink resolves and renders the event's own SQL dialect."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from tests.masking.a10.conftest import a10_surface, fixture_rows, plant_fails, scratch_package

from engine.testsession.tsfakes import NODE, event
from sharpit.engine import sqltext
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect
from sharpit.engine.testsession.sink import TestSessionSink

pytestmark = pytest.mark.needs_sqlalchemy
EXCEPTION_TEST = "tests/masking/a10/test_session.py::test_a_session_exception_reads_its_chain"
SQL_TEST = "tests/masking/a10/test_session.py::test_a_session_sql_uses_its_engine_dialect"


def test_a_session_exception_reads_its_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    render = sqltext.error_text

    def capture(masker: Masker, source: str | BaseException, dialect: Dialect, **kwargs: bool) -> str | None:
        observed.append(dialect)
        return render(masker, source, dialect, **kwargs)

    observed: list[Dialect] = []
    monkeypatch.setattr(sqltext, "error_text", capture)

    def drive():
        for _, expected, error, raw in fixture_rows():
            sink = TestSessionSink("a10", Masker(Exposure.MASKED, True))
            attempt = sink.begin_test(NODE)
            sink.on_exception(error, "logging", (NODE, attempt, "call"))
            groups = sink.current_test.phases["call"].exception_groups  # type: ignore[union-attr]
            type_name, message = next(iter(groups.values()))
            actual = observed[-1] if observed else Dialect.UNSUPPORTED
            known_word = next(word for word in re.findall(r"[A-Za-z]+", raw) if len(word) > 2)
            yield "source_chain", expected, actual, message or type_name, known_word

    report = a10_surface("test-session-exception", drive)
    assert report.counts["source_chain"] == len(fixture_rows())


def test_a_session_sql_uses_its_engine_dialect(monkeypatch: pytest.MonkeyPatch) -> None:
    shape = sqltext.statement_shape
    observed: list[Dialect] = []

    def capture(masker: Masker, statement: str, dialect: Dialect):
        observed.append(dialect)
        return shape(masker, statement, dialect)

    monkeypatch.setattr(sqltext, "statement_shape", capture)
    engine = sa.create_engine("sqlite://")
    try:
        sink = TestSessionSink("a10", Masker(Exposure.MASKED, True))
        attempt = sink.begin_test(NODE)
        sql_event = event()._replace(dialect=engine.dialect, engine=engine)
        sink.on_sql(sql_event, (NODE, attempt, "call"))
        assert observed[-1] is Dialect.SQLITE
        assert sink.facts.sqlite_seen
        assert sink.current_test.phases["call"].selects == {}  # type: ignore[union-attr]
    finally:
        engine.dispose()


def test_a_build_that_skips_the_session_exception_chain_fails_a10(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    plant_fails(
        copy,
        EXCEPTION_TEST,
        "engine/testsession/sink.py",
        "resolve(exc, (ExceptionDialectSource(),), DialectContext(lambda: None))",
        "Dialect.UNSUPPORTED",
    )


def test_a_build_that_skips_the_session_sql_event_fails_a10(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    plant_fails(
        copy,
        SQL_TEST,
        "engine/testsession/sink.py",
        "event_dialect(event, lambda: None)",
        "Dialect.UNSUPPORTED",
    )
