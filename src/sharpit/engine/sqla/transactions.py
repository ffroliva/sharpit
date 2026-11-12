"""The ``transaction`` journal source: one event per completed database transaction (BootUI ``TransactionPayload``).

SQLAlchemy's ``Connection`` events see every transaction exactly once, whatever opened it: ``engine.begin()``,
autobegin on ``connect()``, a ``Session`` (it runs on a ``Connection``) and an async engine (its ``sync_engine``
connection), and ``begin_nested`` for a savepoint. ``Session`` events would miss Core use. The listeners are
class-level on ``Engine``, wired by ``listeners``; this module only holds them.

Metadata only: no SQL text, no parameter, no connection URL.
"""

from __future__ import annotations

import sys
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from sharpit.engine import otel
from sharpit.engine.capture.correlation import INTERNAL, REQUEST, RequestInfo
from sharpit.engine.capture.sqltrace import call_site
from sharpit.engine.sources import dispatch  # the module, not its names: dispatch imports this package

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

SOURCE = "transaction"
HOOK = "transaction journal"
TRANSACTION_EVENTS = ("begin", "commit", "rollback", "savepoint", "release_savepoint", "rollback_savepoint")
_ATTRIBUTE = "_sharpit_tx"  # on the ``Connection``, like ``_sharpit_start`` on an execution context
_FRAMES = 8  # how far up the stack a rollback looks for the SQLAlchemy call that caused it


@dataclass(slots=True)
class _Tx:
    started_ns: int
    epoch_ms: int
    thread: str
    trace_id: str | None
    request: RequestInfo | None
    method: str | None
    nested: bool
    savepoint: bool
    read_only: bool
    isolation: str | None
    targets: list[SharpitContext]
    name: str | None = None
    open: bool = True
    savepoints: list[_Tx] = field(default_factory=list["_Tx"])


# the physical transactions begun in this context: ``nested`` is "another one is still open here" (REQUIRES_NEW)
_ACTIVE: ContextVar[tuple[_Tx, ...]] = ContextVar("sharpit_transactions", default=())


def _options(conn: Any) -> tuple[str | None, bool]:
    options = conn.get_execution_options()
    level = options.get("isolation_level")
    isolation = str(level).upper().replace(" ", "_") if level else None
    return isolation, bool(options.get("postgresql_readonly"))


def _begun(conn: Any, targets: list[SharpitContext], *, savepoint: bool, name: str | None = None) -> _Tx:
    isolation, read_only = _options(conn)
    wants_site = any(c.capture.sql_trace and c.capture.sql_trace.capture_call_site for c in targets)
    live = tuple(t for t in _ACTIVE.get() if t.open)
    return _Tx(
        time.perf_counter_ns(), time.time_ns() // 1_000_000, threading.current_thread().name,
        otel.current_trace_id(), REQUEST.get(), call_site(None) if wants_site else None, savepoint or bool(live),
        savepoint, read_only, isolation, targets, name,
    )  # fmt: skip


def _event(
    ctx: SharpitContext, tx: _Tx, ended_ns: int, completion: str, *, rolled_back: bool
) -> dict[str, str | int | bool | None]:
    """BootUI's ``transaction`` journal event (``TransactionPayload`` and its envelope).

    ``method`` is the application frame that began it (BootUI's ``@Transactional`` method has no Python twin);
    ``rollbackOnly``, ``failureClass`` and the ORM counts are unknown (``False``, ``None``, ``-1``); ``completion`` is
    an extra label: ``COMMIT``, ``ROLLBACK`` (asked for), ``CLOSE`` (SQLAlchemy rolled back a transaction that was
    never committed, which ``rolledBack`` does not claim) or, for a savepoint, ``RELEASE``."""
    info = tx.request
    return {
        "source": SOURCE,
        "epochMillis": tx.epoch_ms,
        "durationNanos": max(0, ended_ns - tx.started_ns),
        "traceId": tx.trace_id,
        "requestId": info.id if info is not None and info.context_id == ctx.context_id else None,
        "thread": tx.thread,
        "method": tx.method,
        "rolledBack": rolled_back,
        "nested": tx.nested,
        "savepoint": tx.savepoint,
        "startNanos": tx.started_ns,
        "readOnly": tx.read_only,
        "isolation": tx.isolation,
        "rollbackOnly": False,
        "failureClass": None,
        "ormStatements": -1,
        "ormFlushes": -1,
        "ormDirtyEntities": -1,
        "completion": completion,
    }


def _finish(tx: _Tx, completion: str, *, rolled_back: bool) -> None:
    ended = time.perf_counter_ns()
    tx.open = False
    for ctx in tx.targets:
        dispatch.offer_journal(ctx, lambda ctx=ctx: _event(ctx, tx, ended, completion, rolled_back=rolled_back), HOOK)


def _attached(conn: Any) -> _Tx | None:
    return cast("_Tx | None", conn.__dict__.get(_ATTRIBUTE))


def _detach(conn: Any) -> _Tx | None:
    return cast("_Tx | None", conn.__dict__.pop(_ATTRIBUTE, None))


def begin(conn: Any) -> None:
    try:
        if INTERNAL.get():
            return
        targets = dispatch.journal_targets(conn.engine, SOURCE)
        if not targets:
            return
        tx = _begun(conn, targets, savepoint=False)
        setattr(conn, _ATTRIBUTE, tx)
        _ACTIVE.set((*(t for t in _ACTIVE.get() if t.open), tx))
    except Exception as exc:  # noqa: BLE001 - a listener never changes the host's transaction
        dispatch.routing_failed(exc)


def _implicit_close() -> bool:
    """Whether SQLAlchemy is rolling back because the connection or session was closed with no commit, not because the
    application asked: a read-only request ends that way. Unknown reads as a rollback."""
    frame = sys._getframe(2)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    for _ in range(_FRAMES):
        if frame is None:
            return False
        name = frame.f_code.co_name
        if name in {"_do_close", "_do_rollback"}:
            return name == "_do_close"
        frame = frame.f_back
    return False


def commit(conn: Any) -> None:
    try:
        tx = _detach(conn)
        if tx is not None:
            _finish(tx, "COMMIT", rolled_back=False)
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def rollback(conn: Any) -> None:
    try:
        tx = _detach(conn)
        if tx is not None:
            closing = _implicit_close()
            _finish(tx, "CLOSE" if closing else "ROLLBACK", rolled_back=not closing)
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def savepoint(conn: Any, name: str) -> None:
    try:
        root = _attached(conn)
        if root is not None:
            root.savepoints.append(_begun(conn, root.targets, savepoint=True, name=name))
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def _end_savepoint(conn: Any, name: str, completion: str, *, rolled_back: bool) -> None:
    try:
        root = _attached(conn)
        if root is None:
            return
        for index in range(len(root.savepoints) - 1, -1, -1):
            if root.savepoints[index].name in {name, None}:  # the event can fire before the name is set
                tx = root.savepoints[index]
                del root.savepoints[index:]  # a savepoint's own inner ones end with it
                _finish(tx, completion, rolled_back=rolled_back)
                return
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def release_savepoint(conn: Any, name: str, context: Any) -> None:
    del context
    _end_savepoint(conn, name, "RELEASE", rolled_back=False)


def rollback_savepoint(conn: Any, name: str, context: Any) -> None:
    del context
    _end_savepoint(conn, name, "ROLLBACK", rolled_back=True)
