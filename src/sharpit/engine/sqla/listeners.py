"""Class-level statement and discovery listeners on ``Engine``, and which contexts they route to."""

# pyright: reportPrivateUsage=false
# the package was one module until 0.5.0; its submodules share private state

from __future__ import annotations

import sys
import time
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from sharpit.engine import sqla as _sqla
from sharpit.engine.capture.correlation import INTERNAL, REQUEST
from sharpit.engine.sources import dispatch  # the module, not its names: dispatch imports this package
from sharpit.engine.sqla import _lock
from sharpit.engine.sqla import connections as _connections
from sharpit.engine.sqla import orm as _orm
from sharpit.engine.sqla.dialect_source import engine_dialect
from sharpit.engine.sqla.orm import (
    _eager_relationship_batches,
    _lazy_seen,
    _mapper_load,
    _record_relationship,
    _relationship_groups,
    _relationship_sites,
    _statement_sites,
    _unbounded_read_facts,
    _unbounded_read_missing_capture,
)
from sharpit.engine.sqltext import Dialect

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

STATEMENT_EVENTS = ("before_cursor_execute", "after_cursor_execute", "handle_error")
POOL_EVENTS = ("checkout", "checkin")  # the connection journal event: follow a connection, offer it when released
DISCOVERY_EVENT = "engine_connect"
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

_discovery_contexts: weakref.WeakValueDictionary[str, SharpitContext] = weakref.WeakValueDictionary()
# what the listener reads per event: a plain tuple, refreshed on every change (iterating the dict is slow)
_discovery_refs: tuple[weakref.ref[SharpitContext], ...] = ()
# contexts that asked for statements through ``add`` (``routed`` reads it); weak, so a collected one stops counting
_statement_contexts: weakref.WeakValueDictionary[str, SharpitContext] = weakref.WeakValueDictionary()
_session = False  # the test-session sink wants statements too (spec 0.3.0 §8.1)
_counting = False  # a pool listener follows connections, so each statement bumps its connection's count


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
        if _counting and (followed := conn.info.get(_connections.CHECKOUT_KEY)) is not None:
            followed.statements += 1  # BootUI ``ConnectionCheckout.statementExecuted``: the application's own only
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
    # the connection's, not the engine's: ``event_dialect`` compares the two. They are one object until a dialect is
    # replaced, so the check proves the engine did not move, not which server answered.
    dialect = engine_dialect(conn)
    dispatch.deliver(
        dispatch.SqlEvent(
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
            Dialect.UNSUPPORTED if dialect is None else dialect,
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
    "checkout": _connections.checkout,
    "checkin": _connections.checkin,
}


def _records_connections(ctx: SharpitContext) -> bool:
    """Whether ``ctx``'s journal is configured for ``connection`` (BootUI ``journal.records(CONNECTION)``)."""
    journal = ctx.capture.journal
    return journal is not None and (journal.sources is None or _connections.SOURCE in journal.sources)


def _target(sa: Any, name: str) -> Any:
    """The class a listener sits on: the pool events belong to ``Pool``, the rest to ``Engine``."""
    return sa.pool.Pool if name in POOL_EVENTS else sa.engine.Engine


def _sync_listeners() -> None:
    """Listen while a context needs the event, remove once none does (callers hold ``_lock``)."""
    # swapped whole under the lock, read lock-free
    global _discovery_refs, _counting  # noqa: PLW0603
    _discovery_refs = tuple(weakref.ref(c) for c in _discovery_contexts.values())
    sa = _sqla.sqlalchemy_module()
    if sa is None:
        return
    followed = any(_records_connections(c) for c in _statement_contexts.values())
    _counting = followed
    wanted = {
        DISCOVERY_EVENT: bool(_discovery_contexts),
        **dict.fromkeys(STATEMENT_EVENTS, bool(_statement_contexts) or _session),
        **dict.fromkeys(POOL_EVENTS, followed),
    }
    for name, fn in _LISTENERS.items():
        target = _target(sa, name)
        present = sa.event.contains(target, name, fn)
        if wanted[name] and not present:
            sa.event.listen(target, name, fn)
        elif present and not wanted[name]:
            sa.event.remove(target, name, fn)


def add(ctx: SharpitContext, *, statements: bool, discovery: bool) -> bool:
    """Route statements and/or engine discovery to ``ctx``; False while SQLAlchemy is not imported (retry later)."""
    if _sqla.sqlalchemy_module() is None:
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
        _statement_sites.clear()
        _eager_relationship_batches.clear()
        _lazy_seen.clear()
        _sync_listeners()


def attach_session() -> bool:
    """Keep the statement listeners on for the test-session sink; False while SQLAlchemy is not imported (retry)."""
    global _session  # noqa: PLW0603 - read by _sync_listeners under the lock
    if _sqla.sqlalchemy_module() is None:
        return False
    with _lock:
        if not _session:
            _unbounded_read_facts.clear()
        _session = True
        _sync_listeners()
        sa = _sqla.sqlalchemy_module()
        orm = sys.modules.get("sqlalchemy.orm")
        if sa is not None and orm is not None and not sa.event.contains(orm.Mapper, "load", _mapper_load):
            sa.event.listen(orm.Mapper, "load", _mapper_load)
    return True


def detach_session() -> None:
    global _session  # noqa: PLW0603
    with _lock:
        _session = False
        sa = _sqla.sqlalchemy_module()
        orm = sys.modules.get("sqlalchemy.orm")
        if sa is not None and orm is not None and sa.event.contains(orm.Mapper, "load", _mapper_load):
            sa.event.remove(orm.Mapper, "load", _mapper_load)
        _unbounded_read_missing_capture.clear()
        _orm._unbounded_read_capture_missing = False
        _orm._unbounded_read_request_seen = False
        _orm._unbounded_read_factor = 2
        _relationship_groups.clear()
        _relationship_sites.clear()
        _statement_sites.clear()
        _eager_relationship_batches.clear()
        _lazy_seen.clear()
        _sync_listeners()


def routed(ctx: SharpitContext) -> tuple[bool, bool]:
    """``(statements, discovery)``: whether ``ctx`` receives traced statements and discovered engines."""
    with _lock:
        return ctx.context_id in _statement_contexts, ctx.context_id in _discovery_contexts


def following_connections(ctx: SharpitContext) -> bool:
    """Whether the pool listener runs for ``ctx``: the ``connection`` journal event can be produced.
    shortcut: a connection detached with ``Connection.detach()`` never fires ``checkin``, so it offers no event."""
    with _lock:
        return ctx.context_id in _statement_contexts and all(attached()[name] for name in POOL_EVENTS)


def note_request_captured() -> None:
    if not _session:
        return
    with _lock:
        _orm._unbounded_read_request_seen = True


def attached() -> dict[str, bool]:
    """Event name -> whether sharpit's class-level listener is on ``Engine`` (``Pool`` for the pool events)."""
    sa = _sqla.sqlalchemy_module()
    if sa is None:
        return dict.fromkeys(_LISTENERS, False)
    return {name: bool(sa.event.contains(_target(sa, name), name, fn)) for name, fn in _LISTENERS.items()}
