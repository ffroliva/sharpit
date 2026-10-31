"""The SQLAlchemy bridge (spec §6.1 steps 4a/4b, §6.2): engine registry, class-level listeners, statement routing.

sharpit never imports SQLAlchemy: it reads ``sys.modules``, so an app that does not use it pays nothing, and the
listeners attach at install, at startup or on the first request, whichever first finds it imported. Listeners are
class-level on ``Engine`` (they see engines created before and after install) and shared by every installed
context; ``StatementRouter`` sends each statement to the contexts it belongs to.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from sharpit.engine.capture.correlation import INTERNAL, REQUEST, internal
from sharpit.engine.capture.sqltrace import call_site
from sharpit.engine.masking import Masker

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

logger = logging.getLogger("sharpit")

STATEMENT_EVENTS = ("before_cursor_execute", "after_cursor_execute", "handle_error")
DISCOVERY_EVENT = "engine_connect"
DISCOVERY_PANELS = ("alembic", "database-connection-pools", "health")  # panels that read the registered engines
START_KEY = "sharpit_sql_start"
UNAVAILABLE = "SQLAlchemy 2.0 or later is not imported by the application"
TRACING_DISABLED = "SQL tracing is disabled via SHARPIT_SQL_TRACE_ENABLED=false"


def sqlalchemy() -> Any | None:
    """The imported ``sqlalchemy`` module when it is 2.0 or later, else ``None``; never imports it."""
    module = sys.modules.get("sqlalchemy")
    version = str(getattr(module, "__version__", "0"))
    try:
        major = int(version.split(".", 1)[0])
    except ValueError:
        return None
    return module if module is not None and major >= 2 else None


def _engine_class() -> type | None:
    sa = sqlalchemy()
    return sa.engine.Engine if sa is not None else None


class EngineRegistry:
    """The engines one context knows about, held weakly, each with a display name that never carries credentials."""

    def __init__(self, masker: Masker) -> None:
        self._masker = masker
        self._names: weakref.WeakKeyDictionary[Any, str] = weakref.WeakKeyDictionary()
        self._lock = threading.Lock()

    def add(self, engine: object) -> None:
        """Register a sync ``Engine`` or an ``AsyncEngine`` (its ``sync_engine``); anything else is ignored."""
        engine_class = _engine_class()
        sync: Any = getattr(engine, "sync_engine", engine)
        if engine_class is None or not isinstance(sync, engine_class):
            return
        with self._lock:
            if sync in self._names:
                return
            url = sync.url
            host = f"{url.host}:{url.port}" if url.host and url.port else url.host or ""
            name = f"{url.get_backend_name()}+{sync.dialect.driver}://{host}/{url.database or ''}"
            name = self._masker.mask_text(name) or name
            taken = set(self._names.values())
            unique, n = name, 1
            while unique in taken:
                n += 1
                unique = f"{name}#{n}"
            self._names[sync] = unique

    def holds(self, engine: object) -> bool:
        with self._lock:
            return engine in self._names

    def engines(self) -> list[tuple[str, Any]]:
        """``(display name, Engine)`` in registration order."""
        with self._lock:
            return [(name, engine) for engine, name in self._names.items()]

    def names(self) -> list[str]:
        return [name for name, _ in self.engines()]


# --- routing --------------------------------------------------------------------------------------------------------

_lock = threading.Lock()
_statement_contexts: weakref.WeakValueDictionary[str, SharpitContext] = weakref.WeakValueDictionary()
_discovery_contexts: weakref.WeakValueDictionary[str, SharpitContext] = weakref.WeakValueDictionary()
# what the listeners read per statement: a plain tuple, refreshed on every change (iterating the dicts is slow)
_statement_refs: tuple[weakref.ref[SharpitContext], ...] = ()
_discovery_refs: tuple[weakref.ref[SharpitContext], ...] = ()
_warned = False


def _routing_failed(exc: BaseException) -> None:
    global _warned  # noqa: PLW0603 - one warning per process for a failure before any context is known
    if not _warned:
        _warned = True
        logger.warning("sharpit SQL listener failed (%s); queries are unaffected", type(exc).__name__)


def _context_failed(ctx: SharpitContext, exc: BaseException) -> None:
    wiring = ctx.capture.wiring
    if wiring is not None:
        wiring.hook_failed("sql statement", exc)
    else:
        _routing_failed(exc)


def _statement_targets(conn: Any) -> list[SharpitContext]:
    """In a request: its own context only. Outside: the contexts holding the engine, else the only context."""
    contexts = [c for r in _statement_refs if (c := r()) is not None]
    info = REQUEST.get()
    if info is not None:
        return [c for c in contexts if c.context_id == info.context_id]
    engine = conn.engine
    held = [c for c in contexts if c.capture.engine_registry is not None and c.capture.engine_registry.holds(engine)]
    return held or (contexts if len(contexts) == 1 else [])


def engine_connect(conn: Any) -> None:
    """Step 4a: record the engine in the registry of the context it belongs to."""
    try:
        if INTERNAL.get():
            return
        contexts = [c for r in _discovery_refs if (c := r()) is not None]
        info = REQUEST.get()
        if info is not None:
            contexts = [c for c in contexts if c.context_id == info.context_id]
        elif len(contexts) != 1:
            return
        for ctx in contexts:
            if ctx.capture.engine_registry is not None:
                ctx.capture.engine_registry.add(conn.engine)
    except Exception as exc:  # noqa: BLE001 - a listener never changes the host's query
        _routing_failed(exc)


def before_cursor_execute(
    conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
) -> None:
    del cursor, statement, parameters, executemany
    try:
        if INTERNAL.get():
            return
        targets = [
            c for c in _statement_targets(conn) if c.capture.sql_trace is not None and c.capture.sql_trace.recording
        ]
        if not targets:
            return
        start = (time.perf_counter_ns(), targets)
        if context is not None:
            context._sharpit_start = start  # noqa: SLF001
        else:
            conn.info[START_KEY] = start
    except Exception as exc:  # noqa: BLE001
        _routing_failed(exc)


def _pop_start(conn: Any, context: Any) -> tuple[int, list[SharpitContext]] | None:
    state = cast("dict[str, Any]", vars(context)) if context is not None else None
    if state is not None and "_sharpit_start" in state:
        return state.pop("_sharpit_start")
    return conn.info.pop(START_KEY, None)


def _named(parameters: Any, context: Any, executemany: bool) -> Any:
    """Positional DBAPI parameters keyed by their bind names again, so the masker sees ``password`` and not ``0``."""
    names = getattr(getattr(context, "compiled", None), "positiontup", None)
    if not names or not parameters or isinstance(parameters, dict):
        return cast(Any, parameters)

    def key(values: Any) -> Any:
        rows, rest = divmod(len(values), len(names))
        if rows == 0 or rest:
            return values
        # insertmanyvalues batches rows into one statement: each row repeats the names, suffixed after the first
        keys = [name if row == 0 else f"{name}#{row + 1}" for row in range(rows) for name in names]
        return dict[Any, Any](zip(keys, values, strict=True))

    # insertmanyvalues reports executemany with one flat batch of values, not one sequence per row
    many = executemany and isinstance(parameters[0], list | tuple | dict)
    return [key(v) for v in parameters] if many else key(parameters)


def _record(
    start: tuple[int, list[SharpitContext]],
    conn: Any,
    statement: str,
    parameters: Any,
    executemany: bool,
    rowcount: int,
    error: BaseException | None,
) -> None:
    started, targets = start
    duration = time.perf_counter_ns() - started
    info = REQUEST.get()
    site = (
        call_site(None) if any(c.capture.sql_trace and c.capture.sql_trace.capture_call_site for c in targets) else None
    )
    try:
        connection_id: str | None = hex(id(conn.connection.dbapi_connection))
    except Exception:  # noqa: BLE001 - an invalidated connection has no DBAPI connection
        connection_id = None
    thread = threading.current_thread().name
    for ctx in targets:
        recorder = ctx.capture.sql_trace
        if recorder is None:
            continue
        try:
            recorder.record(
                statement,
                duration_ns=duration,
                thread=thread,
                connection_id=connection_id,
                parameters=parameters,
                executemany=executemany,
                success=error is None,
                error=error,
                rowcount=rowcount,
                request_id=info.id if info is not None else None,
                call_site=site,
            )
        except Exception as exc:  # noqa: BLE001
            _context_failed(ctx, exc)


def after_cursor_execute(
    conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
) -> None:
    try:
        start = _pop_start(conn, context)
        if start is not None:
            parameters = _named(parameters, context, executemany)
            _record(start, conn, statement, parameters, executemany, getattr(cursor, "rowcount", -1), None)
    except Exception as exc:  # noqa: BLE001
        _routing_failed(exc)


def handle_error(exception_context: Any) -> None:
    try:
        context = exception_context.execution_context
        conn = exception_context.connection
        start = _pop_start(conn, context) if conn is not None else None
        if start is not None:
            error = exception_context.sqlalchemy_exception or exception_context.original_exception
            executemany = bool(getattr(context, "executemany", False))
            parameters = _named(exception_context.parameters, context, executemany)
            _record(start, conn, exception_context.statement or "", parameters, executemany, -1, error)
    except Exception as exc:  # noqa: BLE001
        _routing_failed(exc)


_LISTENERS: dict[str, Callable[..., None]] = {
    DISCOVERY_EVENT: engine_connect,
    "before_cursor_execute": before_cursor_execute,
    "after_cursor_execute": after_cursor_execute,
    "handle_error": handle_error,
}


def _sync_listeners() -> None:
    """Listen while a context needs the event, remove once none does (callers hold ``_lock``)."""
    global _statement_refs, _discovery_refs  # noqa: PLW0603 - swapped whole under the lock, read lock-free
    _statement_refs = tuple(weakref.ref(c) for c in _statement_contexts.values())
    _discovery_refs = tuple(weakref.ref(c) for c in _discovery_contexts.values())
    sa = sqlalchemy()
    if sa is None:
        return
    wanted = {DISCOVERY_EVENT: bool(_discovery_contexts), **dict.fromkeys(STATEMENT_EVENTS, bool(_statement_contexts))}
    for name, fn in _LISTENERS.items():
        present = sa.event.contains(sa.engine.Engine, name, fn)
        if wanted[name] and not present:
            sa.event.listen(sa.engine.Engine, name, fn)
        elif present and not wanted[name]:
            sa.event.remove(sa.engine.Engine, name, fn)


def add(ctx: SharpitContext, *, statements: bool, discovery: bool) -> bool:
    """Route statements and/or engine discovery to ``ctx``; False while SQLAlchemy is not imported (retry later)."""
    if sqlalchemy() is None:
        return False
    registry = ctx.capture.engine_registry
    if registry is not None:
        for engine in ctx.engines:
            registry.add(engine)
    with _lock:
        if statements:
            _statement_contexts[ctx.context_id] = ctx
        if discovery:
            _discovery_contexts[ctx.context_id] = ctx
        _sync_listeners()
    return True


def remove(ctx: SharpitContext) -> None:
    with _lock:
        _statement_contexts.pop(ctx.context_id, None)
        _discovery_contexts.pop(ctx.context_id, None)
        _sync_listeners()


def detach_all() -> None:
    """Forget every context and remove every listener (tests start from a clean slate with it)."""
    with _lock:
        _statement_contexts.clear()
        _discovery_contexts.clear()
        _sync_listeners()


def routed(ctx: SharpitContext) -> tuple[bool, bool]:
    """``(statements, discovery)``: whether ``ctx`` receives traced statements and discovered engines."""
    with _lock:
        return ctx.context_id in _statement_contexts, ctx.context_id in _discovery_contexts


def attached() -> dict[str, bool]:
    """Event name -> whether sharpit's class-level listener is on ``Engine``."""
    sa = sqlalchemy()
    if sa is None:
        return dict.fromkeys(_LISTENERS, False)
    return {name: bool(sa.event.contains(sa.engine.Engine, name, fn)) for name, fn in _LISTENERS.items()}


async def run_db_read[T](engine: Any, fn: Callable[[Any], T], timeout: float) -> T:
    """Run ``fn(connection)`` for sharpit's own read, off the event loop and invisible to SQL Trace.

    An async dialect runs through ``AsyncEngine.run_sync`` (the driver needs the loop); a sync one in a thread.
    """
    with internal():  # the thread and the greenlet copy this context, so the listeners see the marker
        async with asyncio.timeout(timeout):
            if engine.dialect.is_async:
                from sqlalchemy.ext.asyncio import AsyncEngine  # noqa: PLC0415 - only once the app imported it

                async with AsyncEngine(engine).connect() as conn:
                    return await conn.run_sync(fn)

            def read() -> T:
                with engine.connect() as conn:
                    return fn(conn)

            return await asyncio.to_thread(read)
