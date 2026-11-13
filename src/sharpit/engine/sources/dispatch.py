"""The one SQL event path (spec 0.3.0 §8.1): sources emit, console contexts and the test-session sink receive."""

from __future__ import annotations

import logging
import threading
import time
import weakref
from collections.abc import Sized
from typing import TYPE_CHECKING, NamedTuple, Protocol

from sharpit.engine import otel
from sharpit.engine.capture.correlation import INTERNAL, REQUEST, TEST, RequestInfo
from sharpit.engine.capture.journal import SCALAR_BYTES, RecordFields, value_bytes
from sharpit.engine.capture.sqltrace import call_site
from sharpit.engine.context import application_family
from sharpit.engine.sqla.dialect_source import event_dialect
from sharpit.engine.sqltext import Dialect

if TYPE_CHECKING:
    from sharpit.engine.capture.sqltrace import SqlTraceRecorder
    from sharpit.engine.context import SharpitContext


class SqlEvent(NamedTuple):
    # a NamedTuple, not a dataclass: it is built once per statement (~0.06 µs against ~2.3 µs)
    source: str  # "sqlalchemy" | "sqlite3"
    sql: str  # placeholder SQL, never expanded
    parameters: object  # passed to the recorder for masking; the session sink drops it
    executemany: bool
    batch_size: int | None
    started_ns: int
    duration_ns: int
    rowcount: int
    error: BaseException | None
    connection_id: str | None
    engine: object | None  # SQLAlchemy only, for the "held by" routing rule
    dialect: Dialect  # what the source knows it talks to: ``normalize`` reads ``#``, ``"..."`` and ``0x`` by it


logger = logging.getLogger("sharpit")

type TestTag = tuple[str, int, str]


class SessionSink(Protocol):
    def on_sql(self, event: SqlEvent, test: TestTag | None) -> None: ...
    def on_exception(self, exc: BaseException, source: str, test: TestTag | None) -> None: ...
    def on_escaped(self, exc: BaseException) -> None: ...
    def register_app(self, app: object) -> None: ...


_lock = threading.Lock()
_contexts: weakref.WeakValueDictionary[str, SharpitContext] = weakref.WeakValueDictionary()
# what emit reads per statement: a plain tuple, refreshed on every change (iterating the dict is slow)
_refs: tuple[weakref.ref[SharpitContext], ...] = ()
_sink: SessionSink | None = None
_drivers: set[str] = set()
_warned = False


def routing_failed(exc: BaseException) -> None:
    global _warned  # noqa: PLW0603 - one warning per process for a failure before any context is known
    if not _warned:
        _warned = True
        logger.warning("sharpit SQL listener failed (%s); queries are unaffected", type(exc).__name__)


def _context_failed(ctx: SharpitContext, exc: BaseException, hook: str = "sql statement") -> None:
    wiring = ctx.capture.wiring
    if wiring is not None:
        wiring.hook_failed(hook, exc)
    else:
        routing_failed(exc)


def _targets(engine: object | None) -> list[SharpitContext]:
    """In a request: its own context only. Outside: the contexts holding the engine, else the only context."""
    contexts = [c for r in _refs if (c := r()) is not None]
    info = REQUEST.get()
    if info is not None:
        return [c for c in contexts if c.context_id == info.context_id]
    held = (
        [c for c in contexts if c.capture.engine_registry is not None and c.capture.engine_registry.holds(engine)]
        if engine is not None
        else []
    )
    return held or (contexts if len(contexts) == 1 else [])


def recording(engine: object | None, source: str = "sqlalchemy") -> list[SharpitContext]:
    """The contexts a statement from ``source`` is recorded by: routed, recording, and (sqlite3) switched on."""
    if source == "sqlite3":
        info = REQUEST.get()
        for ref in _refs:
            ctx = ref()
            if (
                ctx is not None
                and ctx.settings.sql_trace_sqlite3_enabled
                and (info is None or ctx.context_id == info.context_id)
            ):
                ctx.capture.raw_sqlite_seen = True
    targets = [
        c
        for c in _targets(engine)
        if c.capture.sql_trace is not None
        # a paused panel still feeds the journal when it records sql (BootUI SqlTraceRecorder.java:730-731)
        and (c.capture.sql_trace.recording or (c.capture.journal is not None and c.capture.journal.accepts("sql")))
        and (source != "sqlite3" or c.settings.sql_trace_sqlite3_enabled)
        and source not in c.capture.suspended_sources
    ]
    return targets


_SQL_FIELDS = RecordFields(
    "sql", "sql", "traceId", "requestId", "thread", "durationNanos", "startedAt", "dataSource", "failed", "phase",
    "completedNanos", "codePathStamp", "provenance", "batchSize", "callSite",
)  # fmt: skip
# what the journal charges of a record before its variable texts, derived from the layout: its key bytes, the value of
# each field that never varies, and ``SCALAR_BYTES`` for each number or flag; the texts are charged per statement
_SQL_CONSTANTS = {"source": "sql", "dataSource": None, "phase": None, "codePathStamp": 0, "provenance": "EXECUTION"}
_SQL_TEXTS = ("sql", "traceId", "requestId", "thread", "callSite")  # a text, or None: ``value_bytes`` per statement
_SQL_CONSTANT_BYTES = _SQL_FIELDS.key_bytes + sum(
    value_bytes(_SQL_CONSTANTS[key]) if key in _SQL_CONSTANTS else 0 if key in _SQL_TEXTS else SCALAR_BYTES
    for key in _SQL_FIELDS.keys
)


def _batch(event: SqlEvent) -> int:
    """``SqlPayload.batchSize``: 1 for an ordinary execution, N for a batch, 0 for a batch of unknown size (a one-shot
    generator), never read as unbatched (BootUI ``SqlTraceRecorder.recordNanos``)."""
    if not event.executemany:
        return 1
    if event.batch_size is not None:
        return max(event.batch_size, 1)
    return max(len(event.parameters), 1) if isinstance(event.parameters, Sized) else 0


def _journal_event(
    ctx: SharpitContext,
    recorder: SqlTraceRecorder,
    event: SqlEvent,
    text: str,
    info: RequestInfo | None,
    thread: str,
    site: str | None,
) -> tuple[tuple[str | int | bool | None, ...], int]:
    """BootUI's ``sql`` journal event (``SqlPayload`` and its envelope) and its charged size, computed here per
    statement instead of by walking the event: the literal-free text, never a parameter.

    ``phase`` is None: BootUI's ``RequestPhase`` (FILTERS/HANDLER/RESPONSE) has no sharpit source, and outside a request
    it is null, so the lifespan's STARTUP/SHUTDOWN is not carried."""
    trace_id = otel.current_trace_id()
    request_id = info.id if info is not None and info.context_id == ctx.context_id else None
    site = site if recorder.capture_call_site else None
    record = (
        "sql",
        text,
        trace_id,
        request_id,
        thread,
        event.duration_ns,
        time.time_ns() // 1_000_000 - event.duration_ns // 1_000_000,
        None,
        event.error is not None,
        None,
        # the statement's end on the perf_counter clock, before any recording work (SqlTraceRecorder.java:738)
        event.started_ns + event.duration_ns,
        0,
        "EXECUTION",
        _batch(event),
        site,
    )
    return record, (
        _SQL_CONSTANT_BYTES
        + len(text)
        + len(thread)
        + value_bytes(trace_id)
        + value_bytes(request_id)
        + value_bytes(site)
    )


def _trace_text(
    ctx: SharpitContext, recorder: SqlTraceRecorder, event: SqlEvent, info: RequestInfo | None, thread: str,
    site: str | None,
) -> str | None:  # fmt: skip
    """The statement's literal-free text: recorded as a trace row, or only shaped for the journal while paused."""
    dialect = event_dialect(event, lambda ctx=ctx: application_family(ctx))
    if not recorder.recording:
        return recorder.journal_text(event.sql, dialect)
    return recorder.record(
        event.sql,
        duration_ns=event.duration_ns,
        thread=thread,
        connection_id=event.connection_id,
        parameters=event.parameters,
        executemany=event.executemany,
        success=event.error is None,
        error=event.error,
        rowcount=event.rowcount,
        request_id=info.id if info is not None else None,
        call_site=site,
        batch_size=event.batch_size,
        dialect=dialect,
    )


def _record(event: SqlEvent, targets: list[SharpitContext]) -> None:
    info = REQUEST.get()
    site = (
        call_site(None) if any(c.capture.sql_trace and c.capture.sql_trace.capture_call_site for c in targets) else None
    )
    thread = threading.current_thread().name
    for ctx in targets:
        recorder = ctx.capture.sql_trace
        if recorder is None:
            continue
        try:
            text = _trace_text(ctx, recorder, event, info, thread, site)
        except Exception as exc:  # noqa: BLE001
            _context_failed(ctx, exc)
            continue
        journal = ctx.capture.journal
        if journal is not None and text is not None:
            try:  # its own guard: a journal failure is never reported as the SQL hook's
                journal.offer_record(_SQL_FIELDS, *_journal_event(ctx, recorder, event, text, info, thread, site))
            except Exception as exc:  # noqa: BLE001
                _context_failed(ctx, exc, "sql journal")


def emit(event: SqlEvent) -> None:
    """Route one statement (a source that does not precompute its targets) and deliver it. Never raises."""
    try:
        if INTERNAL.get():
            return
        deliver(event, recording(event.engine, event.source))
    except Exception as exc:  # noqa: BLE001 - a source never changes the host's query
        routing_failed(exc)


def deliver(event: SqlEvent, targets: list[SharpitContext]) -> None:
    """Send one statement to ``targets``, then to the session sink. Never raises; the caller did the routing."""
    try:
        if targets:
            _record(event, targets)
        sink = _sink
        if sink is not None:
            driver = getattr(getattr(event.engine, "dialect", None), "driver", None)
            if isinstance(driver, str):
                _drivers.add(driver)
            sink.on_sql(event, TEST.get())
    except Exception as exc:  # noqa: BLE001 - a source never changes the host's query
        routing_failed(exc)


def set_session_sink(sink: SessionSink | None) -> None:
    # one sink per process, read lock-free by emit
    global _sink  # noqa: PLW0603
    _sink = sink
    if sink is None:
        _drivers.clear()


def session_sink() -> SessionSink | None:
    return _sink


def _refresh() -> None:
    # swapped whole under the lock, read lock-free
    global _refs  # noqa: PLW0603
    _refs = tuple(weakref.ref(c) for c in _contexts.values())


def add_context(ctx: SharpitContext) -> None:
    with _lock:
        _contexts[ctx.context_id] = ctx
        _refresh()


def remove_context(ctx: SharpitContext) -> None:
    with _lock:
        _contexts.pop(ctx.context_id, None)
        _refresh()


def clear_contexts() -> None:
    with _lock:
        _contexts.clear()
        _refresh()


def engine_drivers() -> set[str]:
    """``engine.dialect.driver`` of every engine an event came from while the sink was set."""
    return set(_drivers)
