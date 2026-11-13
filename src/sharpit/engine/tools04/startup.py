from typing import Any

from sharpit.engine.collectors.startup import startup_view
from sharpit.engine.tools import CallContext, Tool

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional case-insensitive filter applied to the results."},
        "limit": {
            "type": "integer",
            "minimum": 1,
            "default": 25,
            "description": (
                "Optional maximum number of items to return; default 25, capped by the SHARPIT_MCP_MAX_RESULTS "
                "server limit."
            ),
        },
    },
    "additionalProperties": False,
}


def _report(call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    return startup_view(call.ctx, args.get("query"), args["limit"])


TOOLS = (Tool("get_startup_timeline", "Return the host startup timeline.", _SCHEMA, "startup", False, _report, 25),)
COMMANDS = {"get_startup_timeline": "startup"}
