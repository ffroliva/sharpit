from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.panels import Panel
from sharpit.engine.panels04 import IMPLEMENTED

LOCAL = ("127.0.0.1", 50000)
EXPECTED_IDS = {
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
PANEL_IDS = {
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
TOOL_NAMES = {
    "get_data_repositories",
    "get_transactions",
    "get_postgresql_report",
    "get_mysql_report",
    "get_traces",
    "get_security_report",
    "get_security_logs",
    "get_database_advisor_report",
    "get_architecture_report",
    "get_sqlalchemy_statistics",
    "get_fastapi_security",
    "get_fastapi_report",
}


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


def test_unimplemented_panel_gets_have_no_side_effects(no_side_effects: SideEffectGuard) -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False)
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop creates a self-pipe socketpair.
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    client.get("/sharpit/api/panels")
    for panel_id in sorted(PANEL_IDS):
        client.get(f"/sharpit/api/{panel_id}")
