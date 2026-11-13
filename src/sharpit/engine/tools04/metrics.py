from __future__ import annotations

from typing import Any

from sharpit.engine.collectors.metrics import metrics_report
from sharpit.engine.tools import Tool

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional case-insensitive filter applied to the results."},
        "limit": {
            "type": "integer",
            "minimum": 1,
            "default": 25,
            "description": "Optional maximum number of items to return; default 25, capped by the "
            "SHARPIT_MCP_MAX_RESULTS server limit.",
        },
    },
    "additionalProperties": False,
}

TOOLS = (
    Tool(
        "get_metrics",
        "Search the current application metrics inventory and return a bounded page of local meter values. "
        "Use a narrow metric-name query when diagnosing one runtime signal. At most limit (25) meters; "
        "page.hasMore means more matched.",
        _SCHEMA,
        "metrics",
        False,
        lambda call, args: metrics_report(
            call.ctx, args.get("query"), limit=str(args["limit"]) if "limit" in args else None
        ),
        25,
    ),
)
COMMANDS = {"get_metrics": "metrics"}
