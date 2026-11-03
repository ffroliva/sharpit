"""The ``mysql`` panel's MCP/CLI tools (BootUI ``McpToolCatalog`` / ``McpToolDescriptions`` rows, 2.2.0).

``get_mysql_report`` is a read (MCP and CLI); ``mysql_read`` is an action, so it is CLI-only and refused when
the panel or sharpit is read-only.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sharpit.engine.collectors.mysql.limits import READ_BUDGET, STATEMENT_TIMEOUT
from sharpit.engine.collectors.mysql.service import (
    has_async_engine,
    mysql_report,
    refresh_mysql,
    summary,
    unavailable_report,
)
from sharpit.engine.tools import CallContext, Tool

_NONE: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


ASYNC_FROM_CLI = (
    "Reads of async engines run from the panel only: the CLI cannot reach the application's event loop, and an "
    "async engine's pool must not be driven from a second loop."
)


def _read(call: CallContext, _args: dict[str, Any]) -> dict[str, Any]:
    """Tool handlers run on a worker thread: the read goes to the app's loop when it is running, else a fresh one."""
    ctx = call.ctx
    loop = ctx.capture.loop
    if loop is not None and loop.is_running() and not loop.is_closed():
        future = asyncio.run_coroutine_threadsafe(refresh_mysql(ctx), loop)
        return summary(future.result(READ_BUDGET + 2 * STATEMENT_TIMEOUT + 5))
    if has_async_engine(ctx):
        return summary(unavailable_report(ASYNC_FROM_CLI))
    return summary(asyncio.run(refresh_mysql(ctx)))


TOOLS = (
    Tool(
        "mysql_read",
        "Actively read MySQL's performance_schema and information_schema views for the application "
        "datasources and record what the server currently reports: the live session snapshot, "
        "the top normalized statements, index and relation activity, lock waits, replication "
        "channels, global status metrics and notable settings. This is a runtime view, not an "
        "advisor: it grades nothing and emits no findings. The read is bounded and read-only. "
        "Read every section's `reason` before trusting its rows: a section sharpit read only "
        "partly stays `AVAILABLE` and carries a non-null `reason`, so `status` alone does not "
        "mean complete, while `SKIPPED` and `FAILED` mark a section it did not read at all. "
        "A `hint` is a methodology caveat on rows that were read, not missing evidence. "
        "`truncated` means the row cap was reached, and any of these degrades the datasource and "
        "report `status` to `PARTIAL`. Budget exhaustion is reported in `reason`, not as "
        "row-cap truncation. It answers with a summary, not the rows: status, message, readAt, "
        "truncated, and each datasource's status, message and sections (id, status, reason, "
        "rowCount, truncated). Read the rows, hints and details with get_mysql_report, which "
        "returns this read without querying again.",
        _NONE,
        "mysql",
        True,
        _read,
    ),
    Tool(
        "get_mysql_report",
        "Return the last completed MySQL runtime view without querying the server again. Before "
        "any read has run its `status` is `NOT_READ` and it carries no rows, which means nothing "
        "has been looked at rather than that nothing is wrong. Its session snapshot is only as "
        "current as that read, so prefer an active mysql_read when the question is about what the "
        "database is doing right now. Check each section's `reason` for missing coverage.",
        _NONE,
        "mysql",
        False,
        lambda call, _args: mysql_report(call.ctx),
    ),
)
COMMANDS = {"mysql_read": "db mysql read", "get_mysql_report": "db mysql report"}
