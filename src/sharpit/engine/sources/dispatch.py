"""The one SQL event path (spec 0.3.0 §8.1): sources emit, console contexts and the test-session sink receive."""

from __future__ import annotations

import logging
import threading
import weakref
from typing import TYPE_CHECKING, NamedTuple, Protocol

from sharpit.engine.capture.correlation import INTERNAL, REQUEST, TEST
from sharpit.engine.capture.sqltrace import call_site

if TYPE_CHECKING:
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


def _context_failed(ctx: SharpitContext, exc: BaseException) -> None:
    wiring = ctx.capture.wiring
    if wiring is not None:
        wiring.hook_failed("sql statement", exc)
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
    return [
        c
        for c in _targets(engine)
        if c.capture.sql_trace is not None
        and c.capture.sql_trace.recording
        and (source != "sqlite3" or c.settings.sql_trace_sqlite3_enabled)
    ]


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
            recorder.record(
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
            )
        except Exception as exc:  # noqa: BLE001
            _context_failed(ctx, exc)


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
    global _sink  # noqa: PLW0603 - one sink per process, read lock-free by emit
    _sink = sink
    if sink is None:
        _drivers.clear()


def session_sink() -> SessionSink | None:
    return _sink


def _refresh() -> None:
    global _refs  # noqa: PLW0603 - swapped whole under the lock, read lock-free
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
