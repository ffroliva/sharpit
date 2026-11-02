from __future__ import annotations

from sharpit.engine.collectors.sqlastats import statistics_report
from sharpit.engine.tools import _NONE, Tool  # pyright: ignore[reportPrivateUsage]

TOOLS = (
    Tool(
        "get_sqlalchemy_statistics",
        "Return SQLAlchemy statement statistics from the SQL Trace recorder: lifetime SELECT and statement counts, the "
        "slowest statement, and N+1 candidates per route. ORM session and entity counters are null with a reason.",
        _NONE,
        "sqlalchemy-statistics",
        False,
        lambda c, _a: statistics_report(c.ctx),
    ),
    Tool(
        "enable_sqlalchemy_statistics",
        "Acknowledge statistics collection and return the report. Statistics are always on while SQL Trace records; "
        "nothing is changed.",
        _NONE,
        "sqlalchemy-statistics",
        True,
        lambda c, _a: statistics_report(c.ctx),
    ),
)
COMMANDS = {
    "get_sqlalchemy_statistics": "sqlalchemy-statistics",
    "enable_sqlalchemy_statistics": "sqlalchemy-statistics enable",
}
