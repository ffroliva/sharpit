"""``GET {api}/http-exchanges`` and the ``get_http_exchanges`` MCP tool (spec §7.1, §13.2, §13.3)."""

from __future__ import annotations

from typing import Any

from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.exchanges import DTO_KEYS
from sharpit.engine.guard import PANEL_ACCESS_DENIED
from sharpit.engine.masking import MASK

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/http-exchanges"


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL)


def test_http_exchanges_shape():
    app = FastAPI()
    app.get("/owners")(lambda: {"owners": []})
    install(app, enabled="ON", show_banner=False)
    client = _client(app)
    client.get("/owners?page=2&token=abc", headers={"Authorization": "Bearer secret-value"})
    client.post("/owners")  # 405
    report = client.get(API).json()
    assert list(report) == ["total", "recorded", "hiddenSelf", "exchanges", "page", "unavailableReason"]
    assert (report["total"], report["unavailableReason"]) == (2, None)
    newest, oldest = report["exchanges"]
    assert tuple(oldest) == DTO_KEYS
    assert (newest["method"], newest["status"], newest["statusFamily"]) == ("POST", 405, "4xx")
    assert (oldest["path"], oldest["query"], oldest["uri"]) == (
        "/owners",
        f"page=2&token={MASK}",
        f"/owners?page=2&token={MASK}",
    )
    auth = next(h for h in oldest["requestHeaders"] if h["name"] == "authorization")
    assert auth == {"name": "authorization", "values": [MASK], "masked": True}
    assert oldest["remoteAddress"] == "127.0.0.1"
    assert oldest["traceId"] == oldest["id"]
    assert oldest["responseSizeBytes"] == len(b'{"owners":[]}')
    assert [e["id"] for e in client.get(f"{API}?method=get").json()["exchanges"]] == [oldest["id"]]
    assert [e["id"] for e in client.get(f"{API}?statusClass=4xx").json()["exchanges"]] == [newest["id"]]
    assert client.get(f"{API}?q=page%3D2&limit=1").json()["page"]["matched"] == 1
    assert client.get(f"{API}?offset=x").status_code == 400


def test_panel_disabled_403():
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, panels={"http-exchanges": {"enabled": False}})
    resp = _client(app).get(API)
    assert (resp.status_code, resp.json()) == (
        403,
        {
            "error": PANEL_ACCESS_DENIED,
            "panel": "http-exchanges",
            "reason": "Panel is disabled via SHARPIT_PANELS_HTTP_EXCHANGES_ENABLED=false",
        },
    )


def test_get_http_exchanges_mcp_no_side_effects(no_side_effects: SideEffectGuard):
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(app) as client:
        no_side_effects.block_network()
        client.get("/owners")
        call = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_http_exchanges", "arguments": {"limit": 5}},
        }
        result = client.post("/sharpit/api/mcp", json=call).json()["result"]
    assert result["isError"] is False, result
    payload = result["structuredContent"]
    assert [e["path"] for e in payload["exchanges"]] == ["/owners"]
    assert payload["page"]["limit"] == 5
    assert no_side_effects.violations == []
