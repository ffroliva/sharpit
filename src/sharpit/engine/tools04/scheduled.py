from typing import Any

from sharpit.engine.collectors.scheduled import scheduled_report
from sharpit.engine.tools import Tool

_NONE: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}

TOOLS = (
    Tool(
        "get_scheduled_tasks",
        "Return the current scheduled task inventory: in-memory APScheduler 3 jobs, configured Celery beat entries "
        "and arq cron jobs, by function name and trigger. Never reads a remote job store.",
        _NONE,
        "scheduled",
        False,
        lambda call, _args: scheduled_report(call.ctx),
    ),
)
COMMANDS = {"get_scheduled_tasks": "scheduled"}
