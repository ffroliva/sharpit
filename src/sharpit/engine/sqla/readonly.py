"""sharpit's own database reads: off the event loop, bounded by timeouts, read-only where it can be verified."""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import math
import re
from collections.abc import Callable
from concurrent.futures import Executor
from typing import Any

from sharpit.engine.capture.correlation import INTERNAL, internal

READ_ONLY_REFUSED = "The read-only transaction could not be established, so sharpit skipped this read"
# Pools that hand the app and sharpit one connection, by class name (SQLAlchemy is not imported here): sharpit's session
# state and rollback would land on the app's own work. AssertionPool has one too, and raises on the app's checkout.
_SHARING_POOLS = frozenset({"StaticPool", "SingletonThreadPool", "AssertionPool"})


class ReadOnlyUnavailable(Exception):
    """Raised when a read-only session or transaction cannot be established and verified on the server."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def is_internal() -> bool:
    """Whether the current thread/task is running sharpit's own database read."""
    return INTERNAL.get()


def _shares_its_connection(engine: Any) -> bool:
    return any(cls.__name__ in _SHARING_POOLS for cls in type(getattr(engine, "pool", None)).__mro__)


def bounded_read_only[T](
    conn: Any,
    fn: Callable[[Any], T],
    statement_timeout: float,
    lock_timeout: float = 2.0,
) -> T:
    """Run ``fn(conn)`` read-only as the server confirmed it, else raise ``ReadOnlyUnavailable`` without running it.

    PostgreSQL: a verified read-only transaction with statement and lock timeouts. SQLite: ``PRAGMA query_only``,
    verified and put back. MySQL/MariaDB: the session's read-only variable and timeouts, verified and put back. Any
    other dialect is refused, and so is any pool that shares its connection with the app.
    """
    if _shares_its_connection(getattr(conn, "engine", None)):
        raise ReadOnlyUnavailable(READ_ONLY_REFUSED)
    name = getattr(getattr(conn, "dialect", None), "name", None)
    if name == "sqlite":
        return _sqlite_read_only(conn, fn)
    if name in ("mysql", "mariadb"):
        return _mysql_read_only(conn, fn, statement_timeout, lock_timeout)
    if name != "postgresql":
        raise ReadOnlyUnavailable(READ_ONLY_REFUSED)
    stmt_ms = max(1, int(statement_timeout * 1000))
    lock_ms = max(1, int(lock_timeout * 1000))
    try:
        # a driver error here (a dropped connection) propagates as itself: READ_ONLY_REFUSED is only the check below
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        conn.exec_driver_sql(f"SET LOCAL statement_timeout = {stmt_ms}")
        conn.exec_driver_sql(f"SET LOCAL lock_timeout = {lock_ms}")
        setting = conn.exec_driver_sql("SELECT current_setting('transaction_read_only')").scalar()
        # under DBAPI autocommit every SET LOCAL was its own transaction: on a server whose default is read-only the
        # setting still says 'on', but the timeouts are gone, so that read is refused too
        dbapi = getattr(getattr(conn, "connection", None), "dbapi_connection", None)
        autocommit = getattr(dbapi, "autocommit", False) is True
        if autocommit or not conn.in_transaction() or str(setting).strip().lower() != "on":
            raise ReadOnlyUnavailable(READ_ONLY_REFUSED)
        return fn(conn)
    finally:
        with contextlib.suppress(Exception):
            conn.rollback()


def _restore(conn: Any, statements: list[str]) -> None:
    """End the read's transaction and put the session back; a connection that cannot be put back is invalidated."""
    try:
        conn.rollback()
        for statement in statements:
            conn.exec_driver_sql(statement)
    except BaseException:
        conn.invalidate()  # never hand the app's pool a connection that keeps sharpit's read-only session
        raise


def _sqlite_read_only[T](conn: Any, fn: Callable[[Any], T]) -> T:
    saved = int(conn.exec_driver_sql("PRAGMA query_only").scalar() or 0)
    try:
        conn.exec_driver_sql("PRAGMA query_only = ON")
        if conn.exec_driver_sql("PRAGMA query_only").scalar() != 1:
            raise ReadOnlyUnavailable(READ_ONLY_REFUSED)
        return fn(conn)
    finally:
        _restore(conn, [f"PRAGMA query_only = {saved}"])


def _version(text: str) -> tuple[int, ...]:
    """``(10, 6, 12)`` from ``10.6.12-MariaDB-log``; ``(0,)`` when it does not start with a number."""
    match = re.match(r"\d+(?:\.\d+)*", text)
    return tuple(int(part) for part in match.group().split(".")) if match else (0,)


def _is_mariadb(conn: Any, version: str = "") -> bool:
    """MariaDB, also behind a ``mysql://`` URL: the dialect's own flag, or ``-MariaDB`` in ``@@version`` when read."""
    dialect = conn.dialect
    return dialect.name == "mariadb" or getattr(dialect, "is_mariadb", False) is True or "mariadb" in version.lower()


def _number(value: Any) -> int | float:
    """A session value as a number, so it can only ever be written back as one (``float`` raises otherwise)."""
    number = float(value)
    return int(number) if number.is_integer() else number


def _mysql_read_only[T](conn: Any, fn: Callable[[Any], T], statement_timeout: float, lock_timeout: float) -> T:
    """The session characteristic, not ``START TRANSACTION READ ONLY``: only ``@@SESSION`` can be read back.

    pymysql's ``autocommit`` is a method, so autocommit is asked of the server: under it each statement is its own
    transaction and the timeouts and the rollback mean nothing, so the read is refused.
    """
    options: dict[str, Any] = conn.get_execution_options() if hasattr(conn, "get_execution_options") else {}
    if str(options.get("isolation_level", "")).upper() == "AUTOCOMMIT":
        raise ReadOnlyUnavailable(READ_ONLY_REFUSED)
    version = str(conn.exec_driver_sql("SELECT @@version").scalar())
    mariadb = _is_mariadb(conn, version)
    modern = _version(version) >= ((11, 1) if mariadb else (5, 7, 20))
    read_only = "transaction_read_only" if modern else "tx_read_only"
    if mariadb:
        timeout, value = "max_statement_time", round(max(statement_timeout, 0.001), 3)
    else:
        timeout, value = "max_execution_time", max(1, int(statement_timeout * 1000))
    if _number(conn.exec_driver_sql("SELECT @@SESSION.autocommit").scalar() or 0) != 0:
        raise ReadOnlyUnavailable(READ_ONLY_REFUSED)
    names = (read_only, timeout, "innodb_lock_wait_timeout")
    saved = {name: _number(conn.exec_driver_sql(f"SELECT @@SESSION.{name}").scalar() or 0) for name in names}
    conn.rollback()  # SQLAlchemy's own, so its state stays in step; the next transaction takes the session value
    try:
        conn.exec_driver_sql(f"SET SESSION {read_only} = 1")
        conn.exec_driver_sql(f"SET SESSION {timeout} = {value}")
        conn.exec_driver_sql(f"SET SESSION innodb_lock_wait_timeout = {max(1, math.ceil(lock_timeout))}")
        if _number(conn.exec_driver_sql(f"SELECT @@SESSION.{read_only}").scalar() or 0) != 1:
            raise ReadOnlyUnavailable(READ_ONLY_REFUSED)
        return fn(conn)
    finally:
        _restore(conn, [f"SET SESSION {name} = {saved[name]}" for name in names])


def bounded[T](conn: Any, fn: Callable[[Any], T], timeout: float) -> T:
    """``fn(conn)`` with the server-side statement timeout set to ``timeout`` where the dialect has one.

    PostgreSQL's ``SET LOCAL`` ends with the transaction. MySQL's session value (MariaDB's ``max_statement_time``, in
    seconds, also behind a ``mysql://`` URL) is put back, because the connection goes back to the app's pool; a server
    without the variable runs the read unbounded. sqlite has none: its wait is the driver's busy timeout.
    """
    name = conn.dialect.name
    if name == "postgresql":
        conn.exec_driver_sql(f"SET LOCAL statement_timeout = {max(1, int(timeout * 1000))}")
    elif name in ("mysql", "mariadb"):
        if _is_mariadb(conn):
            variable, convert, value = "max_statement_time", float, round(max(timeout, 0.001), 3)
        else:
            variable, convert, value = "max_execution_time", int, max(1, int(timeout * 1000))
        try:
            previous = convert(conn.exec_driver_sql(f"SELECT @@SESSION.{variable}").scalar() or 0)
        except Exception:  # noqa: BLE001 - MySQL before 5.7.8 has no such variable
            return fn(conn)
        conn.exec_driver_sql(f"SET SESSION {variable} = {value}")
        try:
            return fn(conn)
        finally:
            try:
                conn.exec_driver_sql(f"SET SESSION {variable} = {previous}")
            except BaseException:
                conn.invalidate()  # never hand the app's pool a connection that keeps sharpit's timeout
                raise
    return fn(conn)


async def run_db_read[T](
    engine: Any,
    fn: Callable[[Any], T],
    budget: float,
    *,
    executor: Executor | None = None,
    done: Callable[[], None] | None = None,
    wall_timeout: float | None = None,
    statement_timeout: float | None = None,
    read_only: bool = False,
    lock_timeout: float | None = None,
) -> T:
    """Run ``fn(connection)`` for sharpit's own read, off the event loop and invisible to SQL Trace.

    An async dialect runs through ``AsyncEngine.run_sync`` (the driver needs the loop); a sync one in a thread, on
    ``executor`` when given. The statement timeout is set inside the read (``bounded``). The connect wait is the
    driver's own connect timeout: setting one would need a hook on every app connection or a copy of the app's engine.
    ``done`` runs once the read really ended: a sync read that timed out keeps its thread (Python cannot stop it), so
    ``done`` waits for that thread when it runs on ``executor``; single-flight callers release on it.
    """
    wall = budget if wall_timeout is None else wall_timeout
    stmt = budget if statement_timeout is None else statement_timeout
    lock = () if lock_timeout is None else (lock_timeout,)  # bounded_read_only's own default otherwise
    sync = getattr(engine, "sync_engine", engine)
    with internal():  # the thread and the greenlet copy this context, so the listeners see the marker
        try:
            if read_only and _shares_its_connection(sync):  # before the checkout: its return rolls the app's work back
                raise ReadOnlyUnavailable(READ_ONLY_REFUSED)
            async with asyncio.timeout(wall):
                if sync.dialect.is_async:
                    from sqlalchemy.ext.asyncio import AsyncEngine  # noqa: PLC0415 - only once the app imported it

                    # shortcut: on timeout `done` fires once the await is cancelled, while the driver's own thread
                    # (aiosqlite) may still run the call, so one extra read can overlap; track the driver if it matters
                    async_engine = engine if isinstance(engine, AsyncEngine) else AsyncEngine(sync)
                    async with async_engine.connect() as conn:
                        if read_only:
                            return await conn.run_sync(bounded_read_only, fn, stmt, *lock)
                        return await conn.run_sync(bounded, fn, stmt)

                def read() -> T:
                    with sync.connect() as conn:
                        return bounded_read_only(conn, fn, stmt, *lock) if read_only else bounded(conn, fn, stmt)

                if executor is None:
                    return await asyncio.to_thread(read)
                work = executor.submit(contextvars.copy_context().run, read)
                if done is not None:
                    # fires when the thread returns, or at once when the queued read is cancelled before it starts
                    work.add_done_callback(lambda _work, done=done: done())
                    done = None
                return await asyncio.wrap_future(work)
        finally:
            if done is not None:
                done()
