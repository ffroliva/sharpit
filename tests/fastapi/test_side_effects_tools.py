"""``get_side_effects`` over MCP and the CLI: advertised only while a side-effects sensor records.

adapted from: AbstractCliConformanceTest.testCliAgentCommandsSayTheAgentIsNotAttachedAndTheOthersAreNotServed
(BootUI v2.5.0), the side-effects tool only.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI, Request
from sharpit import install
from sharpit.engine.sensors import audit
from sharpit.fastapi.adapter import SharpitHandle

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api"
TOOL = "get_side_effects"
SEEDED = "cnry7Q4x"
SECRET_NAME = "AKIAIOSFODNN7EXAMPLE"
UNAVAILABLE_PREFIX = "Tool not available in this application: "


class Hook:
    def __init__(self) -> None:
        self.hooks: list[Any] = []

    def __call__(self, hook: Any) -> None:
        self.hooks.append(hook)

    def fire(self, event: str, *args: Any) -> None:
        for hook in self.hooks:
            hook(event, args)


@pytest.fixture
def hook(monkeypatch: pytest.MonkeyPatch) -> Iterator[Hook]:
    recorder = Hook()
    monkeypatch.setattr(audit.hub, "_add_hook", recorder)
    monkeypatch.setattr(audit.hub, "_installed", False)
    yield recorder
    audit.hub.release()


def _app(tmp_path: Path, hook: Hook, **options: Any) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        mcp_enabled="ON",
        state_dir=str(tmp_path / "state"),
        **options,
    )

    @app.get("/read/{name}")
    def read_path(name: str) -> str:
        hook.fire("open", f"reports/{name}.csv", "r", 0)
        return name

    @app.get("/read")
    def read_named(request: Request) -> str:
        for value in request.query_params.values():
            hook.fire("open", f"reports/{value}.csv", "r", 0)
        return "ok"

    return app, handle


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _rpc(client: TestClient, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return client.post(f"{API}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).json()


def _mcp_names(client: TestClient) -> set[str]:
    return {tool["name"] for tool in _rpc(client, "tools/list")["result"]["tools"]}


def _cli_names(client: TestClient) -> set[str]:
    return {tool["name"] for tool in client.get(f"{API}/cli").json()["tools"]}


def _mcp_call(client: TestClient, **arguments: Any) -> dict[str, Any]:
    answer = _rpc(client, "tools/call", {"name": TOOL, "arguments": arguments})
    assert "error" not in answer, answer
    return answer["result"]["structuredContent"]


def _cli_call(client: TestClient, **arguments: Any) -> dict[str, Any]:
    response = client.post(f"{API}/cli/tools/{TOOL}", json=arguments)
    assert response.status_code == 200, response.text
    return response.json()


def test_get_side_effects_is_listed_only_while_a_side_effects_sensor_records(tmp_path: Path, hook: Hook) -> None:
    # scenario row 15
    bare, _ = _app(tmp_path, hook)
    with _client(bare) as client:
        assert TOOL not in _mcp_names(client)
        answer = _rpc(client, "tools/call", {"name": TOOL, "arguments": {}})
    assert answer["error"]["message"].startswith(f"{UNAVAILABLE_PREFIX}{TOOL}.")
    assert "Requires the sharpit agent" in answer["error"]["message"]

    app, handle = _app(tmp_path, hook, agent_sensors=("files",))
    with _client(app) as client:
        assert TOOL in _mcp_names(client)
        assert TOOL in {tool["name"] for tool in client.get(f"{API}/mcp-server").json()["tools"]}
        lane = handle.context.capture.sensors
        assert lane is not None
        lane.detach()
        assert TOOL not in _mcp_names(client)
        assert "error" in _rpc(client, "tools/call", {"name": TOOL, "arguments": {}})
        lane.attach()
        assert TOOL in _mcp_names(client)
        lane.switch("files", False)
        assert TOOL not in _mcp_names(client)
    handle.uninstall_capture()


def test_the_live_cli_catalogue_lists_side_effects_only_while_a_sensor_records_and_404s_otherwise(
    tmp_path: Path, hook: Hook
) -> None:
    # adapted from: AbstractCliConformanceTest.testCliAgentCommandsSayTheAgentIsNotAttachedAndTheOthersAreNotServed
    bare, _ = _app(tmp_path, hook)
    with _client(bare) as client:
        assert TOOL not in _cli_names(client)
        refused = client.post(f"{API}/cli/tools/{TOOL}", json={})
    assert refused.status_code == 404
    assert TOOL in refused.json()["error"]

    app, handle = _app(tmp_path, hook, agent_sensors=("processes",))
    with _client(app) as client:
        listed = {tool["name"]: tool for tool in client.get(f"{API}/cli").json()["tools"]}
        assert listed[TOOL]["command"] == "side-effects"
        assert listed[TOOL]["schema"] == "QUERY_LIMIT"
        assert listed[TOOL]["panel"] == "side-effects"
        assert client.get(f"{API}/cli").json()["toolCount"] == len(listed)
        assert _cli_call(client)["available"] is True
        lane = handle.context.capture.sensors
        assert lane is not None
        lane.detach()
        assert TOOL not in _cli_names(client)
        assert client.post(f"{API}/cli/tools/{TOOL}", json={}).status_code == 404
    handle.uninstall_capture()


def test_the_bundled_cli_manifest_lists_side_effects_always() -> None:
    manifest = json.loads(
        (Path(__file__).parents[2] / "src" / "sharpit" / "cli" / "tools.json").read_text(encoding="utf-8")
    )
    entry = next(tool for tool in manifest["tools"] if tool["name"] == TOOL)
    assert entry["command"] == "side-effects"
    assert entry["arguments"] == ["query", "limit"]


def _seed(client: TestClient) -> None:
    assert client.get(f"/read/{SEEDED}").status_code == 200
    assert client.get(f"/read?{SECRET_NAME}={SEEDED}x").status_code == 200


def _sinks_app(tmp_path: Path, hook: Hook) -> tuple[FastAPI, SharpitHandle]:
    return _app(
        tmp_path,
        hook,
        agent_sensors=("processes", "files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )


def test_mcp_and_cli_side_effects_answer_the_same_rows(tmp_path: Path, hook: Hook) -> None:
    # scenario row 16
    app, handle = _sinks_app(tmp_path, hook)
    with _client(app) as client:
        _seed(client)
        for arguments in ({}, {"query": "files"}, {"query": "security-sinks", "limit": 1}, {"query": "name"}):
            assert _mcp_call(client, **arguments) == _cli_call(client, **arguments)
        rows = _mcp_call(client, query="security-sinks")["rows"]
    handle.uninstall_capture()
    assert {row["sensor"] for row in rows} == {"security-sinks"}
    assert {row["parameter"] for row in rows} >= {"name"}


def test_the_tool_leaks_neither_a_request_value_nor_a_secret_looking_name(tmp_path: Path, hook: Hook) -> None:
    app, handle = _sinks_app(tmp_path, hook)
    with _client(app) as client:
        _seed(client)
        bodies = [
            json.dumps(call(client, **arguments))
            for call in (_mcp_call, _cli_call)
            for arguments in ({}, {"query": "files"}, {"query": "security-sinks"}, {"query": "name"})
        ]
        asked = _mcp_call(client, query=SEEDED)
    handle.uninstall_capture()
    assert all(SEEDED not in body for body in bodies)
    assert all(SECRET_NAME not in body for body in bodies)
    assert asked["matched"] == 0


def test_the_tool_is_cut_off_with_the_panel_like_any_other(
    tmp_path: Path, hook: Hook, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHARPIT_PANELS_SIDE_EFFECTS_ENABLED", "false")
    app, handle = _sinks_app(tmp_path, hook)
    with _client(app) as client:
        answer = _rpc(client, "tools/call", {"name": TOOL, "arguments": {}})
    handle.uninstall_capture()
    assert answer["result"]["isError"] is True
    assert answer["result"]["content"][0]["text"] == "Panel is disabled via SHARPIT_PANELS_SIDE_EFFECTS_ENABLED=false"


def test_the_limit_argument_is_validated_and_clamped(tmp_path: Path, hook: Hook) -> None:
    app, handle = _sinks_app(tmp_path, hook)
    with _client(app) as client:
        _seed(client)
        assert len(_mcp_call(client, limit=1)["rows"]) == 1
        assert len(_mcp_call(client, limit=10_000)["rows"]) >= 1
        refused = client.post(f"{API}/cli/tools/{TOOL}", json={"limit": -1})
        long_query = _mcp_call(client, query="x\u0007" * 5000)
    handle.uninstall_capture()
    assert refused.status_code == 400
    assert long_query["matched"] == 0
