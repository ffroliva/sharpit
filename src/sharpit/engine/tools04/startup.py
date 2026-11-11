from typing import Any

from sharpit.engine.collectors.startup import startup_report
from sharpit.engine.tools import CallContext, Tool

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional case-insensitive filter applied to the results."},
        "limit": {"type": "integer", "minimum": 1, "default": 25},
    },
    "additionalProperties": False,
}


def _report(call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    return startup_report(call.ctx, args.get("query"), args.get("limit", 25))


TOOLS = (Tool("get_startup_timeline", "Return the host startup timeline.", _SCHEMA, "startup", False, _report, 25),)
COMMANDS = {"get_startup_timeline": "startup"}
