"""Security-sinks safety: a seeded request value that reaches a path, a command and an error leaks nowhere."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

import safety
from conftest import _PATH_PARAMS
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.sensors import audit
from sharpit.engine.tools import TOOLS
from sharpit.fastapi.adapter import SharpitMount
from sharpit.settings_registry import JOURNAL_SOURCES

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api"
CANARY = "canary-sink-value"
# Routes, tools and journal sources that show the request's own exchange (query string or path).
EXCLUDED_ROUTES = frozenset(
    {
        "/sharpit/api/http-exchanges",
        "/sharpit/api/activity/request/0123456789abcdef",
    }
)
EXCLUDED_TOOLS = frozenset(
    {
        "get_http_exchanges",
        "get_request_profile",
    }
)
EXCLUDED_JOURNAL_SOURCES = frozenset({"http"})


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


def _console_get_paths(app: FastAPI) -> list[str]:
    mount = next(r for r in app.router.routes if isinstance(r, SharpitMount))
    lanes = safety.load()
    paths = ["/sharpit"]
    for route in mount.routes:
        if isinstance(route, Route) and "GET" in (route.methods or ()):
            samples = safety.sample_params("/sharpit" + route.path_format, lanes, _PATH_PARAMS)
            params = {name: samples[name] for name in route.param_convertors}
            paths.append("/sharpit" + route.path_format.format(**params))
    return paths


@pytest.mark.parametrize("exposure", ("MASKED", "METADATA_ONLY", "FULL"))
def test_a_seeded_value_reaches_no_route_log_or_error(tmp_path: Path, hook: Hook, exposure: str) -> None:
    app = FastAPI()

    @app.get("/work")
    def work(file: str) -> str:
        hook.fire("open", f"reports/{file}.csv", "r", 0)
        hook.fire("subprocess.Popen", None, [file, f"--in={file}"], None, None)
        raise FileNotFoundError(2, "No such file or directory", f"reports/{file}.csv")

    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        state_dir=str(tmp_path / "state"),
        mcp_enabled="ON",
        stream_max_seconds=0.05,
        agent_sensors=("processes", "files", "security-sinks"),
        agent_security_sinks_request_values=True,
        expose_values=exposure,
    )
    paths = _console_get_paths(app)
    with TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False) as client:
        resp = client.get(f"/work?file={CANARY}")
        assert resp.status_code == 500
        groups = client.get(f"{API}/exceptions").json()["groups"]
        assert len(groups) == 1
        gid = groups[0]["id"]
        checked_paths = [p for p in (*paths, f"{API}/exceptions/{gid}") if p not in EXCLUDED_ROUTES]
        leaked_routes = [p for p in checked_paths if CANARY in client.get(p).text]
        leaked_tools: list[str] = []
        for tool in TOOLS:
            if tool.action or tool.name in EXCLUDED_TOOLS:
                continue
            args = {"id": gid} if tool.name == "get_exception_detail" else {}
            call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool.name, "arguments": args}}
            if CANARY in client.post(f"{API}/mcp", json=call).text:
                leaked_tools.append(tool.name)
    handle.uninstall_capture()
    journal = handle.context.capture.journal
    assert journal is not None
    leaked_sources = [
        source
        for source in JOURNAL_SOURCES
        if source not in EXCLUDED_JOURNAL_SOURCES and CANARY in json.dumps(journal.records(source))
    ]
    assert leaked_routes == []
    assert leaked_tools == []
    assert leaked_sources == []
    assert len(journal.records("security-sinks")) == 3
