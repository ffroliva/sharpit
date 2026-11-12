"""The ``runtime-insights`` panel's MCP/CLI reads (BootUI ``McpToolCatalog`` rows ``get_runtime_insights`` and
``get_runtime_insight``). Both answer the agent view of what ``InsightsService`` projects from the journal."""

from __future__ import annotations

from typing import Any

from sharpit.engine.collectors.insights.agent_view import (
    DEFAULT_LIMIT,
    Steps,
    UnknownObservation,
    agent_detail,
    agent_list,
)
from sharpit.engine.collectors.insights.service import insights_service
from sharpit.engine.tools import _ID, CallContext, Tool, ToolCallError  # pyright: ignore[reportPrivateUsage]
from sharpit.settings import PanelSettings

_LIMIT_NOTE = (
    "Optional maximum number of items to return; default 8, capped by the SHARPIT_MCP_MAX_RESULTS server limit."
)
_QUERY_LIMIT: dict[str, Any] = {  # BootUI's QUERY_LIMIT row, whose schema carries this tool's default of 8
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional case-insensitive filter applied to the results."},
        "limit": {"type": "integer", "minimum": 1, "default": DEFAULT_LIMIT, "description": _LIMIT_NOTE},
    },
    "additionalProperties": False,
}


def _steps(call: CallContext) -> Steps:
    """Next steps name only tools this application advertises: in the catalogue, and their panel is enabled."""
    from sharpit.engine import tools

    panels = {tool.name: tool.panel for tool in tools.TOOLS}
    enabled = call.ctx.settings.panels
    return Steps(tools.COMMANDS, lambda name: name in panels and enabled.get(panels[name], PanelSettings()).enabled)


def _list(call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    return agent_list(insights_service(call.ctx).report(), args["query"], args["limit"], _steps(call))


def _show(call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return agent_detail(insights_service(call.ctx).insight(args["id"]), _steps(call))
    except UnknownObservation as exc:
        raise ToolCallError(str(exc), 404) from None


TOOLS = (
    Tool(
        "get_runtime_insights",
        "Return what this run did that no single panel shows, compacted: coverage first, the checks that did not fully "
        "run, then at most limit (8) observations with an id, status, one sentence, counts, an exemplar request id for "
        "get_request_profile, a verify line, and whether the default list shows it. query is empty, all, new, "
        "security, diff, latency, an observation kind, or a route, table, bean, or class; past the limit, listed rows "
        "come first and every kind is listed once before any kind twice. requests counts completed HTTP exchanges "
        "only: zero is not proof nothing ran when an observation names a request or execution, a non-HTTP limitation, "
        "or eviction says otherwise. A run-level observation with no exemplar does not. The empty query is the default "
        "list, which leaves several kinds out, for example time breakdowns, exception hotspots, repeated SELECTs, and "
        "garbage collection and heap rows; a limitation names each kind it left out with its count, and all, a kind, "
        "or a route lists them. An empty list means not exercised only when limitations say so. INSUFFICIENT, "
        "PARTIAL, NOT_APPLICABLE, and UNAVAILABLE are not successes. next names at most three follow-up calls, each "
        "a tool with its arguments and the equivalent sharpit command.",
        _QUERY_LIMIT,
        "runtime-insights",
        False,
        _list,
        DEFAULT_LIMIT,
    ),
    Tool(
        "get_runtime_insight",
        "Return one Runtime Insights observation by its id from get_runtime_insights, with every check to verify and "
        "at most 20 evidence rows. Drill down with get_request_profile on its exemplar request. An unknown or evicted "
        "id is a tool error naming get_runtime_insights, which lists the current ids; available=false with a reason "
        "means Runtime Insights is unavailable.",
        _ID,
        "runtime-insights",
        False,
        _show,
    ),
)
COMMANDS = {"get_runtime_insights": "insights list", "get_runtime_insight": "insights show"}
