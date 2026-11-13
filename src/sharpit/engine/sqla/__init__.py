"""The SQLAlchemy bridge (spec §6.1 steps 4a/4b, §6.2): engine registry, class-level listeners, statement routing.

sharpit never imports SQLAlchemy: it reads ``sys.modules``, so an app that does not use it pays nothing, and the
listeners attach at install, at startup or on the first request, whichever first finds it imported. Listeners are
class-level on ``Engine`` (they see engines created before and after install) and shared by every installed
context and the test session; ``sources.dispatch`` sends each statement to the contexts it belongs to.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import TYPE_CHECKING, Any

from sharpit.engine.capture.correlation import TEST  # sqla.TEST, as the single module exposed it
from sharpit.engine.sources import sqlite

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

logger = logging.getLogger("sharpit")
UNAVAILABLE = "SQLAlchemy is not imported by this application"
TRACING_DISABLED = "SQL tracing is disabled via SHARPIT_SQL_TRACE_ENABLED=false"
_lock = threading.Lock()  # one lock for the whole package (listeners, ORM facts, connection events)


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


SQLALCHEMY, SQLITE3 = "sqlalchemy", "sqlite3"  # the two SQL sources, as ``dispatch`` names them
# SqlCapture.NOT_RECORDED with sharpit's recorders
NOT_RECORDED = (
    "This application's database access is not recorded: sharpit records statements through SQLAlchemy (2.0+) and"
    " the sqlite3 module, and no SQLAlchemy engine is attached to it and no sqlite3 statement has reached it."
)
SUSPENDED_ALL = "SQL capture is suspended (its SQL hooks are detached), so no statement is recorded."
_SUSPENDED = {
    SQLALCHEMY: "SQL capture is suspended for SQLAlchemy (its hook is detached), so its statements are not counted.",
    SQLITE3: "SQL capture is suspended for sqlite3 (its hook is detached), so its statements are not counted.",
}


def _in_use(ctx: SharpitContext) -> dict[str, bool]:
    """Which SQL sources have a database in use here (nothing runs per statement; see ``sources_recorded``)."""
    capture = ctx.capture
    registry = capture.engine_registry
    return {
        # seen_any is write-once: the registry holds engines weakly, so a collected engine stays a database used here
        SQLALCHEMY: capture.engines_unseen or (registry is not None and registry.seen_any),
        SQLITE3: capture.sqlite_delivered,
    }


def sources_recorded(ctx: SharpitContext) -> tuple[bool, str | None]:
    """``SqlCapture.of``'s second branch for ``ctx``: is a database in use here, and is its hook attached.

    BootUI's fact is known at wrap time (``SqlTraceRecorder.hasWrappedDataSource``): a SQLAlchemy engine registered
    with this context is the analogue; raw sqlite3 (no wrap-time object) counts once a statement was delivered to this
    context. Nothing here runs per statement: engines are registered when they connect; with no discovery panel the
    engines are unknown, and attaching the SQL listeners (``engines_unseen``) is the fact (a deviation row). A hook
    detached from a source in use is named (``recordedExcept``); every one detached: not recorded.
    """
    used = _in_use(ctx)
    suspended = ctx.capture.suspended_sources
    live = [s for s, in_use in used.items() if in_use and s not in suspended]
    missed = [s for s, in_use in used.items() if in_use and s in suspended]
    unsupported = unavailable_reason()
    extra = [] if unsupported in {None, UNAVAILABLE} else [f"{unsupported}, so its statements are not counted."]
    if live:
        return True, " ".join([*(_SUSPENDED[s] for s in missed), *extra]) or None
    return False, " ".join([SUSPENDED_ALL if missed else NOT_RECORDED, *extra])


def tracing_unavailable_reason(ctx: SharpitContext) -> str | None:
    """Why SQL Trace shows nothing: tracing switched off, or SQLAlchemy 2.0+ not imported by the app.

    ``sqlastats`` reads this one: BootUI's Hibernate statistics follow the session factory, never the SQL recorder
    (``HibernateStatisticsService.report``, v2.3.0), so no engine attached does not make them unavailable."""
    if not ctx.settings.sql_trace_enabled:
        return TRACING_DISABLED
    return None if sqlite3_traced(ctx) else unavailable_reason()


def sql_trace_unavailable_reason(ctx: SharpitContext) -> str | None:
    """The SQL Trace panel and its insights: ``tracing_unavailable_reason``, then no database in use here.

    BootUI reports both unavailable while no DataSource is wrapped (``SqlTraceControllerSupport.report`` and
    ``SqlTraceInsightsService.insights``, v2.3.0), and a suspended hook is a capture state, not an absent database, so
    only "in use" counts here (the insights also name a suspended hook). One text replaces BootUI's two (a deviation
    row)."""
    reason = tracing_unavailable_reason(ctx)
    if reason is not None or any(_in_use(ctx).values()):
        return reason
    return sources_recorded(ctx)[1]


# the submodules import the names above, so they load after them
from sharpit.engine.sqla.events import (  # noqa: E402
    CONNECTION_EVENTS,
    ConnectionEvent,
    add_connection_listener,
)
from sharpit.engine.sqla.inspect import (  # noqa: E402
    EngineRegistry,
    live_engine_drivers,
)
from sharpit.engine.sqla.listeners import (  # noqa: E402
    DISCOVERY_EVENT,
    DISCOVERY_PANELS,
    START_KEY,
    STATEMENT_EVENTS,
    add,
    after_cursor_execute,
    attach_session,
    attached,
    before_cursor_execute,
    detach_all,
    detach_session,
    engine_connect,
    handle_error,
    note_request_captured,
    remove,
    routed,
)
from sharpit.engine.sqla.orm import (  # noqa: E402
    GENERIC_BATCH,
    MAX_STATEMENT_SITES,
    RELATIONSHIP_KEY,
    apply_relationship_facts,
    apply_unbounded_read_facts,
    set_identity_key,
    set_unbounded_read_factor,
    unbounded_read_capture_limitation_needed,
)
from sharpit.engine.sqla.readonly import (  # noqa: E402
    READ_ONLY_REFUSED,
    SHARED_CONNECTION_REFUSED,
    ReadOnlyUnavailable,
    bounded,
    bounded_read_only,
    is_internal,
    run_db_read,
)

__all__ = [
    "TEST",
    "CONNECTION_EVENTS",
    "ConnectionEvent",
    "DISCOVERY_EVENT",
    "DISCOVERY_PANELS",
    "EngineRegistry",
    "GENERIC_BATCH",
    "MAX_STATEMENT_SITES",
    "READ_ONLY_REFUSED",
    "SHARED_CONNECTION_REFUSED",
    "RELATIONSHIP_KEY",
    "ReadOnlyUnavailable",
    "START_KEY",
    "STATEMENT_EVENTS",
    "TRACING_DISABLED",
    "UNAVAILABLE",
    "add",
    "add_connection_listener",
    "after_cursor_execute",
    "apply_relationship_facts",
    "apply_unbounded_read_facts",
    "attach_session",
    "attached",
    "before_cursor_execute",
    "bounded",
    "bounded_read_only",
    "detach_all",
    "detach_session",
    "engine_connect",
    "handle_error",
    "is_internal",
    "live_engine_drivers",
    "logger",
    "note_request_captured",
    "remove",
    "routed",
    "run_db_read",
    "set_identity_key",
    "set_unbounded_read_factor",
    "SQLALCHEMY",
    "SQLITE3",
    "NOT_RECORDED",
    "SUSPENDED_ALL",
    "sources_recorded",
    "sql_trace_unavailable_reason",
    "tracing_unavailable_reason",
    "sqlalchemy_module",
    "sqlite3_traced",
    "unavailable_reason",
    "unbounded_read_capture_limitation_needed",
]
