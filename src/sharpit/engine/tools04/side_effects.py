from __future__ import annotations

from typing import Any

from sharpit.engine.tools import Tool  # pyright: ignore[reportPrivateUsage]

_LIMIT_20: dict[str, Any] = {
    "type": "integer",
    "minimum": 1,
    "default": 20,
    "description": "Optional maximum number of items to return; default 20, capped by the SHARPIT_MCP_MAX_RESULTS "
    "server limit.",
}
_QUERY_LIMIT_20: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional case-insensitive filter applied to the results."},
        "limit": _LIMIT_20,
    },
    "additionalProperties": False,
}


def side_effects(ctx: Any, query: str | None, limit: int | None) -> dict[str, Any]:
    return ctx.capture.side_effects.agent_report(query, limit)


TOOLS = (
    Tool(
        "get_side_effects",
        "Return Side Effects.",
        _QUERY_LIMIT_20,
        "side-effects",
        False,
        lambda c, a: side_effects(c.ctx, a["query"], a["limit"]),
        default_limit=20,
    ),
)
COMMANDS = {"get_side_effects": "side-effects"}
