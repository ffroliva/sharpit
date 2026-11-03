"""Lane D2 safety rows: the 2.2.0 capture routes and tools read without side effects (AGENTS.md safety model 4).

Base panels (activity, http-exchanges, exceptions): no ``PANEL``; ``GET_ROWS`` declares the new base GET routes.
``get_request_profile`` needs an ``id``: declared for the MCP sweeps.
"""

from __future__ import annotations

from typing import Any

from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from conftest import SideEffectGuard

GET_ROWS = [  # base-route rows (no PANEL): the four 2.2.0 capture GETs
    "/sharpit/api/http-exchanges/routes",
    "/sharpit/api/exceptions/caught",
    "/sharpit/api/activity/journal",
    "/sharpit/api/activity/resources",
]
WRITE_ROWS: list[tuple[str, str]] = []
TOOL_ARGS = {"get_request_profile": lambda _handle: {"id": "no-such-request"}}
TOOL_SEEDS = {"get_request_profile": lambda _ctx: {"id": "no-such-request"}}
NEW_GETS = [
    "/sharpit/api/http-exchanges/routes",
    "/sharpit/api/http-exchanges?route=/owners",
    "/sharpit/api/exceptions/caught",
    "/sharpit/api/activity/journal",
    "/sharpit/api/activity/resources",
    "/sharpit/api/activity?route=/owners&noRequest=true",
]


def _client(state_dir: Any) -> TestClient:
    app = create_app(show_banner=False, state_dir=str(state_dir), mcp_enabled="ON")
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def test_capture_drift_get_no_side_effects(no_side_effects: SideEffectGuard):
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(no_side_effects.state_dir) as client:
        client.get("/owners")
        no_side_effects.block_network()
        statuses = {path: client.get(path).status_code for path in NEW_GETS}
    assert statuses == dict.fromkeys(NEW_GETS, 200), "every 2.2.0 capture GET is served"
    assert no_side_effects.violations == []


def test_new_tools_read_only(no_side_effects: SideEffectGuard):
    from sharpit.engine.tools import TOOLS

    tools = {t.name: t for t in TOOLS}
    added = ("get_http_routes", "get_request_profile")
    assert [name for name in added if name in tools] == list(added), "both 2.2.0 capture tools are listed"
    assert [tools[name].action for name in added] == [False, False], "read tools, never actions"
    no_side_effects.unblock_network()
    with _client(no_side_effects.state_dir) as client:
        client.get("/owners")
        no_side_effects.block_network()
        results = []
        for name, arguments in (("get_http_routes", {"limit": 5}), ("get_request_profile", {"id": "nope"})):
            call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
            results.append(client.post("/sharpit/api/mcp", json=call).json()["result"]["isError"])
    assert results == [False, False]
    assert no_side_effects.violations == []
