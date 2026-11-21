"""Issue #59: on SQLite a double-quoted run that names no column is a string, so every SQL surface hides it.

The issue's rows run on a live SQLite through SQLAlchemy and sharpit's capture; each surface then shows the statement
the engine ran. PostgreSQL reads ``"..."`` as an identifier, so there it stays visible: the SQLite rule never spreads.
"""

# derived: issue #59 evidence table; no BootUI source

from __future__ import annotations

import pytest

sa = pytest.importorskip("sqlalchemy")

from tests.masking.test_statement_surfaces import (  # noqa: E402
    _attribute,  # pyright: ignore[reportPrivateUsage]
    _exception_message,  # pyright: ignore[reportPrivateUsage]
    _log_line,  # pyright: ignore[reportPrivateUsage]
    _orm_statement,  # pyright: ignore[reportPrivateUsage]
    _recorder_sql,  # pyright: ignore[reportPrivateUsage]
)

from sharpit.engine.masking import Exposure, Masker  # noqa: E402
from sharpit.engine.sqltext import Dialect  # noqa: E402

SECRET = "hunter2Value"
# the issue's table: (statement, what SQLite returned, the run that must stay hidden)
ROWS = [
    (f'SELECT lower("{SECRET}")', SECRET.lower()),
    (f'SELECT "{SECRET}"', SECRET),
    (f'SELECT "{SECRET}" FROM t', SECRET),
    (f'SELECT id FROM t WHERE name = "{SECRET}"', None),  # a value position: no rows
]
EXPOSURES = [Exposure.MASKED, Exposure.METADATA_ONLY]


def _run_live(statement: str) -> tuple[object, str]:
    """Run ``statement`` on a live SQLite under sharpit's capture; return what SQLite returned and what was recorded."""
    from fastapi import FastAPI
    from sharpit import install

    engine = sa.create_engine("sqlite://")
    handle = install(FastAPI(), enabled="ON", show_banner=False, sql_trace_sqlite3_enabled=False, engines=[engine])
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("CREATE TABLE t (id INTEGER, name TEXT)")
            conn.exec_driver_sql("INSERT INTO t VALUES (1, 'ann')")
            row = conn.exec_driver_sql(statement).first()
        recorded = handle.context.capture.sql_trace.rows()[-1]["sql"]
    finally:
        handle.uninstall_capture()
        engine.dispose()
    return (row[0] if row else None), recorded


@pytest.mark.needs_sqlalchemy
@pytest.mark.parametrize(("statement", "returned"), ROWS, ids=[s for s, _ in ROWS])
def test_the_live_recorder_hides_the_double_quoted_run(statement: str, returned: object) -> None:
    got, recorded = _run_live(statement)
    assert got == returned  # SQLite really treated the run as a string, so the case is the issue's
    assert recorded
    assert SECRET not in recorded
    assert SECRET.lower() not in recorded


@pytest.mark.needs_sqlalchemy
@pytest.mark.parametrize("exposure", EXPOSURES)
@pytest.mark.parametrize(("statement", "_returned"), ROWS, ids=[s for s, _ in ROWS])
def test_every_sqlite_surface_hides_the_double_quoted_run(
    statement: str, _returned: object, exposure: Exposure
) -> None:
    masker = Masker(exposure, True)
    engine = sa.create_engine("sqlite://")
    failing = statement.replace(" FROM t", " FROM nope") if " FROM t" in statement else f"{statement} FROM nope"
    conn = engine.connect()
    try:
        with pytest.raises(sa.exc.OperationalError) as caught:
            conn.exec_driver_sql(failing)
    finally:
        conn.close()
    error = str(caught.value)
    assert "[SQL: " in error
    assert SECRET in error  # the real SQLAlchemy block names the run, so the next asserts have something to hide
    shown = {
        "recorder sql": _recorder_sql(masker, statement, Dialect.SQLITE),
        "db.statement": _attribute("db.statement", masker, statement, Dialect.SQLITE),
        "orm statement": _orm_statement(masker, statement, Dialect.SQLITE),
        "log": _log_line("sqlalchemy.engine.Engine", masker, statement, Dialect.SQLITE),
        "[SQL: ] block": _exception_message(masker, error, Dialect.SQLITE),
        "error attribute": _attribute("exception.message", masker, error, Dialect.SQLITE),
    }
    leaked = {name: text for name, text in shown.items() if SECRET in (text or "")}
    assert not leaked, leaked


def test_postgresql_keeps_a_double_quoted_identifier() -> None:
    """PostgreSQL reads ``"..."`` as a name, so the SQLite rule must not reach it."""
    masker = Masker(Exposure.MASKED, True)
    statement = 'SELECT "order" FROM "user"'
    assert '"order"' in (_recorder_sql(masker, statement, Dialect.POSTGRESQL) or "")
    assert '"user"' in (_attribute("db.statement", masker, statement, Dialect.POSTGRESQL) or "")
    assert '"order"' not in (_recorder_sql(masker, statement, Dialect.SQLITE) or "")
