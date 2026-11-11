"""W6 floor over MCP and the CLI: get_agent_status says NOT_ATTACHED, the sensor tools are not advertised and say why.

ported: AbstractMcpConformanceTest.testMcpAgentToolsSayTheAgentIsNotAttachedAndTheOthersAreNotAdvertised and
AbstractCliConformanceTest.testCliAgentSensorSwitchesRejectMissingAndUnsupportedIds (BootUI 2.3.0 conformance).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install

LOCAL = ("127.0.0.1", 50000)
# JavaAgentPresence.AGENT_SENSOR_TOOLS
AGENT_SENSOR_TOOLS = [
    "get_code_inventory",
    "get_code_paths",
    "start_method_probe",
    "get_method_probe",
    "get_side_effects",
]
UNAVAILABLE_PREFIX = "Tool not available in this application: "


def _client(**options: Any) -> TestClient:
    app = FastAPI()
    install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, "mcp_enabled": "ON", **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _rpc(client: TestClient, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return client.post(
        "/sharpit/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    ).json()


def test_mcp_advertises_get_agent_status_and_not_the_sensor_tools() -> None:
    advertised = {tool["name"] for tool in _rpc(_client(), "tools/list")["result"]["tools"]}
    assert "get_agent_status" in advertised
    assert advertised.isdisjoint(AGENT_SENSOR_TOOLS)


def test_mcp_get_agent_status_says_not_attached() -> None:
    answer = _rpc(_client(), "tools/call", {"name": "get_agent_status", "arguments": {}})
    status = answer.get("result", {}).get("structuredContent", {})
    assert status.get("state") == "NOT_ATTACHED", answer
    assert status["reason"].strip()
    assert status["sensors"] == []


@pytest.mark.parametrize("tool", AGENT_SENSOR_TOOLS)
def test_mcp_sensor_tool_says_its_panel_needs_the_agent(tool: str) -> None:
    answer = _rpc(_client(), "tools/call", {"name": tool, "arguments": {}})
    assert "result" not in answer
    assert answer["error"]["code"] == -32602
    assert answer["error"]["message"].startswith(f"{UNAVAILABLE_PREFIX}{tool}."), answer
    assert "Requires the sharpit agent" in answer["error"]["message"]


def test_mcp_sensor_tool_of_a_disabled_panel_gets_the_disabled_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHARPIT_PANELS_CODE_PATHS_ENABLED", "false")
    answer = _rpc(_client(), "tools/call", {"name": "get_code_paths", "arguments": {}})
    result = answer.get("result", {})
    assert result.get("isError") is True, answer
    assert result["content"][0]["text"] == "Panel is disabled via SHARPIT_PANELS_CODE_PATHS_ENABLED=false"


def test_cli_lists_agent_tools_and_not_the_sensor_tools() -> None:
    listed = {tool["name"]: tool for tool in _client().get("/sharpit/api/cli").json()["tools"]}
    assert "get_agent_status" in listed
    assert listed["get_agent_status"]["command"] == "agent status"
    assert listed["get_agent_status"]["schema"] == "QUERY"
    assert listed["enable_agent_sensor"]["command"] == "agent sensor enable"
    assert listed["disable_agent_sensor"]["command"] == "agent sensor disable"
    assert listed["enable_agent_sensor"]["action"] is True
    assert listed["enable_agent_sensor"]["panel"] == "java-agent"
    assert set(listed).isdisjoint(AGENT_SENSOR_TOOLS)


@pytest.mark.parametrize("tool", AGENT_SENSOR_TOOLS)
def test_cli_sensor_tool_is_404_naming_it(tool: str) -> None:
    resp = _client().post(f"/sharpit/api/cli/tools/{tool}", json={})
    assert resp.status_code == 404
    assert tool in resp.json()["error"]


def test_cli_get_agent_status_says_not_attached() -> None:
    resp = _client().post("/sharpit/api/cli/tools/get_agent_status", json={})
    assert resp.status_code == 200
    assert resp.json()["state"] == "NOT_ATTACHED"


@pytest.mark.parametrize("tool", ["enable_agent_sensor", "disable_agent_sensor"])
@pytest.mark.parametrize(
    ("args", "status", "fragment"),
    [({}, 400, "id"), ({"id": "executors"}, 400, "cannot be switched"), ({"id": "files"}, 409, "not armed")],
    ids=["missing", "unswitchable", "not-armed"],
)
def test_cli_sensor_switch_refusals(tool: str, args: dict[str, Any], status: int, fragment: str) -> None:
    resp = _client().post(f"/sharpit/api/cli/tools/{tool}", json=args)
    assert resp.status_code == status
    assert fragment in resp.json()["error"]
