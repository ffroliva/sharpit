"""Whether this application's SQL can be recorded at all (BootUI ``insights/SqlCapture.java``, v2.3.0).

The ``sql`` and ``connection`` sources depend on it. ``for_context`` ports ``SqlCapture.of``: disabled (flag or panel
off) -> DISABLED, no database in use -> NOT_RECORDED, a hook detached from a database in use -> ``recordedExcept``.
The database fact itself is ``sqla.sources_recorded``, the one read by every surface (this, the SQL Trace panel and
MCP reasons, ``sqlastats``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sharpit.engine import sqla

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

# SqlCapture.DISABLED with sharpit's env name
DISABLED = "SQL capture is disabled (SHARPIT_SQL_TRACE_ENABLED=false), so no statement is recorded."
# the panel off with the flag on is not the flag's doing: BootUiAutoConfiguration.bootUiSqlTraceRecorder (v2.3.0:803)
# builds no recorder then, and sharpit's text says which switch it was (a deviation row)
PANEL_OFF = "SQL capture is disabled (the sql-trace panel is disabled), so no statement is recorded."
NOT_RECORDED = sqla.NOT_RECORDED
# RuntimeInsightsService.sqlCapture: a supplier that throws
UNREADABLE = "Whether this application's SQL is recorded could not be read ({}), so no statement is counted."
NOT_RECORDED_SUFFIX = " Its SQL and connection evidence is not counted."  # RuntimeInsightsService.java:1001-1002
SQL_SOURCES = frozenset({"sql", "connection"})  # RuntimeInsightsService.readsSql


@dataclass(frozen=True)
class SqlCapture:
    """``SqlCapture`` record: ``reason`` is why statements are not recorded, or, when ``recorded``, what they miss."""

    recorded: bool
    reason: str | None

    @classmethod
    def capturing(cls) -> SqlCapture:
        return cls(True, None)

    @classmethod
    def recorded_except(cls, limitation: str) -> SqlCapture:
        return cls(True, limitation)

    @classmethod
    def not_recorded(cls, reason: str) -> SqlCapture:
        return cls(False, reason)


def for_context(ctx: SharpitContext) -> SqlCapture:
    """``SqlCapture.of`` for ``ctx``. The recorder exists only while the flag and the sql-trace panel are on
    (BootUiAutoConfiguration.bootUiSqlTraceRecorder, v2.3.0:803), so its absence is the disabled branch."""
    if not ctx.settings.sql_trace_enabled:
        return SqlCapture.not_recorded(DISABLED)
    if ctx.capture.sql_trace is None:
        return SqlCapture.not_recorded(PANEL_OFF)
    recorded, reason = sqla.sources_recorded(ctx)
    if not recorded:
        return SqlCapture.not_recorded(reason or NOT_RECORDED)
    return SqlCapture.recorded_except(reason) if reason else SqlCapture.capturing()
