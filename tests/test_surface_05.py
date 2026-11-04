"""An unimplemented 0.5.0 panel has no surface at all, whatever its lane has built (spec §4.4, council M12).

Each of the eight 0.5.0 panels has its flag monkeypatched off (not read from the tree), so the test still means
something after a lane flips its flag on: no panel row, no route, no MCP tool, no CLI command, no settings entry.
"""

from __future__ import annotations

from importlib import import_module

import pytest
from fastapi.testclient import TestClient

import surface
from fastapi import FastAPI
from sharpit import install
from sharpit.engine import mcp, panels04, tools

LOCAL = ("127.0.0.1", 50000)
PANELS_05 = (
    "transactions",
    "mysql",
    "security",
    "security-logs",
    "database-advisor",
    "architecture",
    "fastapi-security",
    "fastapi",
)


@pytest.mark.parametrize("panel", PANELS_05)
def test_unimplemented_panel_has_no_surface_05(panel: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(panels04.IMPLEMENTED, panel, False)
    catalogue, commands = surface.catalogue_with_lanes(*panels04.tool_definitions())
    monkeypatch.setattr(tools, "TOOLS", catalogue)  # as the import builds it with the flag off
    monkeypatch.setattr(tools, "COMMANDS", commands)
    monkeypatch.setattr(mcp, "TOOLS", catalogue)
    own_tools = {t.name for t in import_module(f"sharpit.engine.tools04.{panel.replace('-', '_')}").TOOLS}
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, mcp_enabled="ON", cli_enabled=True)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    panel_ids = [p["id"] for p in client.get("/sharpit/api/panels").json()["panels"]]
    listed = client.post("/sharpit/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    mcp_names = {t["name"] for t in listed["result"]["tools"]}
    cli_names = {t["name"] for t in client.get("/sharpit/api/cli").json()["tools"]}
    lane_paths = surface.lane_route_paths(handle.context)

    assert panel not in panel_ids
    assert client.get(f"/sharpit/api/{panel}").status_code == 404
    assert [p for p in lane_paths if p == f"/api/{panel}" or p.startswith(f"/api/{panel}/")] == []
    assert own_tools & mcp_names == set()
    assert own_tools & cli_names == set()
    fresh = FastAPI()
    with pytest.raises(ValueError, match="Unknown sharpit panel"):
        install(fresh, enabled="ON", show_banner=False, panels={panel: {"enabled": True}})
