"""Whether this application's SQL can be recorded at all (BootUI ``insights/SqlCapture.java``, v2.3.0).

The ``sql`` and ``connection`` sources depend on it. Without it a check that reads only SQL would run over nothing and
report no finding, which must never read as a healthy result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sharpit.engine import sqla

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

# SqlCapture.DISABLED with sharpit's env name
DISABLED = "SQL capture is disabled (SHARPIT_SQL_TRACE_ENABLED=false), so no statement is recorded."
# SqlCapture.NOT_RECORDED with sharpit's recorders (SQLAlchemy 2.0+, the sqlite3 module) for BootUI's traced DataSource
NOT_RECORDED = (
    "This application's database access is not recorded: sharpit records statements through SQLAlchemy (2.0+) and the"
    " sqlite3 module, and neither is in use."
)
# no SqlCapture counterpart: BootUI cannot suspend its DataSource tracing; sharpit's hooks (HookRegistry) can be
SUSPENDED = "SQL capture is suspended (its SQL hooks are detached), so no statement is recorded."
# SqlCapture.R2DBC_NOT_RECORDED for a library sharpit does not record (SQLAlchemy older than 2.0) beside sqlite3
UNSUPPORTED_NOT_RECORDED = "{}, so only raw sqlite3 statements are counted."
# RuntimeInsightsService.sqlCapture: a supplier that throws
UNREADABLE = "Whether this application's SQL is recorded could not be read ({}), so no statement is counted."
NOT_RECORDED_SUFFIX = " Its SQL and connection evidence is not counted."  # RuntimeInsightsService.java:1001-1002
SQL_SOURCES = frozenset({"sql", "connection"})  # RuntimeInsightsService.readsSql


@dataclass(frozen=True)
class SqlCapture:
    """``recorded``: statements can be recorded. ``reason``: why not, or what they still miss; ``None`` when nothing."""

    recorded: bool
    reason: str | None

    @classmethod
    def capturing(cls) -> SqlCapture:
        return cls(True, None)

    @classmethod
    def not_recorded(cls, reason: str | None = None) -> SqlCapture:
        return cls(False, NOT_RECORDED if reason is None else reason)

    @classmethod
    def recorded_except(cls, limitation: str) -> SqlCapture:
        """``SqlCapture.recordedExcept``: statements are recorded, but ``limitation`` names what they miss."""
        return cls(True, limitation)


def for_context(ctx: SharpitContext) -> SqlCapture:
    """``SqlCapture.of(recorder, tracedDataSourceRequired=true, r2dbc)`` for ``ctx``, from what is attached now.

    ``recorder.hasWrappedDataSource()`` becomes "a SQL source records for this context": the SQLAlchemy statement
    listeners routed here, or raw sqlite3 statements seen here (the patch is process-wide and attached at install, so
    its presence alone proves no database is used). A suspended hook records nothing. SQLAlchemy older than 2.0 is
    BootUI's R2DBC shape: not recorded, or recorded except that library when sqlite3 is in use.
    """
    if not ctx.settings.sql_trace_enabled:
        return SqlCapture.not_recorded(DISABLED)
    suspended = ctx.capture.suspended_sources
    sqlalchemy_on = "sqlalchemy" not in suspended and sqla.routed(ctx)[0]
    sqlite3_on = "sqlite3" not in suspended and sqla.sqlite3_traced(ctx) and ctx.capture.raw_sqlite_seen
    unsupported = sqla.unavailable_reason()
    if unsupported == sqla.UNAVAILABLE:  # not imported: the usual case, nothing to name
        unsupported = None
    if sqlalchemy_on or (sqlite3_on and unsupported is None):
        return SqlCapture.capturing()
    if sqlite3_on and unsupported is not None:
        return SqlCapture.recorded_except(UNSUPPORTED_NOT_RECORDED.format(unsupported))
    if suspended & {"sqlalchemy", "sqlite3"}:
        return SqlCapture.not_recorded(SUSPENDED)
    return SqlCapture.not_recorded(unsupported)
