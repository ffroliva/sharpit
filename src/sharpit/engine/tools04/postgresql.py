"""The ``postgresql`` panel's MCP/CLI tools (BootUI ``McpToolCatalog`` / ``McpToolDescriptions`` rows, 2.2.0).

``get_postgresql_report`` is a read (MCP and CLI); ``postgresql_read`` is an action, so it is CLI-only and refused when
the panel or sharpit is read-only.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sharpit.engine.collectors.postgresql.service import postgresql_report, refresh_postgresql, summary
from sharpit.engine.tools import CallContext, Tool

_NONE: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


def _read(call: CallContext, _args: dict[str, Any]) -> dict[str, Any]:
    # shortcut: tool handlers run on a worker thread (run_in_threadpool), so a fresh loop is safe here
    return summary(asyncio.run(refresh_postgresql(call.ctx)))


TOOLS = (
    Tool(
        "postgresql_read",
        "Actively read PostgreSQL's own pg_stat_* and pg_catalog views for the application datasources "
        "and record what the server currently reports: the live session snapshot, cache hit and "
        "rollback ratios, connection usage, transaction-ID age, the top normalized statements, "
        "index and relation activity, autovacuum state, replication and notable settings. This "
        "is a runtime view, not an advisor: it grades nothing and emits no findings. The read is "
        "bounded and read-only. Read every section's `reason` before trusting its rows: a "
        "section sharpit read only partly stays `AVAILABLE` and carries a non-null `reason`, so "
        "`status` alone does not mean complete, while `SKIPPED` and `FAILED` mark a section it "
        "did not read at all. A `hint` is a methodology caveat on rows that were read, not "
        "missing evidence. `truncated` means the row cap was reached, and any of these degrades "
        "the database and report `status` to `PARTIAL`. The usual cause is a role without "
        "pg_monitor membership, which hides other backends from the session list and the "
        "statement text and replica details from their sections. Budget exhaustion is reported "
        "in `reason`, not as row-cap truncation. An empty replica list proves absence only when "
        "`replication.replicasAvailable` is true; otherwise the list was not read. It answers with a summary, not "
        "the rows: status, message, readAt, truncated, and each database's status, message and sections (id, status, "
        "reason, rowCount, truncated). Read the rows, hints and replication details with get_postgresql_report, "
        "which returns this read without querying again.",
        _NONE,
        "postgresql",
        True,
        _read,
    ),
    Tool(
        "get_postgresql_report",
        "Return the last completed PostgreSQL runtime view without querying the server again. Before any "
        "read has run its `status` is `NOT_READ` and it carries no rows, which means nothing has "
        "been looked at rather than that nothing is wrong. Its session snapshot is only as "
        "current as that read, so prefer an active postgresql_read when the question is about "
        "what the database is doing right now. Check each section's `reason` for missing coverage; "
        "an empty replica list proves absence only when `replication.replicasAvailable` is true.",
        _NONE,
        "postgresql",
        False,
        lambda call, _args: postgresql_report(call.ctx),
    ),
)
COMMANDS = {"postgresql_read": "db postgres read", "get_postgresql_report": "db postgres report"}
