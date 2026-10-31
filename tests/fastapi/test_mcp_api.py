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
    toggle = "/sharpit/api/mcp-server/toggle"
    bad_body = {"error": "Request body must be a JSON object with a boolean or null 'enabled'"}
    for raw in (b'{"enabled": "yes"}', b"{not json", b"[true]"):  # BootUI: Spring binding refuses these with 400
        bad = client.post(toggle, content=raw, headers={"content-type": "application/json"})
        assert (bad.status_code, bad.json()) == (400, bad_body), raw
    assert client.get("/sharpit/api/mcp-server").json()["enabled"] is True  # refused bodies change nothing
    assert client.post(toggle, content=b"").json()["enabled"] is False  # empty body: flip
    assert client.post(toggle, json={}).json()["enabled"] is True  # missing 'enabled': flip
    null = client.post(toggle, content=b"null", headers={"content-type": "application/json"})
    assert (null.status_code, null.json()["enabled"]) == (200, False)  # BootUI: request == null flips
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
    assert body["toolCount"] == 12 and len(body["tools"]) == 12  # Tasks 2-6 add get_http_exchanges, get_log_tail,
    # get_exceptions, get_exception_detail, get_sql_traces and get_live_activity (clear/pause/resume are CLI-only)
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


TOO_LARGE = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Request payload exceeds limit"}}


def test_mcp_payload_cap_by_content_length_and_by_stream():
    # new: review ruling (413 before the body is read when Content-Length is over the cap; otherwise a bounded read)
    client = _client(mcp_enabled="ON", mcp_max_payload_bytes=64)
    big = {**PING, "pad": "x" * 100}
    declared = client.post(MCP, json=big)
    assert (declared.status_code, declared.json()) == (413, TOO_LARGE)
    chunked = client.post(MCP, content=iter([b'{"jsonrpc":"2.0",', b'"pad":"' + b"x" * 100 + b'"}']),
                          headers={"content-type": "application/json"})  # fmt: skip
    assert "content-length" not in chunked.request.headers
    assert (chunked.status_code, chunked.json()) == (413, TOO_LARGE)
    assert client.post(MCP, json=PING).json() == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_toggle_body_is_bounded():
    # new: review ruling (bounded read, MCP payload cap)
    client = _client(mcp_max_payload_bytes=16)
    resp = client.post("/sharpit/api/mcp-server/toggle", json={"enabled": True, "pad": "x" * 100})
    assert (resp.status_code, resp.json()) == (413, {"error": "Request payload exceeds limit"})
    assert client.get("/sharpit/api/mcp-server").json()["enabled"] is False


def test_toggle_body_has_its_own_small_cap():
    # Task P1: per-endpoint caps; a toggle body is tiny, so it never gets the MCP payload's megabyte
    client = _client()
    resp = client.post("/sharpit/api/mcp-server/toggle", json={"enabled": True, "pad": "x" * 5000})
    assert (resp.status_code, resp.json()) == (413, {"error": "Request payload exceeds limit"})
    assert client.get("/sharpit/api/mcp-server").json()["enabled"] is False


def test_deeply_nested_json_is_a_parse_error_not_a_500():
    # code review #6: json.loads raises RecursionError, not ValueError, on deep nesting
    client = _client()
    deep, small = b"[" * 100_000, b"[" * 4000  # small stays under the 4 KiB toggle/logger cap
    headers = {"content-type": "application/json"}
    rpc = client.post(MCP, content=deep, headers=headers)
    assert (rpc.status_code, rpc.json()["error"]["code"]) == (400, -32700)
    for path, body in (
        ("/sharpit/api/mcp-server/toggle", small),
        ("/sharpit/api/loggers/deep.json", small),
        ("/sharpit/api/cli/tools/get_overview", deep),
    ):
        resp = client.post(path, content=body, headers=headers)
        assert (resp.status_code, "error" in resp.json()) == (400, True), path
