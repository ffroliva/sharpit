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


def sql_trace_unavailable_reason(ctx: SharpitContext) -> str | None:
    """Why SQL Trace shows nothing: tracing switched off, or SQLAlchemy 2.0+ not imported by the app."""
    if not ctx.settings.sql_trace_enabled:
        return TRACING_DISABLED
    return None if sqlite3_traced(ctx) else unavailable_reason()


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
    set_unbounded_read_factor,
    unbounded_read_capture_limitation_needed,
)
from sharpit.engine.sqla.readonly import (  # noqa: E402
    READ_ONLY_REFUSED,
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
    "set_unbounded_read_factor",
    "sql_trace_unavailable_reason",
    "sqlalchemy_module",
    "sqlite3_traced",
    "unavailable_reason",
    "unbounded_read_capture_limitation_needed",
]
