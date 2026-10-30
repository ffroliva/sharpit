"""``POST {api}/mcp``, ``GET {api}/mcp-server`` and ``POST {api}/mcp-server/toggle`` over HTTP (port of BootUI
``BootUiMcpController``, ``McpServerController`` and the HTTP side of ``AbstractMcpConformanceTest``).

Dropped, with reason: ``testPentestingTools*``, ``testMcpAdvisorDetailTools*``, ``testMcpArchitectureDetails*``,
``testMcpTransactionsTool*`` (tools outside the MVP catalogue); ``testMcpToolClientErrorIsReportedInBand...`` is
skipped by BootUI itself unless ``get_exception_detail`` is advertised, which it never is here (the engine case is in
``tests/engine/test_tools.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import __version__, install

LOCAL = ("127.0.0.1", 50000)
MCP = "/sharpit/api/mcp"
PING = {"jsonrpc": "2.0", "id": 1, "method": "ping"}


def _client(tmp_path: Path | None = None, **options: Any) -> TestClient:
    app = FastAPI()
    extra = {"state_dir": str(tmp_path)} if tmp_path else {}
    install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **extra, **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def test_get_mcp_405_allow_post():
    # ported: AbstractMcpConformanceTest.testMcpGetRejectsUnsupportedSseStream
    resp = _client().get(MCP)
    assert resp.status_code == 405
    assert resp.headers["allow"] == "POST"
    assert resp.headers["cache-control"] == "no-store, must-revalidate"


def test_disabled_response_over_http():
    # ported: AbstractMcpConformanceTest.testMcpDisabledShortCircuit, testDisabledMcpNotificationReturns202
    client = _client()
    resp = client.post(MCP, json=PING)
    assert resp.status_code == 200
    assert resp.json()["error"]["code"] == -32000
    note = client.post(MCP, json={"jsonrpc": "2.0", "method": "ping"})
    assert (note.status_code, note.content) == (202, b"")
    assert note.headers["cache-control"] == "no-store, must-revalidate"


def test_toggle_enables_in_memory(tmp_path: Path):
    # adapted: McpServerControllerTests toggle (in memory only, brief ruling)
    client = _client(tmp_path)
    assert client.get("/sharpit/api/mcp-server").json()["enabled"] is False
    on = client.post("/sharpit/api/mcp-server/toggle", json={"enabled": True})
    assert on.status_code == 200
    assert (on.json()["enabled"], on.json()["configuredMode"], on.json()["overridden"]) == (True, "OFF", True)
    assert client.post(MCP, json=PING).json() == {"jsonrpc": "2.0", "id": 1, "result": {}}
    flipped = client.post("/sharpit/api/mcp-server/toggle")  # no body: flip
    assert (flipped.json()["enabled"], flipped.json()["overridden"]) == (False, False)
    assert client.post("/sharpit/api/mcp-server/toggle", json={"enabled": None}).json()["enabled"] is True
    bad = client.post("/sharpit/api/mcp-server/toggle", json={"enabled": "yes"})
    assert bad.status_code == 400
    assert list(tmp_path.iterdir()) == []  # in memory only: nothing written to the state dir
    assert _client(tmp_path).get("/sharpit/api/mcp-server").json()["enabled"] is False  # a new install starts OFF


def test_toggle_obeys_global_read_only():
    # new: brief ruling (toggle obeys global read-only via the guard)
    resp = _client(read_only=True).post("/sharpit/api/mcp-server/toggle", json={"enabled": True})
    assert resp.status_code == 403
    assert resp.json() == {
        "error": "sharpit panel access denied",
        "panel": "mcp-server",
        "reason": "sharpit is read-only via SHARPIT_READ_ONLY=true",
    }


def test_toggle_obeys_panel_read_only():
    # new: brief ruling (toggle obeys per-panel read-only via the guard)
    resp = _client(panels={"mcp-server": {"read_only": True}}).post("/sharpit/api/mcp-server/toggle")
    assert resp.status_code == 403
    assert resp.json()["reason"] == "Panel is read-only via SHARPIT_PANELS_MCP_SERVER_READ_ONLY=true"


def test_mcp_server_status_shape():
    # ported: McpServerController status (McpServerStatus fields, MCP tools only)
    body = _client(mcp_enabled="ON").get("/sharpit/api/mcp-server").json()
    assert list(body) == [
        "enabled", "configuredMode", "overridden", "serverName", "serverVersion", "transport", "endpoint",
        "protocolVersion", "maxResults", "callCount", "totalLatencyMillis", "capacityRefusals", "timeouts",
        "responseLimitRefusals", "toolCount", "tools",
    ]  # fmt: skip
    assert (body["enabled"], body["configuredMode"], body["overridden"]) == (True, "ON", False)
    assert (body["serverName"], body["serverVersion"], body["transport"]) == ("sharpit", __version__, "http")
    assert (body["endpoint"], body["protocolVersion"], body["maxResults"]) == ("/sharpit/api/mcp", "2025-06-18", 200)
    assert body["toolCount"] == 6 and len(body["tools"]) == 6
    assert all(not t["action"] for t in body["tools"])
    assert body["tools"][0] == {
        "name": "get_overview",
        "description": body["tools"][0]["description"],
        "panel": "overview",
        "action": False,
        "panelEnabled": True,
        "panelReadOnly": False,
    }


def test_call_counted_in_status():
    # ported: McpRuntimeStats callCount surfaced by McpServerController
    client = _client(mcp_enabled="ON")
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_overview"}}
    result = client.post(MCP, json=call).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["serverPort"] == 80  # the request's own scope, as GET /overview
    assert client.get("/sharpit/api/mcp-server").json()["callCount"] == 1


def test_mcp_is_behind_the_guard():
    # new: brief ruling (cross-origin POST /mcp gets 403 from the guard)
    client = _client(mcp_enabled="ON")
    resp = client.post(MCP, json=PING, headers={"Origin": "http://evil.example"})
    assert resp.status_code == 403
    assert resp.json() == {"error": "sharpit rejected a cross-site request."}
