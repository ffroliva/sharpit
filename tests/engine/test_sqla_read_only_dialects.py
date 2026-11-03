"""Verified read-only reads on SQLite and MySQL/MariaDB (0.5.0 spec §5.0, plan F5b Tasks 2 and 3).

A read-only read either runs inside a session the server confirmed read-only, or does not run (``ReadOnlyUnavailable``).
Whatever sharpit changed on the connection is put back afterwards; a connection it cannot put back is invalidated, so
the app's pool never gets a read-only connection.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from sharpit.engine import sqla

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")
StaticPool = pytest.importorskip("sqlalchemy.pool").StaticPool


def _outcome(engine: Any, fn: Callable[[Any], Any]) -> Any:
    """The read's result, or the exception it raised (so a refusal fails on the test's assertion, not as a crash)."""
    try:
        return asyncio.run(sqla.run_db_read(engine, fn, 5.0, read_only=True))
    except Exception as exc:  # noqa: BLE001 - the tests assert on what came back
        return exc


def _sqlite_engine(query_only: int = 0) -> Any:
    # one connection, shared with the read's worker thread: the tests see what the read left on it
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE probe (id INTEGER)")
        conn.exec_driver_sql(f"PRAGMA query_only = {query_only}")
    return engine


def _query_only(engine: Any) -> Any:
    with engine.connect() as conn:
        return conn.exec_driver_sql("PRAGMA query_only").scalar()


def test_sqlite_read_only_wrapper_rejects_write() -> None:
    engine = _sqlite_engine()

    outcome = _outcome(engine, lambda c: c.exec_driver_sql("INSERT INTO probe VALUES (1)"))

    assert "attempt to write a readonly database" in str(outcome)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM probe").scalar() == 0


def test_read_only_restores_session_state() -> None:
    engine = _sqlite_engine()

    seen = _outcome(engine, lambda c: c.exec_driver_sql("PRAGMA query_only").scalar())
    after_success = _query_only(engine)

    def fail(c: Any) -> None:
        c.exec_driver_sql("SELECT 1")
        raise RuntimeError("the read failed")

    failed = _outcome(engine, fail)
    after_failure = _query_only(engine)

    assert seen == 1
    assert after_success == 0
    assert isinstance(failed, RuntimeError)
    assert after_failure == 0


def test_sqlite_read_only_keeps_an_app_query_only_session() -> None:
    engine = _sqlite_engine(query_only=1)

    seen = _outcome(engine, lambda c: c.exec_driver_sql("SELECT count(*) FROM probe").scalar())

    assert seen == 0
    assert _query_only(engine) == 1


@dataclass
class _FakeDialect:
    name: str = "mysql"
    is_async: bool = False
    is_mariadb: bool = False


@dataclass
class _Result:
    value: Any

    def scalar(self) -> Any:
        return self.value


@dataclass
class _RecordingConn:
    """Records every statement; a ``SELECT`` answers from ``answers`` (a list per statement, consumed in order)."""

    dialect: _FakeDialect = field(default_factory=_FakeDialect)
    answers: dict[str, list[Any]] = field(default_factory=dict)
    fail_on: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    queries: list[str] = field(default_factory=list)
    invalidated: bool = False

    def exec_driver_sql(self, sql: str) -> _Result:
        self.queries.append(sql)
        if sql == self.fail_on:
            raise RuntimeError(f"connection lost during {sql}")
        script = self.answers.get(sql)
        return _Result(script.pop(0) if script else 0)

    def rollback(self) -> None:
        self.queries.append("ROLLBACK")

    def invalidate(self) -> None:
        self.invalidated = True

    def get_execution_options(self) -> dict[str, Any]:
        return self.options


def _read(conn: _RecordingConn, fn: Callable[[Any], Any] | None = None) -> tuple[Any, list[str]]:
    """``bounded_read_only`` on ``conn``: (its result or exception, the statements ``fn`` was handed the conn for)."""
    ran: list[str] = []

    def default(c: Any) -> Any:
        ran.append("fn")
        return c.exec_driver_sql("SELECT 1").scalar()

    try:
        return sqla.bounded_read_only(conn, fn or default, 5.0, 2.0), ran
    except Exception as exc:  # noqa: BLE001 - the tests assert on what came back
        return exc, ran


def test_sqlite_restore_failure_invalidates() -> None:
    conn = _RecordingConn(
        dialect=_FakeDialect(name="sqlite"),
        answers={"PRAGMA query_only": [0, 1]},
        fail_on="PRAGMA query_only = 0",
    )

    result, _ran = _read(conn)

    assert conn.invalidated is True
    assert isinstance(result, RuntimeError)
