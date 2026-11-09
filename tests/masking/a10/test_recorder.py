"""A10: failed statements keep the resolved dialect and render through the facade."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from tests.masking.a10.conftest import a10_surface, fixture_rows, plant_fails, scratch_package

from sharpit.engine import sqltext
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqla.dialect_source import event_dialect
from sharpit.engine.sqltext import Dialect, Shape

pytestmark = pytest.mark.needs_sqlalchemy


def test_each_fixture_error_is_recorded_with_its_family() -> None:
    masker = Masker(Exposure.MASKED, True, None)

    def drive():
        for _, family, error, raw in fixture_rows():
            resolved = event_dialect(SimpleNamespace(error=error), lambda: None)
            recorder = SqlTraceRecorder(masker, capture_call_site=False)
            recorder.record(
                "SELECT 'A10VALUE'",
                duration_ns=1,
                thread="a10",
                connection_id=None,
                dialect=resolved,
                error=error,
            )
            shape = recorder.rows()[0]["shape"]
            assert isinstance(shape, Shape)
            expected = sqltext.error_text(masker, error, resolved, known=True, keep_frames=False) or ""
            assert recorder.rows()[0]["errorMessage"] == (
                expected if len(expected) <= 2000 else expected.strip()[:2000] + "…"
            )
            known_word = next(word for word in re.findall(r"[A-Za-z]+", raw) if len(word) > 2)
            rendered = recorder.rows()[0]["errorMessage"] or type(error).__name__
            yield "source_chain", family, shape.dialect, rendered, known_word

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


def test_unkeyed_sqlite_recorder_identity_cannot_contain_a_hidden_name() -> None:
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True), capture_call_site=False)
    recorder.record(
        'SELECT id FROM "A10SECRET" WHERE a = 1',
        duration_ns=1,
        thread="a10",
        connection_id=None,
        dialect=Dialect.SQLITE,
    )
    shape = recorder.rows()[0]["shape"]
    assert isinstance(shape, Shape)
    assert "A10SECRET" not in repr(shape.fingerprint).upper()
    assert shape.fingerprint is None


def test_keyed_sqlite_recorder_identity_cannot_contain_a_hidden_name() -> None:
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, identity_key=b"k" * 32), capture_call_site=False)
    recorder.record(
        'SELECT id FROM "A10SECRET" WHERE a = 1',
        duration_ns=1,
        thread="a10",
        connection_id=None,
        dialect=Dialect.SQLITE,
    )
    shape = recorder.rows()[0]["shape"]
    assert isinstance(shape, Shape)
    assert "A10SECRET" not in repr(shape.fingerprint).upper()


@pytest.mark.parametrize(
    ("module", "anchor", "replacement"),
    [
        (
            "engine/sqla/dialect_source.py",
            "return resolve(event, _ERROR_SOURCES, DialectContext(application))",
            "return resolve(event, (), DialectContext(application))",
        ),
        (
            "engine/capture/sqltrace.py",
            "sqltext.error_text(masker, error, dialect, known=True, keep_frames=False)",
            "sqltext.error_text(masker, error, Dialect.UNSUPPORTED, known=True, keep_frames=False)",
        ),
    ],
    ids=["listener-no-chain", "recorder-unsupported"],
)
def test_error_dialect_plants_fail_a10(tmp_path, module: str, anchor: str, replacement: str) -> None:
    plant_fails(
        scratch_package(tmp_path),
        "tests/masking/a10/test_recorder.py::test_each_fixture_error_is_recorded_with_its_family",
        module,
        anchor,
        replacement,
    )
