"""Whether this application's SQL can be recorded at all (BootUI ``insights/SqlCapture.java``, v2.3.0).

The ``sql`` and ``connection`` sources depend on it. Without it a check that reads only SQL would run over nothing and
report no finding, which must never read as a healthy result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

# SqlCapture.DISABLED with sharpit's env name
DISABLED = "SQL capture is disabled (SHARPIT_SQL_TRACE_ENABLED=false), so no statement is recorded."
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
    def not_recorded(cls, reason: str) -> SqlCapture:
        return cls(False, reason)


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
