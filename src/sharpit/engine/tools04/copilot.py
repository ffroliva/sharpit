from __future__ import annotations

from typing import Any

from sharpit.engine.collectors.agentsessions import Layout, session_store
from sharpit.engine.paging import paged
from sharpit.engine.tools import CallContext, Tool

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional case-insensitive filter applied to the results."},
        "limit": {
            "type": "integer",
            "minimum": 1,
            "default": 10,
            "description": (
                "Optional maximum number of items to return; default 10, capped by the SHARPIT_MCP_MAX_RESULTS "
                "server limit."
            ),
        },
    },
    "additionalProperties": False,
}

_DESCRIPTION = (
    "Return the bounded, sanitized Copilot CLI session inventory parsed from local session files. "
    "Raw prompts, tool arguments, command output, diffs, and network calls are excluded. "
    "At most limit (10) sessions matching query (id, model, working directory, status, or last activity). "
    "The first read after startup parses the newest session files (bootui.copilot.max-parsed-sessions) "
    "and can take seconds on a large session directory; "
    "later reads answer from the cache a directory watcher keeps current."
)


def _report(call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    store = session_store(call.ctx, Layout.COPILOT)
    store.refresh()
    list_dto = store.sessions()
    sessions = list_dto["sessions"]
    query = args.get("query")
    limit = args.get("limit", 10)
    listed, page = paged(
        sessions,
        query,
        None,
        limit,
        lambda s: (
            s.get("id"),
            s.get("model"),
            s.get("workingDirectory"),
            s.get("status"),
            s.get("lastActivitySummary"),
        ),
    )
    return {
        "available": list_dto["available"],
        "unavailableReason": list_dto["unavailableReason"],
        "sessionStateDir": list_dto["sessionStateDir"],
        "total": list_dto["total"],
        "returned": len(listed),
        "maxSessions": list_dto["maxSessions"],
        "sessions": listed,
        "warnings": list_dto["warnings"],
        "page": page,
    }


TOOLS = (
    Tool(
        "get_copilot_sessions",
        _DESCRIPTION,
        _SCHEMA,
        "copilot",
        False,
        _report,
        10,
    ),
)
COMMANDS = {"get_copilot_sessions": "sessions copilot"}
