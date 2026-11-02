"""Proof that the shared surface expectations (tests/surface.py) follow a 0.4 flag flip with a planted tool."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import surface
from fastapi import FastAPI
from sharpit import install
from sharpit.engine import panels04
from sharpit.fastapi.routes import _panel_04_routes

LOCAL = ("127.0.0.1", 50000)
NONE_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


_IMPORT_WITH_FLAG_ON = """
import importlib, sys, types
sys.path.insert(0, sys.argv[1])
from sharpit.engine import panels04
plant = next((p for p in panels04.PANEL_04_IDS if not panels04.IMPLEMENTED[p]), None)
if plant is None:
    print("True")  # every panel implemented: the import-time catalogue already holds every lane tool
    raise SystemExit
module = importlib.import_module("sharpit.engine.tools04." + plant.replace("-", "_"))
panels04.IMPLEMENTED[plant] = True
name = "get_" + plant.replace("-", "_") + "_probe"
module.TOOLS = (*module.TOOLS, types.SimpleNamespace(name=name, panel=plant, action=False))
module.COMMANDS = {**getattr(module, "COMMANDS", {}), name: plant + " probe"}
from sharpit.engine import tools
tools = importlib.reload(tools)  # sharpit imports tools early: re-run its import with the plant implemented
import surface
rebuilt, commands = surface.catalogue_with_lanes(*panels04.tool_definitions())
print([t.name for t in rebuilt] == [t.name for t in tools.TOOLS] and commands == tools.COMMANDS)
"""


def test_catalogue_rebuild_matches_the_import_time_catalogue_with_the_flag_on() -> None:
    # a fresh interpreter whose tools module is (re-)imported with one more panel implemented: no catalogue patching
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
