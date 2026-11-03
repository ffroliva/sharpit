"""sharpit's own database reads: off the event loop, bounded by timeouts, read-only where it can be verified."""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
from collections.abc import Callable
from concurrent.futures import Executor
from typing import Any

from sharpit.engine.capture.correlation import INTERNAL, internal

READ_ONLY_REFUSED = "The read-only transaction could not be established, so sharpit skipped this read"


class ReadOnlyUnavailable(Exception):
    """Raised when a PostgreSQL read-only transaction pin cannot be established."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def is_internal() -> bool:
    """Whether the current thread/task is running sharpit's own database read."""
    return INTERNAL.get()


def bounded_read_only[T](
    conn: Any,
    fn: Callable[[Any], T],
    statement_timeout: float,
    lock_timeout: float = 2.0,
) -> T:
    """Run ``fn(conn)`` inside a verified PostgreSQL read-only transaction with statement and lock timeouts."""
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
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
        if name == "mariadb" or getattr(conn.dialect, "is_mariadb", False):
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
    timeout: float,
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
    wall = timeout if wall_timeout is None else wall_timeout
    stmt = timeout if statement_timeout is None else statement_timeout
    lock = () if lock_timeout is None else (lock_timeout,)  # bounded_read_only's own default otherwise
    sync = getattr(engine, "sync_engine", engine)
    with internal():  # the thread and the greenlet copy this context, so the listeners see the marker
        try:
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
