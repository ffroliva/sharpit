"""Whether this application's SQL can be recorded at all (BootUI ``insights/SqlCapture.java``, v2.3.0).

The ``sql`` and ``connection`` sources depend on it. Without it a check that reads only SQL would run over nothing and
report no finding, which must never read as a healthy result.
"""

from __future__ import annotations

from dataclasses import dataclass

# SqlCapture.DISABLED with sharpit's env name
DISABLED = "SQL capture is disabled (SHARPIT_SQL_TRACE_ENABLED=false), so no statement is recorded."
# SqlCapture.NOT_RECORDED with sharpit's recorders (SQLAlchemy 2.0+, the sqlite3 module) for BootUI's traced DataSource
NOT_RECORDED = (
    "This application's database access is not recorded: sharpit records statements through SQLAlchemy (2.0+) and the"
    " sqlite3 module, and neither is in use."
)
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
