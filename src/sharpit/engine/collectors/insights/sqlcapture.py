"""Whether this application's SQL can be recorded at all (BootUI ``insights/SqlCapture.java``, v2.3.0).

The ``sql`` and ``connection`` sources depend on it. This module guarantees one thing: the SQL trace flag off, or the
sql-trace panel off, is DISABLED, so a check that reads SQL is UNAVAILABLE rather than a healthy result. The wider fact
(no engine attached, hooks suspended, raw sqlite3 only) is not decided here; that is task W5c-sql-recorded-fact, and
until it lands a SQL-only check with no database can still read as evaluated with no finding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sharpit.engine.collectors.insights.capturestate import CaptureState

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

# SqlCapture.DISABLED with sharpit's env name
DISABLED = "SQL capture is disabled (SHARPIT_SQL_TRACE_ENABLED=false), so no statement is recorded."
# RuntimeInsightsService.sqlCapture: a supplier that throws
UNREADABLE = "Whether this application's SQL is recorded could not be read ({}), so no statement is counted."
NOT_RECORDED_SUFFIX = " Its SQL and connection evidence is not counted."  # RuntimeInsightsService.java:1001-1002
SQL_SOURCES = frozenset({"sql", "connection"})  # RuntimeInsightsService.readsSql


class SqlCapture(CaptureState):
    """Whether this application's SQL is recorded."""


def for_context(ctx: SharpitContext) -> SqlCapture:
    """``SqlCapture.of`` for ``ctx``, the disabled branch only: the recorder is enabled when the flag is on and the
    sql-trace panel is enabled (BootUiAutoConfiguration.bootUiSqlTraceRecorder, v2.3.0:803).

    Whether a database is in use at all (BootUI ``hasWrappedDataSource``, ``NOT_RECORDED``) is not decided here yet;
    that is task W5c-sql-recorded-fact, which needs a per-context fact set where a source is attached.
    """
    panel = ctx.settings.panels.get("sql-trace")
    if not ctx.settings.sql_trace_enabled or (panel is not None and not panel.enabled):
        return SqlCapture.not_recorded(DISABLED)
    return SqlCapture.capturing()
