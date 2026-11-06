"""A10: wired surfaces must resolve their proven database family."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from tests.masking.a10.conftest import a10_surface, fixture_rows, plant_fails, scratch_package

from sharpit.engine import sqltext
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqla.dialect_source import EngineDialectSource, ExceptionDialectSource
from sharpit.engine.sqltext import Dialect, DialectContext, resolve

pytestmark = pytest.mark.needs_sqlalchemy
ROOT = Path(__file__).resolve().parents[3]
FAMILY_TEST = "tests/masking/a10/test_gate.py::test_every_fixture_type_resolves_to_its_family"


def test_the_facade_has_all_three_entries() -> None:
    assert callable(getattr(sqltext, "statement_text", None))
    assert callable(getattr(sqltext, "error_text", None))
    assert callable(getattr(sqltext, "statement_shape", None))


def test_statement_shape_uses_masked_text_for_its_fingerprint() -> None:
    masker = Masker(Exposure.MASKED, True, None)
    shape = sqltext.statement_shape(masker, "SELECT 'A10VALUE'", Dialect.SQLITE)
    assert shape.text == "SELECT ?"
    assert shape.fingerprint == shape.text.lower()
    assert shape.dialect is Dialect.SQLITE
    assert shape.literal_count == 1


def test_error_text_accepts_the_facade_source_type() -> None:
    masker = Masker(Exposure.MASKED, True, None)
    assert sqltext.error_text(masker, "connection failed", Dialect.SQLITE) == "connection failed"


def test_every_fixture_type_resolves_to_its_family() -> None:
    rows = fixture_rows()
    if os.environ.get("SHARPIT_A10_SQLITE_ONLY"):
        rows = [row for row in rows if row[1] is Dialect.SQLITE]
    families = {family for _, family, _ in rows}
    assert families >= {Dialect.SQLITE, Dialect.POSTGRESQL, Dialect.MYSQL_FAMILY}
    source = ExceptionDialectSource()
    report = a10_surface(
        "fixture-types",
        lambda: (
            ("proved", family, resolve(error, (source,), DialectContext(lambda: None))) for _, family, error in rows
        ),
    )
    assert report.counts["proved"] == len(rows)


def test_the_recorder_uses_the_sqlite_engine_family() -> None:
    engine = sa.create_engine("sqlite://")
    try:
        event = SimpleNamespace(dialect=engine.dialect, engine=engine, error=None)
        resolved = resolve(event, (EngineDialectSource(),), DialectContext(lambda: None))
        recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, None), capture_call_site=False)
        recorder.record("SELECT 'A10VALUE'", duration_ns=1, thread="t", connection_id=None, dialect=resolved)
        row = recorder.rows()[0]
        assert row["shape"].dialect is Dialect.SQLITE
    finally:
        engine.dispose()


def test_a_build_without_the_chain_walk_fails_a10(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    plant_fails(
        copy, FAMILY_TEST, "engine/sqla/dialect_source.py", "reading = read_chain(error)", "return Dialect.UNSUPPORTED"
    )


def test_a_build_that_resolves_nothing_fails_a10(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    plant_fails(
        copy,
        FAMILY_TEST,
        "engine/sqltext/dialect.py",
        "        proof: set[Dialect] = set()",
        "        return Dialect.UNSUPPORTED\n        proof: set[Dialect] = set()",
    )


def test_a_sqlite_only_input_is_refused(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    # Restricting the fixture corpus models a SQLite-only run; the same A10 row must reject it.
    env = os.environ.copy()
    env["SHARPIT_A10_SQLITE_ONLY"] = "1"
    env["PYTHONPATH"] = os.pathsep.join((str(copy.parent), str(ROOT), env.get("PYTHONPATH", "")))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", FAMILY_TEST],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output[-2000:]
    assert "AssertionError" in output, output[-2000:]
    assert "1 failed" in output, output[-2000:]
