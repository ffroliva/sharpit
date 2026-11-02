"""Transactions captured from SQLAlchemy connection events, without querying the database."""

from __future__ import annotations

import itertools
import threading
import time
import weakref
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from sharpit.engine import sqla
from sharpit.engine.capture.correlation import INTERNAL, REQUEST
from sharpit.engine.capture.sqltrace import call_site
from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.masking import Masker
from sharpit.engine.sources import dispatch

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
        max_entries: int = 200,
        slow_threshold_ms: int = 200,
        hold_threshold_ms: int = 500,
        recording: bool = True,
    ) -> None:
        self._masker = masker
        self.max_entries = max(1, max_entries)
        self.slow_threshold_ms = slow_threshold_ms
        self.hold_threshold_ms = hold_threshold_ms
        self.recording = recording
        self._entries: deque[dict[str, Any]] = deque()
        self._open: dict[int, dict[str, Any]] = {}
        self._ids = itertools.count(1)
        self._total = 0
        self._evicted = 0
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
            if len(self._entries) >= self.max_entries:
                removed = self._entries.popleft()
                self._open.pop(removed["id"], None)
                self._evicted += 1
            row = {
                "id": entry_id,
                "methodName": method or "unknown",
                "propagation": "PARTICIPATING" if parent is not None else "NEW",
                "isolation": None,
                "status": "UNKNOWN",
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

    def end(self, entry_id: int, status: str, error: BaseException | None = None) -> None:
        if entry_id < 0:
            return
        with self._lock:
            row = self._open.pop(entry_id, None)
            if row is None:
                return
            now = time.time_ns()
            duration = max(0, (now - row["_startedNs"]) // 1_000_000)
            row["endTimestamp"] = now // 1_000_000
            row["durationMillis"] = duration
            row["status"] = status if status in {"COMMITTED", "ROLLED_BACK", "UNKNOWN"} else "UNKNOWN"
            row["slow"] = self.slow_threshold_ms >= 0 and duration >= self.slow_threshold_ms
            row["connectionHeld"] = self.hold_threshold_ms >= 0 and duration >= self.hold_threshold_ms
            if error is not None:
                row["errorMessage"] = self._masker.mask_text(str(error))
        self.changes.signal()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._open.clear()
        self.changes.signal()

    def set_recording(self, enabled: bool) -> None:
        if self.recording != enabled:
            self.recording = enabled
            self.changes.signal()

    def report(self, sql_rows: list[dict[str, Any]] | None) -> dict[str, Any]:
        with self._lock:
            rows = [dict(row) for row in self._entries]
            total, evicted = self._total, self._evicted
        warnings = [] if sql_rows is not None else [NO_SQL_TRACE]
        for row in rows:
            if sql_rows is not None:
                row["sqlStatementCount"] = (
                    sum(
                        sql.get("connectionId") == row["_connectionId"]
                        and row["startTimestamp"]
                        <= _sql_timestamp(sql.get("timestamp"))
                        <= (row["endTimestamp"] or row["startTimestamp"])
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
            unknownCount=sum(row["status"] == "UNKNOWN" for row in rows),
            nestedCount=sum(row["parentId"] is not None for row in rows),
            evicted=evicted,
        )
        # Keep the report stable if an event ends a transaction while the DTO is being assembled.
        return {
            "available": True,
            "unavailableReason": None,
            "capturing": self.recording,
            "bufferSize": len(rows),
            "totalCaptured": total,
            "slowTransactionThresholdMillis": self.slow_threshold_ms,
            "connectionHoldThresholdMillis": self.hold_threshold_ms,
            "stats": stats,
            "entries": [{key: row[key] for key in ENTRY_KEYS} for row in reversed(rows)],
            "warnings": warnings,
        }


def _sql_timestamp(value: object) -> int:
    if isinstance(value, int | float):
        return int(value // 1_000_000 if value > 10**14 else value)
    if isinstance(value, str):
        try:
            return int(datetime.fromisoformat(value).timestamp() * 1000)
        except ValueError:
            return 0
    return 0


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
    try:
        return dispatch._targets(conn.engine)  # pyright: ignore[reportPrivateUsage]
    except Exception as exc:  # noqa: BLE001 - transaction listeners must not affect the host
        dispatch.routing_failed(exc)
        return []


def _connection_id(conn: Any) -> str | None:
    try:
        return hex(id(conn.connection.dbapi_connection))
    except Exception:  # noqa: BLE001 - invalidated connection
        return None


def _stack(conn: Any) -> list[tuple[SharpitContext, int]]:
    return cast("list[tuple[SharpitContext, int]]", conn.info.setdefault("sharpit_tx", []))


def _begin(conn: Any, parent_ids: dict[str, int] | None = None) -> None:
    stack = _stack(conn)
    if parent_ids is None:
        for ctx, entry_id in stack:
            recorder = ctx.capture.transactions
            if isinstance(recorder, TransactionRecorder):
                recorder.end(entry_id, "UNKNOWN")
        stack.clear()
    info = REQUEST.get()
    connection_id = _connection_id(conn)
    for ctx in _targets(conn):
        recorder = _enabled(ctx)
        if recorder is None:
            continue
        try:
            parent = parent_ids.get(ctx.context_id) if parent_ids else None
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
                stack.append((ctx, entry_id))
        except Exception as exc:  # noqa: BLE001 - never alter the application's transaction
            dispatch._context_failed(ctx, exc)  # pyright: ignore[reportPrivateUsage]


def _end(conn: Any, status: str, *, name: str | None = None) -> None:
    stack = _stack(conn)
    targets = {ctx.context_id: ctx for ctx in _targets(conn)}
    closing: list[tuple[SharpitContext, int]]
    if name is None:
        closing, stack[:] = stack[:], []
    else:
        closing = []
        closed: set[str] = set()
        for index in range(len(stack) - 1, -1, -1):
            ctx, _ = stack[index]
            if ctx.context_id in targets and ctx.context_id not in closed:
                closing.append(stack.pop(index))
                closed.add(ctx.context_id)
    for ctx, entry_id in closing:
        recorder = ctx.capture.transactions
        if isinstance(recorder, TransactionRecorder):
            try:
                recorder.end(entry_id, status)
            except Exception as exc:  # noqa: BLE001 - never alter the application's transaction
                dispatch._context_failed(ctx, exc)  # pyright: ignore[reportPrivateUsage]


def tx_begin(conn: Any) -> None:
    try:
        _begin(conn)
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def tx_commit(conn: Any) -> None:
    try:
        _end(conn, "COMMITTED")
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def tx_rollback(conn: Any) -> None:
    try:
        _end(conn, "ROLLED_BACK")
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def tx_savepoint(conn: Any, name: str | None) -> None:
    try:
        stack = _stack(conn)
        parents = {ctx.context_id: entry_id for ctx, entry_id in stack}
        _begin(conn, parents)
    except Exception as exc:  # noqa: BLE001 - never affect the application's transaction
        dispatch.routing_failed(exc)


def tx_rollback_savepoint(conn: Any, name: str, context: object) -> None:
    try:
        _end(conn, "ROLLED_BACK", name=name)
    except Exception as exc:  # noqa: BLE001 - never affect the application's transaction
        dispatch.routing_failed(exc)


def tx_release_savepoint(conn: Any, name: str, context: object) -> None:
    try:
        _end(conn, "COMMITTED", name=name)
    except Exception as exc:  # noqa: BLE001 - never affect the application's transaction
        dispatch.routing_failed(exc)


_attach_lock = threading.Lock()
_attach_count = 0
_attach_removers: list[Callable[[], None]] = []


def _release_attachment() -> None:
    global _attach_count  # noqa: PLW0603
    with _attach_lock:
        _attach_count -= 1
        if _attach_count == 0:
            while _attach_removers:
                _attach_removers.pop()()


def attach() -> Callable[[], None] | None:
    """Attach the shared class listeners once and return a per-context reference-counted remover."""
    global _attach_count, _attach_removers  # noqa: PLW0603
    callbacks = {
        "begin": tx_begin,
        "commit": tx_commit,
        "rollback": tx_rollback,
        "savepoint": tx_savepoint,
        "rollback_savepoint": tx_rollback_savepoint,
        "release_savepoint": tx_release_savepoint,
    }
    with _attach_lock:
        if _attach_count == 0:
            removers: list[Callable[[], None]] = []
            for event, callback in callbacks.items():
                remover = sqla.add_connection_listener(cast(Any, event), callback)
                if remover is None:
                    for attached in reversed(removers):
                        attached()
                    return None
                removers.append(remover)
            _attach_removers = removers
        _attach_count += 1

    finalizer: Any

    def remove() -> None:
        finalizer()

    finalizer = weakref.finalize(remove, _release_attachment)
    return remove
