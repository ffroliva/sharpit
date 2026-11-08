"""Transactions captured from SQLAlchemy connection events, without querying the database."""

from __future__ import annotations

import itertools
import threading
import time
import weakref
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from sharpit.engine import sqla
from sharpit.engine.capture.correlation import INTERNAL, REQUEST
from sharpit.engine.capture.sqltrace import call_site
from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.masking import Masker
from sharpit.engine.sources import dispatch
from sharpit.engine.sqla.dialect_source import exception_dialect
from sharpit.engine.sqla.events import add_pool_listener
from sharpit.engine.sqltext import Dialect, error_text

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

PAUSED = "Recording is paused. Resume it to capture new transactions."
NO_SQL_TRACE = "SQL Trace is not active, so SQL statement/connection counts are not correlated."

REPORT_KEYS = (
    "available",
    "unavailableReason",
    "capturing",
    "bufferSize",
    "totalCaptured",
    "slowTransactionThresholdMillis",
    "connectionHoldThresholdMillis",
    "stats",
    "entries",
    "warnings",
)
STATS_KEYS = (
    "totalTransactions",
    "totalDurationMillis",
    "maxDurationMillis",
    "avgDurationMillis",
    "slowTransactions",
    "connectionHeldTransactions",
    "committedCount",
    "rolledBackCount",
    "unknownCount",
    "nestedCount",
    "evicted",
)
ENTRY_KEYS = (
    "id",
    "methodName",
    "propagation",
    "isolation",
    "status",
    "startTimestamp",
    "endTimestamp",
    "durationMillis",
    "parentId",
    "thread",
    "traceId",
    "sqlStatementCount",
    "connectionCount",
    "readOnly",
    "slow",
    "connectionHeld",
    "errorMessage",
)


def _empty_stats() -> dict[str, int | float]:
    return dict.fromkeys(STATS_KEYS, 0)


def unavailable_report(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "unavailableReason": reason,
        "capturing": False,
        "bufferSize": 0,
        "totalCaptured": 0,
        "slowTransactionThresholdMillis": 0,
        "connectionHoldThresholdMillis": 0,
        "stats": _empty_stats(),
        "entries": [],
        "warnings": [],
    }


def context_report(ctx: SharpitContext) -> dict[str, Any]:
    """Read a snapshot, correlating only already-captured SQL Trace rows."""
    recorder = ctx.capture.transactions
    if not isinstance(recorder, TransactionRecorder):
        reason = (
            "Transactions are disabled via SHARPIT_TRANSACTIONS_ENABLED=false"
            if not ctx.settings.transactions_enabled
            else "Transaction capture is not installed"
        )
        return unavailable_report(reason)
    trace = ctx.capture.sql_trace
    rows = trace.report([])["entries"] if trace is not None and ctx.settings.sql_trace_enabled else None
    return recorder.report(rows)


class TransactionRecorder:
    """A bounded transaction ring. Event callbacks mutate rows; report-time work only reads cached rows."""

    def __init__(
        self,
        masker: Masker,
        *,
        application: Callable[[], Dialect | None],
        max_entries: int = 200,
        slow_threshold_ms: int = 200,
        hold_threshold_ms: int = 500,
        recording: bool = True,
    ) -> None:
        self._masker = masker
        self._application = application
        self.max_entries = max(1, max_entries)
        self.slow_threshold_ms = slow_threshold_ms
        self.hold_threshold_ms = hold_threshold_ms
        self.recording = recording
        self._entries: deque[dict[str, Any]] = deque()
        self._open: dict[int, dict[str, Any]] = {}
        self._unsettled: dict[int, dict[str, Any]] = {}
        self._ids = itertools.count(1)
        self._total = 0
        self._evicted = 0
        self._evicted_open = 0
        self._lock = threading.RLock()
        self.changes = ChangeStream()

    def begin(
        self,
        key: int,
        *,
        parent: int | None,
        method: str,
        thread: str,
        trace_id: str | None,
        connection_id: str | None,
    ) -> int:
        if not self.recording:
            return -1
        now = time.time_ns()
        with self._lock:
            entry_id = next(self._ids)
            while len(self._entries) >= self.max_entries:
                if not self._evict_completed_locked():
                    break
            if len(self._entries) >= 2 * self.max_entries:
                # Open rows may outlive capacity (a long transaction) but never twice it: a connection dropped
                # without an end event would otherwise grow the ring forever.
                stale = self._entries.popleft()
                self._open.pop(stale["id"], None)
                self._evicted += 1
                self._evicted_open += 1
            row = {
                "id": entry_id,
                "methodName": method or "unknown",
                "propagation": "PARTICIPATING" if parent is not None else "NEW",
                "isolation": "UNKNOWN",  # never queried; BootUI reports UNKNOWN when it cannot tell
                "status": "OPEN",
                "startTimestamp": now // 1_000_000,
                "endTimestamp": None,
                "durationMillis": 0,
                "parentId": parent,
                "thread": thread,
                "traceId": trace_id,
                "sqlStatementCount": 0,
                "connectionCount": 1,
                "readOnly": None,
                "slow": False,
                "connectionHeld": False,
                "errorMessage": None,
                "_startedNs": now,
                "_connectionId": connection_id,
                "_key": key,
            }
            self._entries.append(row)
            self._open[entry_id] = row
            self._total += 1
        return entry_id

    def end(self, entry_id: int, status: str, error: BaseException | None = None, *, settle: bool = False) -> None:
        """Close an open row; ``settle=True`` lets ``settle`` re-close it once the DBAPI commit has returned."""
        if entry_id < 0:
            return
        with self._lock:
            row = self._open.pop(entry_id, None)
            if row is None:
                return
            self._close_locked(row, status, error)
            if settle:
                self._unsettled[entry_id] = row
            while len(self._entries) > self.max_entries:
                if not self._evict_completed_locked():
                    break
        self.changes.signal()

    def settle(self, entry_id: int, error: BaseException | None = None) -> None:
        """The DBAPI commit returned (``error`` None) or failed: re-close the row so its duration includes it."""
        with self._lock:
            row = self._unsettled.pop(entry_id, None)
            if row is None:
                return
            self._close_locked(row, "COMMITTED" if error is None else "UNKNOWN", error)
        self.changes.signal()

    def _close_locked(self, row: dict[str, Any], status: str, error: BaseException | None) -> None:
        now = time.time_ns()
        duration = max(0, (now - row["_startedNs"]) // 1_000_000)
        row["endTimestamp"] = now // 1_000_000
        row["durationMillis"] = duration
        row["status"] = status if status in {"COMMITTED", "ROLLED_BACK", "UNKNOWN"} else "UNKNOWN"
        row["slow"] = self.slow_threshold_ms > 0 and duration >= self.slow_threshold_ms
        row["connectionHeld"] = self.hold_threshold_ms > 0 and duration >= self.hold_threshold_ms
        if error is not None:
            row["errorMessage"] = error_text(
                self._masker, error, exception_dialect(error, self._application)
            ) or self._masker.mask_text(type(error).__name__)

    def _evict_completed_locked(self) -> bool:
        for row in self._entries:
            if row["endTimestamp"] is not None:
                self._entries.remove(row)
                self._unsettled.pop(row["id"], None)
                self._evicted += 1
                return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._open.clear()
            self._unsettled.clear()
        self.changes.signal()

    def set_recording(self, enabled: bool) -> None:
        if self.recording != enabled:
            self.recording = enabled
            self.changes.signal()

    def report(self, sql_rows: list[dict[str, Any]] | None) -> dict[str, Any]:
        with self._lock:
            rows = [dict(row) for row in self._entries]
            total, evicted, evicted_open = self._total, self._evicted, self._evicted_open
        warnings = [] if sql_rows is not None else [NO_SQL_TRACE]
        for row in rows:
            if sql_rows is not None:
                row["sqlStatementCount"] = (
                    sum(
                        sql.get("connectionId") == row["_connectionId"]
                        and row["startTimestamp"] <= sql["timestamp"] <= (row["endTimestamp"] or row["startTimestamp"])
                        for sql in sql_rows
                    )
                    if row["_connectionId"] is not None
                    else 0
                )
            for key in ("_startedNs", "_connectionId", "_key"):
                row.pop(key, None)
        stats = _empty_stats()
        durations = [row["durationMillis"] for row in rows if row["endTimestamp"] is not None]
        stats.update(
            totalTransactions=len(rows),
            totalDurationMillis=sum(durations),
            maxDurationMillis=max(durations, default=0),
            avgDurationMillis=(sum(durations) / len(durations)) if durations else 0.0,
            slowTransactions=sum(row["slow"] for row in rows),
            connectionHeldTransactions=sum(row["connectionHeld"] for row in rows),
            committedCount=sum(row["status"] == "COMMITTED" for row in rows),
            rolledBackCount=sum(row["status"] == "ROLLED_BACK" for row in rows),
            unknownCount=sum(row["status"] == "UNKNOWN" for row in rows) + evicted_open,
            nestedCount=sum(row["parentId"] is not None for row in rows),
            evicted=evicted,
        )
        # Keep the report stable if an event ends a transaction while the DTO is being assembled.
        return {
            "available": True,
            "unavailableReason": None,
            "capturing": self.recording,
            "bufferSize": self.max_entries,
            "totalCaptured": total,
            "slowTransactionThresholdMillis": self.slow_threshold_ms,
            "connectionHoldThresholdMillis": self.hold_threshold_ms,
            "stats": stats,
            "entries": [{key: row[key] for key in ENTRY_KEYS} for row in reversed(rows)],
            "warnings": warnings,
        }


def _enabled(ctx: SharpitContext) -> TransactionRecorder | None:
    recorder = ctx.capture.transactions
    if (
        isinstance(recorder, TransactionRecorder)
        and ctx.settings.transactions_enabled
        and ctx.settings.panels["transactions"].enabled
        and recorder.recording
    ):
        return recorder
    return None


def _targets(conn: Any) -> list[SharpitContext]:
    if INTERNAL.get():
        return []
    # valuerefs, not values: once per begin, and values is a generator under an iteration guard; read lock-free
    contexts = [ctx for ref in _contexts.valuerefs() if (ctx := ref()) is not None]
    info = REQUEST.get()
    if info is not None:
        return [ctx for ctx in contexts if ctx.context_id == info.context_id]
    engine = getattr(conn, "engine", None)
    held = [
        ctx for ctx in contexts if ctx.capture.engine_registry is not None and ctx.capture.engine_registry.holds(engine)
    ]
    if held:
        return held
    fallback: list[SharpitContext] = []
    try:
        fallback = dispatch._targets(engine)  # pyright: ignore[reportPrivateUsage]  # SQL Trace fallback for unregistered engines
    except Exception as exc:  # noqa: BLE001 - transaction listeners must not affect the host
        dispatch.routing_failed(exc)
    return fallback or (contexts if len(contexts) == 1 else [])


def _connection_id(conn: Any) -> str | None:
    try:
        return hex(id(conn.connection.dbapi_connection))
    except Exception:  # noqa: BLE001 - invalidated connection
        return None


# conn.info outlives a context on a pooled connection, so it holds recorders weakly, never a context.
Tracked = tuple["weakref.ref[TransactionRecorder]", int]
PENDING_COMMIT = "sharpit_tx_pending_commit"


def _stack(info: dict[str, Any]) -> list[Tracked]:
    return info.setdefault("sharpit_tx", [])


def _savepoints(info: dict[str, Any]) -> list[tuple[str | None, list[Tracked]]]:
    """Open savepoints, innermost last; one frame per savepoint event, empty when nothing was recorded."""
    return info.setdefault("sharpit_tx_savepoints", [])


def _close(items: list[Tracked], status: str) -> None:
    for ref, entry_id in items:
        recorder = ref()
        if recorder is not None:
            try:
                recorder.end(entry_id, status, settle=status == "COMMITTED")
            except Exception as exc:  # noqa: BLE001 - never alter the application's transaction
                dispatch.routing_failed(exc)


def _settle(info: dict[str, Any], error: BaseException | None = None) -> None:
    for ref, entry_id in info.pop(PENDING_COMMIT, ()):
        recorder = ref()
        if recorder is not None:
            recorder.settle(entry_id, error)


def _begin(conn: Any, parent_ids: dict[int, int] | None = None) -> None:
    conn_info = conn.info  # a property chain: one read per listener
    stack = _stack(conn_info)
    if parent_ids is None:
        _close(stack, "UNKNOWN")
        stack.clear()
        _savepoints(conn_info).clear()
    parents = parent_ids or {}
    info = REQUEST.get()
    connection_id = _connection_id(conn)
    for ctx in _targets(conn):
        recorder = _enabled(ctx)
        if recorder is None:
            continue
        try:
            parent = parents.get(id(recorder))
            method = call_site(None) if ctx.settings.sql_trace_capture_call_site else "unknown"
            entry_id = recorder.begin(
                id(conn),
                parent=parent,
                method=method or "unknown",
                thread=threading.current_thread().name,
                trace_id=info.id if info is not None and info.context_id == ctx.context_id else None,
                connection_id=connection_id,
            )
            if entry_id >= 0:
                stack.append((weakref.ref(recorder), entry_id))
        except Exception as exc:  # noqa: BLE001 - never alter the application's transaction
            dispatch._context_failed(ctx, exc)  # pyright: ignore[reportPrivateUsage]


def _end(info: dict[str, Any], status: str) -> None:
    stack = _stack(info)
    closing, stack[:] = stack[:], []
    _savepoints(info).clear()
    _close(closing, status)


def _end_savepoint(conn: Any, name: str, status: str) -> None:
    stack = _stack(conn.info)
    savepoints = _savepoints(conn.info)
    names = [frame_name for frame_name, _ in savepoints]
    # SQLAlchemy emits savepoint(name=None) before generating its sa_savepoint_N name: match the innermost unnamed.
    key = name if name in names else None
    if key not in names:
        return
    depth = len(names) - 1 - names[::-1].index(key)
    tracked = {id(item) for _, frame in savepoints[depth:] for item in frame}  # inner savepoints end with their outer
    del savepoints[depth:]
    closing = [item for item in stack if id(item) in tracked]
    stack[:] = [item for item in stack if id(item) not in tracked]
    _close(closing, status)


def tx_begin(conn: Any) -> None:
    try:
        _settle(conn.info)
        _begin(conn)
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def tx_commit(conn: Any) -> None:
    try:
        info = conn.info  # a property chain: one read per listener
        info[PENDING_COMMIT] = list(_stack(info))
        _end(info, "COMMITTED")
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def tx_rollback(conn: Any) -> None:
    try:
        _settle(conn.info)
        _end(conn.info, "ROLLED_BACK")
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def tx_handle_error(exception_context: Any) -> None:
    try:
        conn = exception_context.connection
        if exception_context.statement is not None or conn is None or PENDING_COMMIT not in conn.info:
            return
        error = exception_context.sqlalchemy_exception or exception_context.original_exception
        # Only an error raised while the committing transaction is still active is the DBAPI commit failing.
        _settle(conn.info, error if conn.in_transaction() else None)
    except Exception as exc:  # noqa: BLE001 - never affect the application's transaction
        dispatch.routing_failed(exc)


def tx_checkin(_dbapi_connection: Any, connection_record: Any) -> None:
    """The connection went back to the pool, so its last commit has returned."""
    try:
        if connection_record is not None:
            _settle(connection_record.info)
    except Exception as exc:  # noqa: BLE001 - never affect the pool
        dispatch.routing_failed(exc)


def tx_savepoint(conn: Any, name: str | None) -> None:
    try:
        stack = _stack(conn.info)
        parents = {id(recorder): entry_id for ref, entry_id in stack if (recorder := ref()) is not None}
        before = len(stack)
        _begin(conn, parents)
        _savepoints(conn.info).append((name, stack[before:]))
    except Exception as exc:  # noqa: BLE001 - never affect the application's transaction
        dispatch.routing_failed(exc)


def tx_rollback_savepoint(conn: Any, name: str, context: object) -> None:
    try:
        _end_savepoint(conn, name, "ROLLED_BACK")
    except Exception as exc:  # noqa: BLE001 - never affect the application's transaction
        dispatch.routing_failed(exc)


def tx_release_savepoint(conn: Any, name: str, context: object) -> None:
    try:
        _end_savepoint(conn, name, "COMMITTED")
    except Exception as exc:  # noqa: BLE001 - never affect the application's transaction
        dispatch.routing_failed(exc)


CONNECTION_CALLBACKS: dict[str, Callable[..., None]] = {
    "begin": tx_begin,
    "commit": tx_commit,
    "rollback": tx_rollback,
    "savepoint": tx_savepoint,
    "rollback_savepoint": tx_rollback_savepoint,
    "release_savepoint": tx_release_savepoint,
    "handle_error": tx_handle_error,
}
_attach_lock = threading.Lock()
_attach_count = 0
_attach_removers: list[Callable[[], None]] = []
_contexts_lock = threading.Lock()
_contexts: weakref.WeakValueDictionary[str, SharpitContext] = weakref.WeakValueDictionary()
_context_attachments: dict[str, int] = {}  # live attachments per context id: one remove() must not unroute the rest


def _release_attachment() -> None:
    global _attach_count  # noqa: PLW0603
    with _attach_lock:
        _attach_count -= 1
        if _attach_count == 0:
            while _attach_removers:
                _attach_removers.pop()()


def _listen() -> list[Callable[[], None]] | None:
    """Every class listener's remover, or ``None`` (nothing left attached) while SQLAlchemy is not imported."""
    removers: list[Callable[[], None]] = []
    for event, callback in CONNECTION_CALLBACKS.items():
        remover = sqla.add_connection_listener(cast(Any, event), callback)
        if remover is None:
            for attached in reversed(removers):
                attached()
            return None
        removers.append(remover)
    checkin = add_pool_listener("checkin", tx_checkin)
    return [*removers, checkin] if checkin is not None else removers


def attach(ctx: SharpitContext | None = None) -> Callable[[], None] | None:
    """Attach the shared class listeners once and return a per-context reference-counted remover."""
    global _attach_count, _attach_removers  # noqa: PLW0603
    with _attach_lock:
        if _attach_count == 0:
            removers = _listen()
            if removers is None:
                return None
            _attach_removers = removers
        _attach_count += 1
    if ctx is not None:
        with _contexts_lock:
            _contexts[ctx.context_id] = ctx
            _context_attachments[ctx.context_id] = _context_attachments.get(ctx.context_id, 0) + 1

    released = False

    def remove() -> None:
        nonlocal released
        with _attach_lock:
            if released:
                return
            released = True
        _release_attachment()
        if ctx is not None:
            with _contexts_lock:
                left = _context_attachments.pop(ctx.context_id, 1) - 1
                if left > 0:
                    _context_attachments[ctx.context_id] = left
                else:
                    _contexts.pop(ctx.context_id, None)

    return remove
