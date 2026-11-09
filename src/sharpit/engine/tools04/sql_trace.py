from __future__ import annotations

from typing import Any

from sharpit.engine.capture.sqlinsights import insights_report
from sharpit.engine.sqla import sql_trace_unavailable_reason
from sharpit.engine.tools import _NONE, Tool  # pyright: ignore[reportPrivateUsage]


def insights(ctx: Any) -> dict[str, Any]:
    """``SqlTraceInsightsReport`` over the retained ring; unavailable while tracing is off or SQLAlchemy is absent."""
    return insights_report(ctx.capture.sql_trace, ctx.capture.exchanges, sql_trace_unavailable_reason(ctx))


TOOLS = (
    Tool(
        "get_sql_trace_insights",
        "Rank the SQL statements retained in the SQL Trace buffer by total, max, average, p95 and p99 duration, "
        "executions and errors, and attribute them to the HTTP routes that issued them. Statements are normalized: "
        "no literal or bound value is shown. Figures describe the retained window, not lifetime totals.",
        _NONE,
        "sql-trace",
        False,
        lambda c, _a: insights(c.ctx),
    ),
)
COMMANDS = {"get_sql_trace_insights": "sql-trace insights"}
