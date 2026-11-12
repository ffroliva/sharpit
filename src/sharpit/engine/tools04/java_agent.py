from __future__ import annotations

from typing import Any

from sharpit.engine.sensors.floor import SensorRefusal, java_agent_report, switch_sensor_for_agents
from sharpit.engine.tools import _ID, _QUERY, CallContext, Tool, ToolCallError  # pyright: ignore[reportPrivateUsage]

_SWITCH = (
    " one supported sharpit agent sensor for this application now; the override is not persisted. id is one of"
    " threads, files, environment, thread-activity, thread-locals, or security-sinks. The agent must be attached and"
    " armed for this application: this version ships no agent sensors, so a switchable id is refused (409, not armed)"
    " and any other id is refused (400). Returns the updated Java Agent report; ask the user before switching."
)


def _status(_call: CallContext, _args: dict[str, Any]) -> dict[str, Any]:
    return java_agent_report()  # no sensors to filter by query in this version


def _switch(_call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return switch_sensor_for_agents(args["id"])
    except SensorRefusal as refusal:
        raise ToolCallError(refusal.message, refusal.status) from None


TOOLS = (
    Tool(
        "get_agent_status",
        "Return the sharpit agent's status: NOT_ATTACHED with a reason in this version, which ships no agent sensors;"
        " versions, the current claim, sensors, and setup. This read never claims, installs, or changes anything."
        " Query with a sensor id to list only matching sensors.",
        _QUERY,
        "java-agent",
        False,
        _status,
    ),
    Tool("enable_agent_sensor", "With the user's authorization, switch on" + _SWITCH, _ID, "java-agent", True, _switch),
    Tool(
        "disable_agent_sensor", "With the user's authorization, switch off" + _SWITCH, _ID, "java-agent", True, _switch
    ),
)
COMMANDS = {
    "get_agent_status": "agent status",
    "enable_agent_sensor": "agent sensor enable",
    "disable_agent_sensor": "agent sensor disable",
}
