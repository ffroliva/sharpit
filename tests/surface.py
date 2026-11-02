"""The expected sharpit surface: the base panels, tools and commands pinned literally, plus what the 0.4 flags add.

Shared count- and list-pinned tests read their expectation here, so a lane flipping its own flag (and filling its own
``tools04``/``routes`` modules) never turns a foundation test red, while the base surface stays pinned exactly.
"""

from __future__ import annotations

from typing import Any

from sharpit.engine import panels04
from sharpit.engine.panels import PANELS
from sharpit.fastapi.routes import _panel_04_routes  # pyright: ignore[reportPrivateUsage]

BASE_PANEL_IDS = [
    "overview",
    "config",
    "mappings",
    "loggers",
    "beans",
    "vulnerabilities",
    "mcp-server",
    "cli",
    "activity",
    "http-exchanges",
    "exceptions",
    "sql-trace",
    "log-tail",
    "alembic",
    "database-connection-pools",
    "health",
    "threads",
    "rest-api",
    "http-probe",
]
BASE_MCP_TOOL_NAMES = [
    "get_overview",
    "get_config",
    "get_mappings",
    "get_loggers",
    "get_beans",
    "get_http_exchanges",
    "get_log_tail",
    "get_exceptions",
    "get_exception_detail",
    "get_sql_traces",
    "get_live_activity",
    "get_alembic_migrations",
    "get_health",
    "get_database_connection_pools",
    "get_threads",
    "get_vulnerabilities_report",
    "get_rest_api_report",
    "get_rest_api_rule_violations",
]
BASE_CLI_COMMANDS = {
    "get_overview": "overview",
    "get_config": "config",
    "get_mappings": "mappings",
    "get_loggers": "loggers",
    "get_beans": "beans",
    "get_http_exchanges": "http exchanges",
    "get_log_tail": "logs tail",
    "get_exceptions": "exceptions list",
    "get_exception_detail": "exceptions show",
    "clear_exceptions": "exceptions clear",
    "get_sql_traces": "sql traces",
    "clear_sql_traces": "sql clear",
    "pause_sql_trace_recording": "sql pause",
    "resume_sql_trace_recording": "sql resume",
    "get_live_activity": "activity",
    "get_alembic_migrations": "db alembic",
    "get_health": "health",
    "get_database_connection_pools": "db pools",
    "get_threads": "threads",
    "get_vulnerabilities_report": "vulnerabilities report",
    "vulnerabilities_scan": "vulnerabilities scan",
    "get_rest_api_report": "rest-api report",
    "get_rest_api_rule_violations": "rest-api violations",
    "rest_api_scan": "rest-api scan",
}


def lane_tools() -> tuple[Any, ...]:
    """The tools the implemented lane modules add (``engine/tools04/<id>.py``), in catalogue order."""
    return panels04.tool_definitions()[0]


def lane_commands() -> dict[str, str]:
    return panels04.tool_definitions()[1]


def expected_panel_ids() -> list[str]:
    return [*BASE_PANEL_IDS, *(p.id for p in PANELS if p.id in panels04.PANEL_04_IDS and p.implemented)]


def expected_mcp_tool_names() -> list[str]:
    return [*BASE_MCP_TOOL_NAMES, *(t.name for t in lane_tools() if not t.action)]


def expected_cli_commands() -> dict[str, str]:
    return {**BASE_CLI_COMMANDS, **lane_commands()}


def lane_route_paths(ctx: Any, host_app: Any) -> list[str]:
    """Sub-app paths the implemented per-panel route modules mount (appended after the base routes)."""
    return [route.path for route in _panel_04_routes(ctx, host_app)]  # pyright: ignore[reportAttributeAccessIssue]


def catalogue_with_lanes(
    lane_tools: tuple[Any, ...], lane_commands: dict[str, str]
) -> tuple[tuple[Any, ...], dict[str, str]]:
    """``(TOOLS, COMMANDS)`` as the import builds them: the base catalogue plus the given lane tools."""
    from sharpit.engine import tools

    return tools.merge_lane_tools(tools.TOOLS, tools.COMMANDS, lane_tools, lane_commands)
