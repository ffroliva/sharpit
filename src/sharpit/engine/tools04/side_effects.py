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
        "Return Side Effects: what the application does outside the process, from the sharpit agent's side-effect "
        "sensors; this version records the processes it starts, the files it opens, deletes, moves, and copies, and, "
        "opt-in, request input reaching a command or a file path (security-sinks, request-input-in-sink). Advertised "
        "only while a side-effects sensor records. Every sensor first, with its coverage (recording, disabled, "
        "not-available in this version), without its hooks or, when none of its rows is listed, its fixed limitations "
        "unless query names that sensor, then at most limit (20) rows, most frequent first, matching query: a sensor "
        "id such as processes, files, or security-sinks, or part of a route, target, or parameter. A row "
        "is attributed to a request's route, startup, or a thread family, with counts, failures, "
        "times, and up to three request ids. A process row names the command's file name only, never its arguments "
        "or environment; a file row a path pattern with its kind, location, and origin, never contents; a "
        "security-sinks row the command and argument index, or the file path pattern, that a request parameter's "
        "value reached unchanged, with that value redacted to {name}, the parameter's name, and a sentence stating "
        "the fact, a check to perform in the code and never a vulnerability verdict. Request-value matching is off "
        "by default and checks commands and file paths only; SQL statements and outbound URLs are not checked.",
        _QUERY_LIMIT_20,
        "side-effects",
        False,
        lambda c, a: side_effects(c.ctx, a["query"], a["limit"]),
        default_limit=20,
    ),
)
COMMANDS = {"get_side_effects": "side-effects"}
