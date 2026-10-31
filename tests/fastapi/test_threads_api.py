"""Threads endpoint (F9, spec §7.9, §13.2): GET on the loop reads tasks directly; the MCP tool hands off to the loop."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.masking import MASK

LOCAL = ("127.0.0.1", 50000)
URL = "/sharpit/api/threads"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0aHJlYWRzIn0.c2lnbmF0dXJlLWJ5dGVz"


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _rpc(client: TestClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return client.post("/sharpit/api/mcp", json=call).json()["result"]


def _stuck_app() -> tuple[FastAPI, threading.Event, asyncio.Event]:
    """A host route that parks its request task until the test releases it."""
    app = FastAPI()
    entered = threading.Event()
    release = asyncio.Event()

    @app.get("/reset/{token}")
    async def reset(token: str) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        entered.set()
        await release.wait()
        return {"ok": token[:0]}

    install(app, enabled="ON", show_banner=False, mcp_enabled="ON")
    return app, entered, release


def test_task_request_path_masked():
    app, entered, release = _stuck_app()
    with _client(app) as client:
        host = threading.Thread(target=lambda: client.get(f"/reset/{JWT}"), daemon=True)
        host.start()
        try:
            assert entered.wait(5)
            resp = client.get(URL)
        finally:
            client.portal.call(release.set)  # pyright: ignore[reportOptionalMemberAccess]
            host.join(5)
    assert resp.status_code == 200
    assert JWT not in resp.text
    rows = [t for t in resp.json()["tasks"] if t["request"] is not None and t["request"]["path"].startswith("/reset/")]
    assert rows
    assert rows[0]["request"]["path"] == f"/reset/{MASK}"
    assert "reset" in [s.split(" (", 1)[0].rsplit(".", 1)[-1] for s in rows[0]["stackTrace"]]


def test_threads_get_shape_and_filters():
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    with _client(app) as client:
        body = client.get(f"{URL}?state=RUNNABLE&limit=1").json()
        assert body["warnings"] == []
        assert body["page"]["limit"] == 1
        assert all(r["state"] == "RUNNABLE" for r in body["threads"])
        assert client.get(f"{URL}?limit=x").status_code == 400


def test_get_threads_mcp_no_side_effects(no_side_effects: SideEffectGuard):
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(app) as client:
        client.get("/owners")
        no_side_effects.block_network()
        before = threading.active_count()
        result = _rpc(client, "get_threads", {"limit": 5})
    assert result["isError"] is False
    content = result["structuredContent"]
    assert content["warnings"] == []
    assert len(content["threads"]) <= 5
    assert threading.active_count() <= before + 1  # the ToolGate worker at most; the read itself starts no thread
    assert no_side_effects.violations == []
