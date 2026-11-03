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


def _mysql(version: str = "8.0.36", **kwargs: Any) -> _RecordingConn:
    answers = {
        "SELECT @@version": [version],
        "SELECT @@SESSION.autocommit": [0],
        "SELECT @@SESSION.transaction_read_only": [0, 1],
        "SELECT @@SESSION.tx_read_only": [0, 1],
        "SELECT @@SESSION.max_execution_time": [0],
        "SELECT @@SESSION.max_statement_time": [0.0],
        "SELECT @@SESSION.innodb_lock_wait_timeout": [50],
    }
    answers.update(kwargs.pop("answers", {}))
    return _RecordingConn(answers=answers, **kwargs)


def test_mysql_read_only_statement_order() -> None:
    conn = _mysql(answers={"SELECT 1": [1]})

    result, _ran = _read(conn)

    assert conn.queries == [
        "SELECT @@version",
        "SELECT @@SESSION.autocommit",
        "SELECT @@SESSION.transaction_read_only",
        "SELECT @@SESSION.max_execution_time",
        "SELECT @@SESSION.innodb_lock_wait_timeout",
        "ROLLBACK",
        "SET SESSION transaction_read_only = 1",
        "SET SESSION max_execution_time = 5000",
        "SET SESSION innodb_lock_wait_timeout = 2",
        "SELECT @@SESSION.transaction_read_only",
        "SELECT 1",
        "ROLLBACK",
        "SET SESSION transaction_read_only = 0",
        "SET SESSION max_execution_time = 0",
        "SET SESSION innodb_lock_wait_timeout = 50",
    ]
    assert result == 1
    assert conn.invalidated is False


def test_mysql_verification_failure_refuses() -> None:
    conn = _mysql(answers={"SELECT @@SESSION.transaction_read_only": [0, 0]})

    result, ran = _read(conn)

    assert "SET SESSION transaction_read_only = 1" in conn.queries
    assert isinstance(result, sqla.ReadOnlyUnavailable)
    assert ran == []
    assert conn.queries[-3:] == [
        "SET SESSION transaction_read_only = 0",
        "SET SESSION max_execution_time = 0",
        "SET SESSION innodb_lock_wait_timeout = 50",
    ]


def test_mysql_autocommit_refused() -> None:
    conn = _mysql(answers={"SELECT @@SESSION.autocommit": [1]})

    result, ran = _read(conn)

    assert "SELECT @@SESSION.autocommit" in conn.queries
    assert isinstance(result, sqla.ReadOnlyUnavailable)
    assert ran == []
    assert not [q for q in conn.queries if q.startswith("SET ")]


def test_mysql_autocommit_execution_option_refused_before_any_statement() -> None:
    conn = _mysql(options={"isolation_level": "AUTOCOMMIT"})

    result, ran = _read(conn)

    assert isinstance(result, sqla.ReadOnlyUnavailable)
    assert conn.queries == []
    assert ran == []


def test_mariadb_old_variable_name() -> None:
    conn = _mysql("10.6.12-MariaDB", answers={"SELECT 1": [1]})

    result, _ran = _read(conn)

    assert "SET SESSION tx_read_only = 1" in conn.queries
    assert "SET SESSION max_statement_time = 5.0" in conn.queries
    assert "SELECT @@SESSION.transaction_read_only" not in conn.queries
    assert result == 1


def test_mariadb_11_1_uses_transaction_read_only() -> None:
    conn = _mysql("11.4.2-MariaDB-ubu2404", answers={"SELECT 1": [1]})

    result, _ran = _read(conn)

    assert "SET SESSION transaction_read_only = 1" in conn.queries
    assert result == 1


def test_mysql_before_5_7_20_uses_tx_read_only() -> None:
    conn = _mysql("5.7.19-log", answers={"SELECT 1": [1]})

    result, _ran = _read(conn)

    assert "SET SESSION tx_read_only = 1" in conn.queries
    assert result == 1


def test_mysql_restore_failure_invalidates() -> None:
    conn = _mysql(fail_on="SET SESSION transaction_read_only = 0")

    result, _ran = _read(conn)

    assert conn.invalidated is True
    assert isinstance(result, RuntimeError)


def test_other_dialect_read_only_unavailable() -> None:
    conn = _RecordingConn(dialect=_FakeDialect(name="oracle"))

    result, ran = _read(conn)

    assert isinstance(result, sqla.ReadOnlyUnavailable)
    assert conn.queries == []
    assert ran == []


def test_sqlite_read_back_not_on_refuses() -> None:
    # council F5b finding 1: the read-back is the check; a server that keeps query_only off refuses the read
    conn = _RecordingConn(dialect=_FakeDialect(name="sqlite"), answers={"PRAGMA query_only": [0, 0]})

    result, ran = _read(conn)

    assert isinstance(result, sqla.ReadOnlyUnavailable)
    assert ran == []
    assert conn.queries[-1] == "PRAGMA query_only = 0"
    assert conn.invalidated is False


class _ReadBackFails(_RecordingConn):
    """The second ``PRAGMA query_only`` (the read-back) raises, as a dropped connection would."""

    def exec_driver_sql(self, sql: str) -> _Result:
        if sql == "PRAGMA query_only" and sql in self.queries:
            self.queries.append(sql)
            raise RuntimeError("connection lost during the read-back")
        return super().exec_driver_sql(sql)


def test_sqlite_read_back_failure_refuses() -> None:
    conn = _ReadBackFails(dialect=_FakeDialect(name="sqlite"), answers={"PRAGMA query_only": [0]})

    result, ran = _read(conn)

    assert isinstance(result, RuntimeError)
    assert ran == []
    assert conn.queries[-1] == "PRAGMA query_only = 0"
