"""Proof that the shared surface expectations (tests/surface.py) follow a 0.4 flag flip with a planted tool."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

import surface
from fastapi import FastAPI
from sharpit import install
from sharpit.engine import mcp, panels04, tools
from sharpit.engine.tools import Tool
from sharpit.engine.tools04 import data as data_tools
from sharpit.fastapi.routes import _panel_04_routes
from sharpit.fastapi.routes import data as data_routes

LOCAL = ("127.0.0.1", 50000)
NONE_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


@pytest.fixture
def data_flipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """What A-data's merge looks like: its flag true, one read tool, one CLI command and one GET route."""
    planted = Tool("get_data_probe", "probe", NONE_SCHEMA, "data", False, lambda _call, _args: {"probe": True})
    monkeypatch.setitem(panels04.IMPLEMENTED, "data", True)
    monkeypatch.setattr(data_tools, "TOOLS", (planted,))
    monkeypatch.setattr(data_tools, "COMMANDS", {"get_data_probe": "data probe"})

    def probe(request: Request) -> JSONResponse:
        return JSONResponse({"probe": True})

    def build_routes(ctx: Any, host_app: Any) -> list[BaseRoute]:
        api = ctx.settings.api_path[len(ctx.settings.path) :]
        return [Route(f"{api}/data/probe", probe, methods=["GET"])]

    monkeypatch.setattr(data_routes, "build_routes", build_routes)
    # TOOLS/COMMANDS are built at import: rebuild them as the import would with the flag on
    lane_tools, lane_commands = panels04.tool_definitions()
    merged_tools, merged_commands = surface.catalogue_with_lanes(lane_tools, lane_commands)
    monkeypatch.setattr(tools, "TOOLS", merged_tools)
    monkeypatch.setattr(tools, "COMMANDS", merged_commands)
    monkeypatch.setattr(mcp, "TOOLS", merged_tools)


def test_every_shared_count_follows_a_flag_flip(data_flipped: None) -> None:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, mcp_enabled="ON")
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    panel_ids = [p["id"] for p in client.get("/sharpit/api/panels").json()["panels"]]
    assert panel_ids == surface.expected_panel_ids()
    assert panel_ids[-1] == "data"

    listed = client.post("/sharpit/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    mcp_names = [t["name"] for t in listed["result"]["tools"]]
    assert mcp_names == surface.expected_mcp_tool_names()
    assert mcp_names[-1] == "get_data_probe"
    assert client.get("/sharpit/api/mcp-server").json()["toolCount"] == len(surface.expected_mcp_tool_names())

    cli = client.get("/sharpit/api/cli").json()
    assert cli["toolCount"] == len(surface.BASE_CLI_COMMANDS) + len(surface.lane_tools())
    assert {t["name"]: t["command"] for t in cli["tools"]} == surface.expected_cli_commands()
    assert surface.expected_cli_commands()["get_data_probe"] == "data probe"

    assert surface.lane_route_paths(handle.context, app) == [p.path for p in _panel_04_routes(handle.context, app)]
    assert surface.lane_route_paths(handle.context, app) == ["/api/data/probe"]
    assert client.get("/sharpit/api/data/probe").json() == {"probe": True}


_IMPORT_WITH_FLAG_ON = """
import sys, types
sys.path.insert(0, sys.argv[1])
from sharpit.engine import panels04
from sharpit.engine.tools04 import data
panels04.IMPLEMENTED["data"] = True
data.TOOLS = (types.SimpleNamespace(name="get_data_probe", panel="data", action=False),)
data.COMMANDS = {"get_data_probe": "data probe"}
import importlib
from sharpit.engine import tools
tools = importlib.reload(tools)  # sharpit imports tools early: re-run its import with data implemented
import surface
rebuilt, commands = surface.catalogue_with_lanes(*panels04.tool_definitions())
print([t.name for t in rebuilt] == [t.name for t in tools.TOOLS] and commands == tools.COMMANDS)
"""


def test_catalogue_rebuild_matches_the_import_time_catalogue_with_the_flag_on() -> None:
    # a fresh interpreter whose tools module is (re-)imported with data implemented: no catalogue patching
    tests_dir = str(Path(__file__).parent)
    done = subprocess.run(
        [sys.executable, "-c", _IMPORT_WITH_FLAG_ON, tests_dir],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.stdout.strip() == "True", done.stderr


@pytest.mark.parametrize(
    "already", [(), ("data", "postgresql")], ids=["none-implemented", "data-postgresql-implemented"]
)
def test_shared_counts_follow_a_flip_of_any_unimplemented_panel(
    monkeypatch: pytest.MonkeyPatch, already: tuple[str, ...]
) -> None:
    for panel_id in already:  # lanes that really implemented their panel before this one
        monkeypatch.setitem(panels04.IMPLEMENTED, panel_id, True)
    plant = surface.plant_unimplemented_panel(monkeypatch)
    probe = f"get_{plant.replace('-', '_')}_probe"
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, mcp_enabled="ON")
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    assert plant not in already
    panel_ids = [p["id"] for p in client.get("/sharpit/api/panels").json()["panels"]]
    assert panel_ids == surface.expected_panel_ids()
    assert plant in panel_ids
    listed = client.post("/sharpit/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    mcp_names = [t["name"] for t in listed["result"]["tools"]]
    assert mcp_names == surface.expected_mcp_tool_names()
    assert probe in mcp_names
    assert client.get("/sharpit/api/mcp-server").json()["toolCount"] == len(surface.expected_mcp_tool_names())
    cli = client.get("/sharpit/api/cli").json()
    assert cli["toolCount"] == len(surface.BASE_CLI_COMMANDS) + len(surface.lane_tools())
    assert {t["name"]: t["command"] for t in cli["tools"]} == surface.expected_cli_commands()
    assert surface.expected_cli_commands()[probe] == f"{plant} probe"
    lane_paths = surface.lane_route_paths(handle.context, app)
    assert lane_paths == [p.path for p in _panel_04_routes(handle.context, app)]
    assert f"/api/{plant}/probe" in lane_paths
    assert client.get(f"/sharpit/api/{plant}/probe").json() == {"probe": True}
