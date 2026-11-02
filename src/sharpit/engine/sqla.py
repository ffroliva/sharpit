"""The SQLAlchemy bridge (spec §6.1 steps 4a/4b, §6.2): engine registry, class-level listeners, statement routing.

sharpit never imports SQLAlchemy: it reads ``sys.modules``, so an app that does not use it pays nothing, and the
listeners attach at install, at startup or on the first request, whichever first finds it imported. Listeners are
class-level on ``Engine`` (they see engines created before and after install) and shared by every installed
context and the test session; ``sources.dispatch`` sends each statement to the contexts it belongs to.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import functools
import gc
import inspect
import logging
import sys
import threading
import time
import weakref
from collections.abc import Callable
from concurrent.futures import Executor
from types import CodeType
from typing import TYPE_CHECKING, Any, Literal, cast

from sharpit.engine.capture.correlation import INTERNAL, REQUEST, TEST, internal
from sharpit.engine.capture.frames import is_application_frame
from sharpit.engine.masking import Masker
from sharpit.engine.sources import dispatch, sqlite
from sharpit.engine.sources.dispatch import SqlEvent

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

logger = logging.getLogger("sharpit")

STATEMENT_EVENTS = ("before_cursor_execute", "after_cursor_execute", "handle_error")
DISCOVERY_EVENT = "engine_connect"
ConnectionEvent = Literal["begin", "commit", "rollback", "savepoint", "rollback_savepoint", "release_savepoint"]
CONNECTION_EVENTS: tuple[ConnectionEvent, ...] = (
    "begin",
    "commit",
    "rollback",
    "savepoint",
    "rollback_savepoint",
    "release_savepoint",
)  # add_connection_listener's events (O1)
DISCOVERY_PANELS = (
    "alembic",
    "database-connection-pools",
    "health",
    "postgresql",
    "mysql",
    "database-advisor",
    "sqlalchemy-statistics",
)  # panels that read the registered engines
START_KEY = "sharpit_sql_start"
RELATIONSHIP_KEY = "sharpit_relationship"
_EAGER_RELATIONSHIP_KEY = "sharpit_eager_relationship"
UNAVAILABLE = "SQLAlchemy is not imported by this application"
TRACING_DISABLED = "SQL tracing is disabled via SHARPIT_SQL_TRACE_ENABLED=false"
# Kept as an empty compatibility bucket for existing test cleanup; relationship totals come from SQL facts.
_relationship_loads: dict[tuple[str, int, str], dict[str, int]] = {}
_relationship_groups: dict[tuple[str, int, str], dict[str, tuple[str, bool]]] = {}
_relationship_sites: dict[tuple[str, int, str], dict[str, str | None]] = {}
_eager_relationship_batches: dict[tuple[str, int, str], dict[str, int]] = {}
# lazy loads already recorded per test: (compiled, parent class, statement) decides the whole outcome, so a repeat
# (the N in N+1) skips the path read and the fingerprint; the lazy-load overhead budget depends on it
_lazy_seen: dict[tuple[str, int, str], set[tuple[Any, Any, str]]] = {}


@functools.lru_cache(maxsize=4096)
def _is_application_code(code: CodeType) -> bool:
    return is_application_frame(code.co_filename)


def _first_application_location() -> str | None:
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame is not None else None
        while frame is not None:
            if _is_application_code(frame.f_code):
                return f"{frame.f_code.co_filename}:{frame.f_lineno}"
            frame = frame.f_back
        return None
    finally:
        del frame


@functools.lru_cache(maxsize=1)
def _relationship_masker() -> Masker:
    from sharpit.engine.testsession.sink import report_masker

    return report_masker()


@functools.lru_cache(maxsize=1024)
def _masked_fingerprint(statement: str) -> str:
    from sharpit.engine.capture.sqltrace import normalize

    return _relationship_masker().mask_text(normalize(statement).fingerprint) or ""


def _relationship_path(context: Any) -> tuple[Any, str, str, int] | None:
    compiled = getattr(context, "compiled", None)
    compile_state = getattr(compiled, "compile_state", None)
    current_path = getattr(compile_state, "current_path", None)
    path = getattr(current_path, "path", ())
    if not path:
        return None
    prop = path[-1]
    key = getattr(prop, "key", None)
    direction = getattr(getattr(prop, "direction", None), "name", "")
    if not isinstance(key, str) or not direction:
        return None
    return prop, key, direction, len(path)


def _relationship_observation(context: Any, tag: tuple[str, int, str]) -> Any:
    options = getattr(context, "execution_options", {})
    relation_value = options.get(RELATIONSHIP_KEY) if options is not None else None
    if relation_value is not None:
        return relation_value
    load_options = options.get("_sa_orm_load_options") if options is not None else None
    parent = getattr(load_options, "_lazy_loaded_from", None)
    path_info = _relationship_path(context)
    if path_info is None:
        return None
    prop, key, direction, path_length = path_info
    if parent is None:
        if path_length < 2:
            return None
        parent_mapper = getattr(prop, "parent", None)
        model_name = getattr(getattr(parent_mapper, "class_", None), "__name__", None)
        return _EAGER_RELATIONSHIP_KEY if isinstance(model_name, str) else None
    model_name = getattr(getattr(parent, "class_", None), "__name__", None)
    if not isinstance(model_name, str):
        return None
    identity = f"{model_name}.{key}"
    sites = _relationship_sites.get(tag)
    if sites is None or identity not in sites:
        with _lock:
            sites = _relationship_sites.setdefault(tag, {})
            if identity not in sites:
                sites[identity] = _first_application_location()
    collection = direction in {"ONETOMANY", "MANYTOMANY"}
    return identity, collection


def _lazy_key(context: Any, statement: str) -> tuple[Any, Any, str] | None:
    """What a lazy load's observation depends on, or None for anything else (counted per execution, or not cached)."""
    options = getattr(context, "execution_options", None)
    if not options or RELATIONSHIP_KEY in options:
        return None
    parent = getattr(options.get("_sa_orm_load_options"), "_lazy_loaded_from", None)
    compiled = getattr(context, "compiled", None)
    if parent is None or compiled is None:
        return None
    return compiled, getattr(parent, "class_", None), statement


def _record_relationship(context: Any) -> None:
    """Record relationship loads using SQLAlchemy's compiled execution context, without an ORM hook."""
    tag = TEST.get()
    if tag is None or tag[2] != "call":
        return
    statement = getattr(context, "statement", None)
    if not isinstance(statement, str):
        return
    seen_key = _lazy_key(context, statement)
    if seen_key is not None:
        seen = _lazy_seen.get(tag)
        if seen is not None and seen_key in seen:
            return
    relation_value = _relationship_observation(context, tag)
    if seen_key is not None:
        with _lock:
            _lazy_seen.setdefault(tag, set()).add(seen_key)
    if isinstance(relation_value, tuple) and len(cast("tuple[object, ...]", relation_value)) == 2:
        _store_lazy_group(tag, statement, cast("tuple[object, object]", relation_value))
    elif relation_value is _EAGER_RELATIONSHIP_KEY:
        _count_eager_batch(tag, statement)


def _store_lazy_group(tag: tuple[str, int, str], statement: str, relation: tuple[object, object]) -> None:
    """Remember which relationship a lazy-load statement belongs to (first observation wins)."""
    identity, collection = relation
    if not isinstance(identity, str) or not isinstance(collection, bool):
        return
    key = _masked_fingerprint(statement)
    groups = _relationship_groups.get(tag)
    if groups is None or key not in groups:
        with _lock:
            _relationship_groups.setdefault(tag, {}).setdefault(key, (identity, collection))


def _count_eager_batch(tag: tuple[str, int, str], statement: str) -> None:
    """Count one eager-load batch statement, so it is not mistaken for an N+1 repeat."""
    key = _masked_fingerprint(statement)
    with _lock:
        batches = _eager_relationship_batches.setdefault(tag, {})
        batches[key] = batches.get(key, 0) + 1


def apply_relationship_facts(test: Any) -> None:
    """Move one test attempt's relationship observations into its serializable phase facts."""
    tag = (test.key.node_id, test.key.attempt, "call")
    with _lock:
        groups = _relationship_groups.pop(tag, {})
        sites = _relationship_sites.pop(tag, {})
        eager_batches = _eager_relationship_batches.pop(tag, {})
        _lazy_seen.pop(tag, None)
    if not groups and not eager_batches:
        return
    phase = test.phases.get("call")
    if phase is None:
        return
    for group, count in eager_batches.items():
        remaining = phase.selects.get(group, 0) - count
        if remaining > 0:
            phase.selects[group] = remaining
        else:
            phase.selects.pop(group, None)
            phase.sql_of.pop(group, None)
    phase.relationship_of.update(groups)
    phase.relationship_sites.update(sites)
    for group, (identity, _collection) in groups.items():
        count = phase.selects.get(group, 0)
        if count:
            phase.relationship_loads[identity] = phase.relationship_loads.get(identity, 0) + count


def sqlalchemy_module() -> Any | None:
    """The imported ``sqlalchemy`` module when it is 2.0 or later, else ``None``; never imports it."""
    module = sys.modules.get("sqlalchemy")
    version = str(getattr(module, "__version__", "0"))
    try:
        major = int(version.split(".", 1)[0])
    except ValueError:
        return None
    return module if module is not None and major >= 2 else None


def unavailable_reason() -> str | None:
    """Why the SQLAlchemy-backed panels are empty: not imported, or imported but older than 2.0."""
    module = sys.modules.get("sqlalchemy")
    if module is None:
        return UNAVAILABLE
    if sqlalchemy_module() is None:
        return f"SQLAlchemy {getattr(module, '__version__', '?')} is imported, but sharpit needs 2.0 or later"
    return None


def sqlite3_traced(ctx: SharpitContext) -> bool:
    """The raw sqlite3 source feeds this context: its own switch is on and the patch is in (any holder's)."""
    return ctx.settings.sql_trace_sqlite3_enabled and sqlite.is_attached()


def sql_trace_unavailable_reason(ctx: SharpitContext) -> str | None:
    """Why SQL Trace shows nothing: tracing switched off, or SQLAlchemy 2.0+ not imported by the app."""
    if not ctx.settings.sql_trace_enabled:
        return TRACING_DISABLED
    return None if sqlite3_traced(ctx) else unavailable_reason()


def _engine_class() -> type | None:
    sa = sqlalchemy_module()
    return sa.engine.Engine if sa is not None else None


def live_engine_drivers() -> set[str]:
    """Drivers of live SQLAlchemy Engine objects; inspect once without importing SQLAlchemy."""
    sa = sqlalchemy_module()
    if sa is None:
        return set()
    engine_class = sa.engine.Engine
    drivers: set[str] = set()
    try:
        for obj in gc.get_objects():
            if type(obj) is engine_class:
                drivers.add(obj.dialect.driver)
    except Exception:  # noqa: BLE001 - best-effort evidence must not affect the host
        return drivers
    return drivers


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


# --- discovery and listener syncing --------------------------------------------------------------------------------

_lock = threading.Lock()
_discovery_contexts: weakref.WeakValueDictionary[str, SharpitContext] = weakref.WeakValueDictionary()
# what the listener reads per event: a plain tuple, refreshed on every change (iterating the dict is slow)
_discovery_refs: tuple[weakref.ref[SharpitContext], ...] = ()
# contexts that asked for statements through ``add`` (``routed`` reads it); weak, so a collected one stops counting
_statement_contexts: weakref.WeakValueDictionary[str, SharpitContext] = weakref.WeakValueDictionary()
_session = False  # the test-session sink wants statements too (spec 0.3.0 §8.1)


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
        dispatch.routing_failed(exc)


def before_cursor_execute(
    conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
) -> None:
    del cursor, statement, parameters, executemany
    try:
        if INTERNAL.get():
            return
        _record_relationship(context)
        targets = dispatch.recording(conn.engine)  # routed once here; the after hook delivers to the same targets
        if not targets and dispatch.session_sink() is None:
            return
        start = (time.perf_counter_ns(), targets)
        if context is not None:
            context._sharpit_start = start  # noqa: SLF001
        else:
            conn.info[START_KEY] = start
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def _pop_start(conn: Any, context: Any) -> tuple[int, list[SharpitContext]] | None:
    state = cast("dict[str, Any]", vars(context)) if context is not None else None
    if state is not None and "_sharpit_start" in state:
        return state.pop("_sharpit_start")
    return conn.info.pop(START_KEY, None)


def _named(parameters: Any, context: Any, executemany: bool) -> tuple[Any, int | None]:
    """The parameters keyed by bind name, so the masker sees ``password`` and not ``0``, and the row count.

    ``compiled_parameters`` holds one dict per row after IN-list expansion (``a_1``, ``a_2``), also for an
    insertmanyvalues batch the DBAPI gets as one flat tuple. Without a compiled statement the DBAPI parameters are
    kept and masked by value.
    """
    rows = getattr(context, "compiled_parameters", None) if getattr(context, "compiled", None) is not None else None
    if not rows or not parameters:
        return parameters, None
    # shortcut: an insertmanyvalues execute split into pages (over insertmanyvalues_page_size rows, 1000 by default)
    # records every page with the whole execute's rows and count, since SQLAlchemy does not show the listener which
    # page it is; still masked. Upgrade if per-page batch sizes matter: track the page offset on the context.
    return (rows, len(rows)) if executemany else (rows[0], None)


def _emit(
    state: tuple[int, list[SharpitContext]],
    conn: Any,
    statement: str,
    parameters: Any,
    executemany: bool,
    rowcount: int,
    error: BaseException | None,
    batch_size: int | None = None,
) -> None:
    started, targets = state
    duration = time.perf_counter_ns() - started
    try:
        connection_id: str | None = hex(id(conn.connection.dbapi_connection))
    except Exception:  # noqa: BLE001 - an invalidated connection has no DBAPI connection
        connection_id = None
    dispatch.deliver(
        SqlEvent(
            "sqlalchemy",
            statement,
            parameters,
            executemany,
            batch_size,
            started,
            duration,
            rowcount,
            error,
            connection_id,
            conn.engine,
        ),  # fmt: skip
        targets,
    )


def after_cursor_execute(
    conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
) -> None:
    try:
        start = _pop_start(conn, context)
        if start is not None:
            parameters, rows = _named(parameters, context, executemany)
            _emit(start, conn, statement, parameters, executemany, getattr(cursor, "rowcount", -1), None, rows)
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


def handle_error(exception_context: Any) -> None:
    try:
        context = exception_context.execution_context
        conn = exception_context.connection
        start = _pop_start(conn, context) if conn is not None else None
        if start is not None:
            error = exception_context.sqlalchemy_exception or exception_context.original_exception
            executemany = bool(getattr(context, "executemany", False))
            parameters, rows = _named(exception_context.parameters, context, executemany)
            _emit(start, conn, exception_context.statement or "", parameters, executemany, -1, error, rows)
    except Exception as exc:  # noqa: BLE001
        dispatch.routing_failed(exc)


_LISTENERS: dict[str, Callable[..., None]] = {
    DISCOVERY_EVENT: engine_connect,
    "before_cursor_execute": before_cursor_execute,
    "after_cursor_execute": after_cursor_execute,
    "handle_error": handle_error,
}


def _sync_listeners() -> None:
    """Listen while a context needs the event, remove once none does (callers hold ``_lock``)."""
    # swapped whole under the lock, read lock-free
    global _discovery_refs  # noqa: PLW0603
    _discovery_refs = tuple(weakref.ref(c) for c in _discovery_contexts.values())
    sa = sqlalchemy_module()
    if sa is None:
        return
    wanted = {
        DISCOVERY_EVENT: bool(_discovery_contexts),
        **dict.fromkeys(STATEMENT_EVENTS, bool(_statement_contexts) or _session),
    }
    for name, fn in _LISTENERS.items():
        present = sa.event.contains(sa.engine.Engine, name, fn)
        if wanted[name] and not present:
            sa.event.listen(sa.engine.Engine, name, fn)
        elif present and not wanted[name]:
            sa.event.remove(sa.engine.Engine, name, fn)


def add(ctx: SharpitContext, *, statements: bool, discovery: bool) -> bool:
    """Route statements and/or engine discovery to ``ctx``; False while SQLAlchemy is not imported (retry later)."""
    if sqlalchemy_module() is None:
        return False
    registry = ctx.capture.engine_registry
    if registry is not None:
        for engine in ctx.engines:
            registry.add(engine)
    with _lock:
        if statements:
            dispatch.add_context(ctx)
            _statement_contexts[ctx.context_id] = ctx
        if discovery:
            _discovery_contexts[ctx.context_id] = ctx
        _sync_listeners()
    return True


def remove(ctx: SharpitContext) -> None:
    with _lock:
        dispatch.remove_context(ctx)
        _statement_contexts.pop(ctx.context_id, None)
        _discovery_contexts.pop(ctx.context_id, None)
        _sync_listeners()


def detach_all() -> None:
    """Forget every context and remove every listener (tests start from a clean slate with it)."""
    global _session  # noqa: PLW0603
    with _lock:
        dispatch.clear_contexts()
        _statement_contexts.clear()
        _discovery_contexts.clear()
        _session = False
        _relationship_groups.clear()
        _relationship_sites.clear()
        _eager_relationship_batches.clear()
        _lazy_seen.clear()
        _sync_listeners()


def attach_session() -> bool:
    """Keep the statement listeners on for the test-session sink; False while SQLAlchemy is not imported (retry)."""
    global _session  # noqa: PLW0603 - read by _sync_listeners under the lock
    if sqlalchemy_module() is None:
        return False
    with _lock:
        _session = True
        _sync_listeners()
    return True


def detach_session() -> None:
    global _session  # noqa: PLW0603
    with _lock:
        _session = False
        _relationship_groups.clear()
        _relationship_sites.clear()
        _eager_relationship_batches.clear()
        _lazy_seen.clear()
        _sync_listeners()


def routed(ctx: SharpitContext) -> tuple[bool, bool]:
    """``(statements, discovery)``: whether ``ctx`` receives traced statements and discovered engines."""
    with _lock:
        return ctx.context_id in _statement_contexts, ctx.context_id in _discovery_contexts


def add_connection_listener(event: ConnectionEvent, fn: Callable[..., None]) -> Callable[[], None] | None:
    """Listen to the class-level ``Engine`` connection event ``event`` (O1 slot); returns an idempotent remover.

    Inert until a lane calls it (A-transactions registers here and never edits this module).
    Returns ``None`` while SQLAlchemy is not imported: call it from a ``CaptureState.attachers`` entry, which the
    wiring retries at startup and on the first request, as ``add`` is retried.
    """
    if event not in CONNECTION_EVENTS:
        raise ValueError(f"unknown connection event {event!r}")
    sa = sqlalchemy_module()
    if sa is None:
        return None
    with _lock:
        sa.event.listen(sa.engine.Engine, event, fn)

    def remove() -> None:
        with _lock:
            if sa.event.contains(sa.engine.Engine, event, fn):
                sa.event.remove(sa.engine.Engine, event, fn)

    return remove


def attached() -> dict[str, bool]:
    """Event name -> whether sharpit's class-level listener is on ``Engine``."""
    sa = sqlalchemy_module()
    if sa is None:
        return dict.fromkeys(_LISTENERS, False)
    return {name: bool(sa.event.contains(sa.engine.Engine, name, fn)) for name, fn in _LISTENERS.items()}


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
