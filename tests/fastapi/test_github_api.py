from __future__ import annotations

import subprocess
from pathlib import Path

from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient
from starlette.requests import Request

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.tools import CallContext, call_tool
from sharpit.fastapi.routes.github import build_routes


def test_github_controller_dashboard_returns_local_state(tmp_path: Path, monkeypatch, no_side_effects) -> None:
    # ported: GitHubControllerTests.dashboardReturnsLocalRepositoryState
    git = tmp_path / ".git"
    git.mkdir()
    (git / "config").write_text('[remote "origin"]\n url = https://github.com/acme/app.git\n')
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("spawned process"))
    )
    app = FastAPI()
    handle = install(app, show_banner=False, state_dir=str(no_side_effects.state_dir))
    route = build_routes(handle.context)[0]
    request = Request(
        {"type": "http", "method": "GET", "path": "/api/github", "headers": [], "query_string": b"", "path_params": {}}
    )
    response = route.endpoint(request)
    assert response.status_code == 200
    assert response.body
    assert b'"status":"READY"' in response.body


def test_github_controller_dashboard_reports_unavailable(tmp_path: Path, monkeypatch, tmp_state_dir: Path) -> None:
    # ported: GitHubControllerTests.dashboardReportsUnavailableOutsideGitHubRepository
    monkeypatch.chdir(tmp_path)
    app = create_app(show_banner=False, state_dir=str(tmp_state_dir))
    response = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)).get("/sharpit/api/github")
    assert response.status_code == 200
    assert response.json()["status"] == "UNAVAILABLE"


def test_github_reads_spawn_no_process_and_mcp_is_read_only(tmp_path: Path, monkeypatch, no_side_effects) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("spawned process"))
    )
    app = FastAPI()
    handle = install(app, show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    request = Request(
        {"type": "http", "method": "GET", "path": "/api/github", "headers": [], "query_string": b"", "path_params": {}}
    )
    route = build_routes(handle.context)[0]
    response = route.endpoint(request)
    assert response.status_code == 200
    assert b'"status":"UNAVAILABLE"' in response.body
    result = call_tool(CallContext(handle.context, {}), "get_github_dashboard", {}, via="mcp")
    assert result["status"] == "UNAVAILABLE"
