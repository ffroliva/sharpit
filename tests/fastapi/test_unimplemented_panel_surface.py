from __future__ import annotations

import asyncio
from importlib import import_module

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.panels import Panel
from sharpit.engine.panels04 import IMPLEMENTED as ALL_IMPLEMENTED

LOCAL = ("127.0.0.1", 50000)
ALL_PANEL_IDS = {
    "data",
    "transactions",
    "postgresql",
    "mysql",
    "traces",
    "security",
    "security-logs",
    "database-advisor",
    "architecture",
    "sqlalchemy-statistics",
    "fastapi-security",
    "fastapi",
}
EXPECTED_IDS = {panel_id for panel_id, implemented in ALL_IMPLEMENTED.items() if not implemented}
IMPLEMENTED = dict.fromkeys(EXPECTED_IDS, False)
PANEL_IDS = set(IMPLEMENTED)
TOOL_NAMES = {
    tool.name
    for panel_id in PANEL_IDS
    for tool in import_module(f"sharpit.engine.tools04.{panel_id.replace('-', '_')}").TOOLS
}


@pytest.fixture(scope="module")
def asgi_loop():
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


def test_panel_implemented_defaults_true() -> None:
    panel = Panel("legacy", "Legacy", False, "/legacy")

    assert panel.implemented is True


def test_unimplemented_panel_has_no_surface() -> None:
    assert set(IMPLEMENTED) == EXPECTED_IDS
    assert set(IMPLEMENTED.values()) == {False}

    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, mcp_enabled="ON")
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    panels = client.get("/sharpit/api/panels").json()["panels"]
    listed_ids = {panel["id"] for panel in panels}
    assert listed_ids.isdisjoint(PANEL_IDS)

    mcp = client.post("/sharpit/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    mcp_names = {tool["name"] for tool in mcp["result"]["tools"]}
    assert mcp_names.isdisjoint(TOOL_NAMES)

    cli = client.get("/sharpit/api/cli").json()
    cli_names = {tool["name"] for tool in cli["tools"]}
    assert cli_names.isdisjoint(TOOL_NAMES)

    for panel_id in sorted(PANEL_IDS):
        response = client.get(f"/sharpit/api/{panel_id}")
        assert response.status_code == 404, panel_id


def test_unimplemented_panel_gets_have_no_side_effects(no_side_effects: SideEffectGuard, asgi_loop) -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False)

    async def check() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            panels_response = await client.get("/sharpit/api/panels")
            assert panels_response.status_code == 200
            for panel_id in sorted(PANEL_IDS):
                response = await client.get(f"/sharpit/api/{panel_id}")
                assert response.status_code == 404, panel_id

    asgi_loop.run_until_complete(check())


def test_all_0_4_panel_flags_are_registered() -> None:
    assert set(ALL_IMPLEMENTED) == ALL_PANEL_IDS
