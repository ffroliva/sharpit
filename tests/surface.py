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


def lane_route_paths(ctx: Any) -> list[str]:
    """Sub-app paths the implemented per-panel route modules mount (appended after the base routes)."""
    return [route.path for route in _panel_04_routes(ctx)]  # pyright: ignore[reportAttributeAccessIssue]


def catalogue_with_lanes(
    lane_tools: tuple[Any, ...], lane_commands: dict[str, str]
) -> tuple[tuple[Any, ...], dict[str, str]]:
    """``(TOOLS, COMMANDS)`` as the import builds them: the base catalogue plus the given lane tools."""
    from sharpit.engine import tools

    # from the base, not the current TOOLS: a lane implemented at import already has its tools there
    return tools.merge_lane_tools(tools._BASE_TOOLS, tools._BASE_COMMANDS, lane_tools, lane_commands)  # noqa: SLF001


def plant_unimplemented_panel(monkeypatch: Any) -> str:
    """Flip the first still-unimplemented 0.4 panel on with a read tool, a CLI command and a GET route; return its id.

    Lanes that really implement their panel never collide with the plant; with every panel implemented it skips.
    """
    from importlib import import_module

    import pytest

    from sharpit.engine import mcp, tools

    plant = next((p for p in panels04.PANEL_04_IDS if not panels04.IMPLEMENTED[p]), None)
    if plant is None:
        pytest.skip("every 0.4 panel is implemented: no panel left to plant on")
    module = import_module(f"sharpit.engine.tools04.{plant.replace('-', '_')}")
    name = f"get_{plant.replace('-', '_')}_probe"
    planted = tools.Tool(name, "probe", _NONE_SCHEMA, plant, False, lambda _call, _args: {"probe": True})
    monkeypatch.setitem(panels04.IMPLEMENTED, plant, True)
    monkeypatch.setattr(module, "TOOLS", (*module.TOOLS, planted))
    monkeypatch.setattr(module, "COMMANDS", {**getattr(module, "COMMANDS", {}), name: f"{plant} probe"})
    _plant_route(monkeypatch, plant)
    merged_tools, merged_commands = catalogue_with_lanes(*panels04.tool_definitions())
    monkeypatch.setattr(tools, "TOOLS", merged_tools)
    monkeypatch.setattr(tools, "COMMANDS", merged_commands)
    monkeypatch.setattr(mcp, "TOOLS", merged_tools)
    return plant


_NONE_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


def _plant_route(monkeypatch: Any, plant: str) -> None:
    from importlib import import_module

    from starlette.responses import JSONResponse
    from starlette.routing import Route

    module = import_module(f"sharpit.fastapi.routes.{plant.replace('-', '_')}")
    original = getattr(module, "build_routes", None)

    def build_routes(ctx: Any) -> list[Any]:
        api = ctx.settings.api_path[len(ctx.settings.path) :]
        probe = Route(f"{api}/{plant}/probe", lambda _request: JSONResponse({"probe": True}), methods=["GET"])
        return [*(original(ctx) if original is not None else ()), probe]

    monkeypatch.setattr(module, "build_routes", build_routes, raising=False)
