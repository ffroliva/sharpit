"""The ``mysql`` panel's report service (BootUI 2.2.0 contract §6).

``mysql_report(ctx)`` returns the last completed read or the initial ``NOT_READ`` report without
connecting or querying any database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sharpit.engine import sqla

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

Dto = dict[str, Any]

DISCLAIMER = (
    "Explicit, bounded READ ONLY observations of MySQL's own metadata and statistics, not application "
    "rows. Collection is not an atomic snapshot. Server counters include other clients; default-schema "
    "association is not exhaustive schema access. Pool acquisition and network timeouts are separate "
    "from the cooperative 15-second read budget. No health score or complete-history claim."
)
NOT_READ_MESSAGE = "No MySQL read has run. Run MySQL read explicitly to contact existing JDBC datasources."


@dataclass
class MySqlState:
    report: Dto | None = None
    previous: dict[str, dict[str, Any]] | None = None


def _report(
    status: str,
    message: str | None,
    read_started_at: int | None,
    read_at: int | None,
    datasources_read: int,
    datasources: list[Dto],
    diagnostics: list[Dto],
    truncated: bool,
    limitations: list[str] | None = None,
) -> Dto:
    return {
        "localOnly": True,
        "disclaimer": DISCLAIMER,
        "status": status,
        "message": message,
        "readStartedAt": read_started_at,
        "readAt": read_at,
        "dataSourcesRead": datasources_read,
        "dataSources": datasources,
        "diagnostics": diagnostics,
        "limitations": limitations or [],
        "truncated": truncated,
    }


def unavailable_report(reason: str) -> Dto:
    """A ``DISABLED`` report that read nothing, for a read sharpit refused to start."""
    return _report("DISABLED", reason, None, None, 0, [], [], False)


def mysql_report(ctx: SharpitContext) -> Dto:
    """The last read, or the initial ``NOT_READ`` report: never discovers an engine, never connects."""
    if (reason := sqla.unavailable_reason()) is not None:
        return unavailable_report(reason)
    state = ctx.peek("mysql")
    if isinstance(state, MySqlState) and state.report is not None:
        return state.report
    return _report("NOT_READ", NOT_READ_MESSAGE, None, None, 0, [], [], False)
