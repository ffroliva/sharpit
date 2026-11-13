"""Transactions captured from SQLAlchemy connection events, without querying the database."""

from __future__ import annotations

import itertools
import sys
import threading
import time
import weakref
from collections import deque
from collections.abc import Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

from sharpit.engine import otel, sqla
from sharpit.engine.capture.correlation import INTERNAL, REQUEST
from sharpit.engine.capture.journal import SCALAR_BYTES
from sharpit.engine.capture.sqltrace import call_site
from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.masking import Masker
from sharpit.engine.sources import dispatch
from sharpit.engine.sqla.dialect_source import exception_dialect
from sharpit.engine.sqla.events import add_pool_listener
from sharpit.engine.sqltext import Dialect, error_text

if TYPE_CHECKING:
    from sharpit.engine.capture.journal import RuntimeJournal
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

JOURNAL_SOURCE = "transaction"
_TX_KEYS = (
    "source", "epochMillis", "durationNanos", "traceId", "requestId", "thread", "method", "rolledBack", "nested",
    "savepoint", "startNanos", "readOnly", "isolation", "rollbackOnly", "failureClass", "ormStatements", "ormFlushes",
    "ormDirtyEntities",
)  # fmt: skip
# every key's length, the source's text and the eleven number or bool fields: what the journal's ``_flat`` charges
_TX_EVENT_BYTES = sum(map(len, _TX_KEYS)) + len(JOURNAL_SOURCE) + 11 * SCALAR_BYTES

type JournalEvent = dict[str, str | int | bool | None]
# the event's fixed parts, built once in BootUI's key order: each event is a copy with its own fields set, cheaper on
# the listener's budget than a dict display of all 18 keys. ``rollbackOnly`` and the ORM counts are unknown here.
_TX_FIXED: JournalEvent = dict.fromkeys(_TX_KEYS) | {
    "source": JOURNAL_SOURCE, "rollbackOnly": False, "ormStatements": -1, "ormFlushes": -1, "ormDirtyEntities": -1,
}  # fmt: skip
# a begin's journal facts, the same for every context: the perf_counter start (BootUI's ``startNanos``, on P-sql's
# ``completedNanos`` clock), the trace id, nested, savepoint, read-only, isolation and the connection's write count
type _Facts = tuple[int, str | None, bool, bool, bool, str | None, int]
# statements on a connection that were not a SELECT, a running count in ``conn.info``: a rollback undoes something
# only when it grew since the begin. A write-free rollback is BootUI's read-only commit (coordinator default, r3).
WRITES = "sharpit_tx_writes"
# what a transaction's journal event keeps from its begin: the journal, this install's request id and the facts.
# Plain tuples: one is built per begin, on the listener's budget.
type JournalStart = tuple[RuntimeJournal, str | None, _Facts]

# the connections whose transaction began in this context: BootUI's thread stack, so ``nested`` is "another one is
# still open here" (REQUIRES_NEW). Weak: a connection dropped without an end event stops counting once collected.
_OPEN: ContextVar[tuple[weakref.ref[Any], ...]] = ContextVar("sharpit_open_transactions", default=())


def _nests(conn: Any) -> bool:
    stack = _OPEN.get()
    if len(stack) == 1 and stack[0]() is conn:  # the same connection again, nothing else open: nothing to change
        return False
    live = tuple(r for r in stack if (other := r()) is not None and other is not conn and other.in_transaction())
    _OPEN.set((*live, weakref.ref(conn)))
    return bool(live)


def _autocommit(conn: Any) -> bool:
    autocommit = getattr(conn, "_is_autocommit_isolation", None)  # SQLAlchemy 2.0+: the option or the engine's level
    return callable(autocommit) and bool(autocommit())


def _facts(conn: Any, conn_info: dict[str, Any], *, savepoint: bool) -> _Facts:
    options = conn.get_execution_options()
    level = options.get("isolation_level")
    isolation = str(level).upper().replace(" ", "_") if level else None
    nested = savepoint or _nests(conn)
    read_only = bool(options.get("postgresql_readonly"))
    writes: int = conn_info.get(WRITES, 0)
    return time.perf_counter_ns(), otel.current_trace_id(), nested, savepoint, read_only, isolation, writes


def _journal_start(
    journal: RuntimeJournal | None,
    conn: Any,
    conn_info: dict[str, Any],
    request_id: str | None,
    *,
    recording: bool,
    savepoint: bool,
    facts: list[_Facts],
) -> JournalStart | None:
    """What the begin keeps for its journal event, or ``None``: no journal; AUTOCOMMIT, where each statement commits
    itself and there is no physical transaction for BootUI to record; or ``transaction`` not a journal source, where a
    recorded transaction only counts its drop (no facts read, no event built). ``facts`` is read once per begin."""
    if journal is None or _autocommit(conn):
        return None
    if not journal.accepts(JOURNAL_SOURCE):
        if recording:  # a paused panel offers nothing then (BootUI ``TransactionRecorder.java:208-211``)
            journal.count_dropped(JOURNAL_SOURCE)
        return None
    if not facts:
        facts.append(_facts(conn, conn_info, savepoint=savepoint))
    return journal, request_id, facts[0]


def _class_name(error: BaseException) -> str:
    cls = type(error)
    return cls.__qualname__ if cls.__module__ == "builtins" else f"{cls.__module__}.{cls.__qualname__}"


def transaction_event(
    row: dict[str, Any], start: JournalStart, error: BaseException | None, writes: int = 0
) -> tuple[JournalEvent, int]:
    """BootUI's ``transaction`` journal event (``TransactionPayload`` and its envelope, ``TransactionRecorder.java``
    315-336) from the panel's completed row, and its charged size: metadata only, never SQL text or a parameter.

    ``method`` is the row's call site (BootUI's ``@Transactional`` method has no Python twin); ``rollbackOnly`` and the
    ORM counts are unknown (``False``, ``-1``); ``failureClass`` names the error that failed the DBAPI commit;
    ``writes`` is the connection's write count at the end: a rollback with no write since the begin undid nothing."""
    _, request_id, (started_ns, trace_id, nested, savepoint, read_only, isolation, begun_writes) = start
    thread: str = row["thread"]
    method: str = row["methodName"]
    failure = None if error is None else _class_name(error)
    record = _TX_FIXED.copy()
    record["epochMillis"] = row["startTimestamp"]
    record["durationNanos"] = max(0, time.perf_counter_ns() - started_ns)
    record["traceId"] = trace_id
    record["requestId"] = request_id
    record["thread"] = thread
    record["method"] = method
    # BootUI: status == ROLLED_BACK (a failed commit is UNKNOWN); a write-free rollback is its read-only commit
    record["rolledBack"] = row["status"] == "ROLLED_BACK" and writes > begun_writes
    record["nested"] = nested
    record["savepoint"] = savepoint
    record["startNanos"] = started_ns
    record["readOnly"] = read_only
    record["isolation"] = isolation
    record["failureClass"] = failure
    return record, (
        _TX_EVENT_BYTES
        + len(thread)
        + len(method)
        + (SCALAR_BYTES if trace_id is None else len(trace_id))
        + (SCALAR_BYTES if request_id is None else len(request_id))
        + (SCALAR_BYTES if isolation is None else len(isolation))
        + (SCALAR_BYTES if failure is None else len(failure))
    )


def _publish(row: dict[str, Any], error: BaseException | None = None, writes: int = 0) -> None:
    """Offer the row's journal event, built here inside the guard: a failing build or offer costs only this event,
    counted dropped, never the panel's row or another context's event."""
    start: JournalStart | None = row.get("_journal")
    if start is None:
        return
    try:
        start[0].offer_flat(*transaction_event(row, start, error, writes))
    except Exception as exc:  # noqa: BLE001 - publishing never disturbs the transaction it observes
        start[0].count_dropped(JOURNAL_SOURCE)
        dispatch.routing_failed(exc)


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


# a panel row's fixed parts, built once in its key order: a begin copies them and sets its own fields (the listener's
# budget). ``isolation`` is never queried: BootUI reports UNKNOWN when it cannot tell.
_ROW_FIXED: dict[str, Any] = {
    "id": 0, "methodName": "unknown", "propagation": "NEW", "isolation": "UNKNOWN", "status": "OPEN",
    "startTimestamp": 0, "endTimestamp": None, "durationMillis": 0, "parentId": None, "thread": "", "traceId": None,
    "sqlStatementCount": 0, "connectionCount": 1, "readOnly": None, "slow": False, "connectionHeld": False,
    "errorMessage": None, "_startedNs": 0, "_connectionId": None, "_key": 0, "_journal": None,
}  # fmt: skip


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
        journal: JournalStart | None = None,
    ) -> int:
        """A row for the panel, or, while it is paused, a journal-only row the panel never shows (BootUI
        ``TransactionRecorder.java:206-211``: a paused panel skips its buffer, the journal keeps recording)."""
        if not self.recording and journal is None:
            return -1
        now = time.time_ns()
        with self._lock:
            entry_id = next(self._ids)
            if self.recording:
                self._make_room_locked()
            if len(self._open) >= 2 * self.max_entries:  # the oldest: an abandoned row never ends
                abandoned = self._open.pop(next(iter(self._open)))
                if (start := abandoned["_journal"]) is not None:
                    start[0].count_dropped(JOURNAL_SOURCE)
            row = _ROW_FIXED.copy()
            row["id"] = entry_id
            row["methodName"] = method or "unknown"
            row["propagation"] = "PARTICIPATING" if parent is not None else "NEW"
            row["startTimestamp"] = now // 1_000_000
            row["parentId"] = parent
            row["thread"] = thread
            row["traceId"] = trace_id
            row["_startedNs"] = now
            row["_connectionId"] = connection_id
            row["_key"] = key
            row["_journal"] = journal
            if self.recording:
                self._entries.append(row)
                self._total += 1
            self._open[entry_id] = row
        return entry_id

    def _make_room_locked(self) -> None:
        while len(self._entries) >= self.max_entries:
            if not self._evict_completed_locked():
                break
        if len(self._entries) >= 2 * self.max_entries:
            # Open rows may outlive capacity (a long transaction) but never twice it: a connection dropped
            # without an end event would otherwise grow the ring forever.
            self._entries.popleft()  # still in ``_open``: its event outlives the panel row (BootUI's ``active`` map)
            self._evicted += 1
            self._evicted_open += 1

    def end(
        self,
        entry_id: int,
        status: str,
        error: BaseException | None = None,
        *,
        settle: bool = False,
        writes: int = 0,
    ) -> None:
        """Close an open row; ``settle=True`` lets ``settle`` re-close it once the DBAPI commit has returned.
        ``writes``: the connection's write count now (``WRITES``)."""
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
        if not settle:  # a commit is offered once its DBAPI commit has returned or failed (``settle``)
            _publish(row, error, writes)

    def settle(self, entry_id: int, error: BaseException | None = None) -> None:
        """The DBAPI commit returned (``error`` None) or failed: re-close the row so its duration includes it."""
        with self._lock:
            row = self._unsettled.pop(entry_id, None)
            if row is None:
                return
            self._close_locked(row, "COMMITTED" if error is None else "UNKNOWN", error)
        self.changes.signal()
        _publish(row, error)

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
                self._entries.remove(row)  # an unsettled row stays in ``_unsettled``: its event is still to come
                self._evicted += 1
                return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()  # open and unsettled rows go on to their event, as BootUI's ``active`` map does
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
    ):  # paused or not: a paused panel still feeds the journal (``_begin``)
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
    # a context whose transactions hook is suspended (low-footprint) is out of every fallback
    fallback = [ctx for ctx in fallback if SOURCE not in getattr(ctx.capture, "suspended_sources", ())]
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


def _close(items: list[Tracked], status: str, *, settle: bool = False, writes: int = 0) -> None:
    for ref, entry_id in items:
        recorder = ref()
        if recorder is not None:
            try:
                recorder.end(entry_id, status, settle=settle, writes=writes)
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
    facts: list[_Facts] = []  # read once, at the first context whose journal records the source
    for ctx in _targets(conn):
        recorder = _enabled(ctx)
        if recorder is None:
            continue
        try:
            request_id = info.id if info is not None and info.context_id == ctx.context_id else None
            journal = _journal_start(
                getattr(ctx.capture, "journal", None),  # a capture state without the journal lane has none
                conn,
                conn_info,
                request_id,
                recording=recorder.recording,
                savepoint=parent_ids is not None,
                facts=facts,
            )
            if journal is None and not recorder.recording:
                continue  # paused, and nothing for the journal: BootUI records nothing (-1)
            parent = parents.get(id(recorder))
            # the walk starts at the listener's caller (tx_begin's or tx_savepoint's): the frames below are sharpit's
            method = (
                call_site(sys._getframe(2))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                if ctx.settings.sql_trace_capture_call_site
                else "unknown"
            )
            entry_id = recorder.begin(
                id(conn),
                parent=parent,
                method=method or "unknown",
                thread=threading.current_thread().name,
                trace_id=request_id,
                connection_id=connection_id,
                journal=journal,
            )
            if entry_id >= 0:
                stack.append((weakref.ref(recorder), entry_id))
        except Exception as exc:  # noqa: BLE001 - never alter the application's transaction
            dispatch._context_failed(ctx, exc)  # pyright: ignore[reportPrivateUsage]


def _end(info: dict[str, Any], status: str, *, settle: bool = False) -> None:
    stack = _stack(info)
    closing, stack[:] = stack[:], []
    _savepoints(info).clear()
    _close(closing, status, settle=settle, writes=info.get(WRITES, 0))


def _end_savepoint(conn: Any, name: str, status: str) -> None:
    info = conn.info
    stack = _stack(info)
    savepoints = _savepoints(info)
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
    _close(closing, status, writes=info.get(WRITES, 0))


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
        _end(info, "COMMITTED", settle=True)
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


# a SELECT and the savepoint statements undo nothing on rollback (BootUI has no write count: sharpit's own rule)
_NO_WRITE = ("select", "savepoint", "release savepoint", "rollback to savepoint")


def tx_statement(conn: Any, _cursor: Any, statement: str, *_: object) -> None:
    """Count a statement that is not a SELECT (``WRITES``). Leading comments, ``WITH`` and anything else count as a
    write: a rollback is then reported, never hidden."""
    try:
        if not statement.lstrip()[:21].lower().startswith(_NO_WRITE):
            info = conn.info
            info[WRITES] = info.get(WRITES, 0) + 1
    except Exception as exc:  # noqa: BLE001 - never affect the application's statement
        dispatch.routing_failed(exc)


CONNECTION_CALLBACKS: dict[str, Callable[..., None]] = {
    "begin": tx_begin,
    "commit": tx_commit,
    "rollback": tx_rollback,
    "savepoint": tx_savepoint,
    "rollback_savepoint": tx_rollback_savepoint,
    "release_savepoint": tx_release_savepoint,
    "handle_error": tx_handle_error,
    "before_cursor_execute": tx_statement,
}
_attach_lock = threading.Lock()
_attach_count = 0
_attach_removers: list[Callable[[], None]] = []
SOURCE = "transactions"  # the capture registry entry's name, and its mark in ``CaptureState.suspended_sources``
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
