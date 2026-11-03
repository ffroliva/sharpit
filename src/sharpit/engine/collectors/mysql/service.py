"""The ``mysql`` panel's report: ``GET`` serves the last read, ``POST /read`` reads every MySQL engine.

Port of BootUI ``MySqlInsightService`` (2.2.0).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sharpit.engine import sqla

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

OPERATION = "mysql-read"
DISCLAIMER = (
    "Explicit, bounded READ ONLY observations of MySQL's own metadata and statistics, not application rows. "
    "Collection is not an atomic snapshot. Server counters include other clients; default-schema association is not "
    "exhaustive schema access. Pool acquisition and network timeouts are separate from the cooperative 15-second read "
    "budget. No health score or complete-history claim."
)
NOT_READ_MESSAGE = "No MySQL read has run. Run MySQL read explicitly to contact existing JDBC datasources."

Dto = dict[str, Any]


class MySqlState:
    report: Dto | None = None
    previous: dict[str, dict[str, Any]]


def mysql_report(ctx: SharpitContext) -> Dto:
    """The last read, or the initial ``NOT_READ`` report: never discovers an engine, never connects."""
    if (reason := sqla.unavailable_reason()) is not None:
        return unavailable_report(reason)
    state = ctx.peek("mysql")
    if isinstance(state, MySqlState) and state.report is not None:
        return state.report
    return _report("NOT_READ", NOT_READ_MESSAGE, None, None, 0, [], [], False)


def unavailable_report(reason: str) -> Dto:
    return _report("DISABLED", reason, None, None, 0, [], [], False)


async def refresh_mysql(_ctx: SharpitContext) -> Dto:
    """Read every registered MySQL engine (single-flight, held until every worker thread returns)."""
    return {"status": "NOT_READ", "message": NOT_READ_MESSAGE, "dataSources": [], "diagnostics": []}


def _report(
    status: str,
    message: str | None,
    read_started_at: int | None,
    read_at: int | None,
    data_sources_read: int,
    data_sources: list[Dto],
    diagnostics: list[Dto],
    truncated: bool,
    read_limitations: list[str] | None = None,
) -> Dto:
    return {
        "localOnly": True,
        "disclaimer": DISCLAIMER,
        "status": status,
        "message": message,
        "readStartedAt": read_started_at,
        "readAt": read_at,
        "dataSourcesRead": data_sources_read,
        "dataSources": data_sources,
        "diagnostics": diagnostics,
        "limitations": read_limitations or [],
        "truncated": truncated,
    }
