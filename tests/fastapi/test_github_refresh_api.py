"""``POST {api}/github/refresh`` end to end (W7 Task G2): the real client, token resolver and masker are wired; only
the transport is a recording fake (``client.no_redirect_opener`` is patched to put it under urllib)."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.engine.collectors.github.fakes import FakeTransport, ok
from tests.engine.collectors.github.test_github_client import CANARY, full_routes

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.github import client as client_module
from sharpit.engine.tools import CallContext, call_tool

LOCAL = ("127.0.0.1", 50000)
REFRESH = "/sharpit/api/github/refresh"
REAL_OPENER = client_module.no_redirect_opener


def _repo(root: Path) -> None:
    git = root / ".git"
    git.mkdir()
    (git / "config").write_text('[remote "origin"]\n url = https://github.com/jdubois/boot-ui.git\n')
    (git / "HEAD").write_text("ref: refs/heads/main\n")


def _app(
    monkeypatch: pytest.MonkeyPatch, cwd: Path, routes: dict[str, Any], **options: Any
) -> tuple[TestClient, FakeTransport, Any]:
    monkeypatch.chdir(cwd)
    transport = FakeTransport(routes)
    monkeypatch.setattr(client_module, "no_redirect_opener", lambda: REAL_OPENER(transport))
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL), transport, handle


def _no_process(*_a: Any, **_kw: Any) -> Any:
    raise AssertionError("spawned a process")


@pytest.fixture
def env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "local-token")


def test_refresh_reports_disabled_when_api_refresh_is_disabled(tmp_path: Path, monkeypatch, env_token) -> None:
    # ported: GitHubControllerTests.refreshReportsDisabledWhenApiRefreshIsDisabled
    _repo(tmp_path)
    client, transport, _ = _app(monkeypatch, tmp_path, full_routes(), github_api_enabled=False)
    response = client.post(REFRESH)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DISABLED"
    assert "SHARPIT_GITHUB_API_ENABLED" in body["message"]
    assert isinstance(body["refreshedAt"], int)
    assert transport.requests == []


def test_refresh_delegates_to_client_when_api_enabled(tmp_path: Path, monkeypatch, env_token) -> None:
    # ported: GitHubControllerTests.refreshDelegatesToClientWhenApiEnabled
    _repo(tmp_path)
    client, transport, _ = _app(monkeypatch, tmp_path, full_routes())
    response = client.post(REFRESH)
    assert response.status_code == 200
    assert response.json()["status"] == "CONNECTED"
    assert response.json()["credential"]["source"] == "GITHUB_TOKEN"
    assert transport.paths()[0] == "/rate_limit"
    assert client.get("/sharpit/api/github").json()["status"] == "CONNECTED"


def test_refresh_reports_unavailable_outside_github_repository(tmp_path: Path, monkeypatch, env_token) -> None:
    # ported: GitHubControllerTests.refreshReportsUnavailableOutsideGitHubRepository
    client, transport, _ = _app(monkeypatch, tmp_path, full_routes())
    response = client.post(REFRESH)
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["status"] == "UNAVAILABLE"
    assert transport.requests == []


def test_refresh_surfaces_client_error_report(tmp_path: Path, monkeypatch, env_token) -> None:
    # ported: GitHubControllerTests.refreshSurfacesClientErrorReport
    _repo(tmp_path)
    client, _, _ = _app(monkeypatch, tmp_path, {"/rate_limit": (401, "{}", {})})
    response = client.post(REFRESH)
    assert response.status_code == 200
    assert response.json()["status"] == "ERROR"
    assert response.json()["connected"] is False
    assert response.json()["message"] == "GitHub returned HTTP 401 for rate limits."
    assert client.get("/sharpit/api/github").json()["status"] == "READY"


@pytest.mark.parametrize(
    ("options", "reason"),
    [
        ({"read_only": True}, "sharpit is read-only via SHARPIT_READ_ONLY=true"),
        ({"panels": {"github": {"read_only": True}}}, "Panel is read-only via SHARPIT_PANELS_GITHUB_READ_ONLY=true"),
    ],
    ids=["global", "panel"],
)
def test_github_refresh_refused_read_only_client_not_called(
    tmp_path: Path, monkeypatch, options: dict[str, Any], reason: str
) -> None:
    _repo(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "local-token")
    client, transport, handle = _app(monkeypatch, tmp_path, full_routes(), **options)
    monkeypatch.setattr(subprocess, "Popen", _no_process)
    response = client.post(REFRESH)
    assert response.status_code == 403
    assert response.json()["reason"] == reason
    assert transport.requests == []
    assert handle.context.peek("github-dashboard") is None


def _gh_run(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(["gh"], 0, f"{CANARY}\n".encode(), None)


def _timeout(_request: Any) -> Any:
    raise TimeoutError("timed out")


@pytest.mark.parametrize("source", ["GITHUB_TOKEN", "GH_TOKEN", "gh auth token"])
@pytest.mark.parametrize(
    "rate", [(401, '{"message":"Bad credentials"}', {}), _timeout, ok("{not json")], ids=["401", "timeout", "malformed"]
)
def test_github_token_never_in_output(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture, source: str, rate: Any
) -> None:
    caplog.set_level(logging.DEBUG)
    _repo(tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    if source == "gh auth token":
        monkeypatch.setattr(subprocess, "run", _gh_run)
    else:
        monkeypatch.setenv(source, CANARY)
    client, transport, handle = _app(monkeypatch, tmp_path, full_routes() | {"/rate_limit": rate}, mcp_enabled="ON")
    refreshed = client.post(REFRESH)
    assert refreshed.json()["status"] == "ERROR"
    assert transport.requests[0].get_header("Authorization") == f"Bearer {CANARY}"
    outputs = [
        refreshed.text,
        client.get("/sharpit/api/github").text,
        json.dumps(call_tool(CallContext(handle.context, {}), "get_github_dashboard", {}, via="mcp")),
        json.dumps(call_tool(CallContext(handle.context, {}), "get_github_dashboard", {}, via="cli")),
        caplog.text,
    ]
    assert [CANARY in output for output in outputs] == [False] * len(outputs)


def test_github_token_never_in_output_after_a_cached_refresh(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", CANARY)
    client, _, handle = _app(monkeypatch, tmp_path, full_routes(), mcp_enabled="ON")
    assert client.post(REFRESH).json()["status"] == "CONNECTED"
    cached = json.dumps(call_tool(CallContext(handle.context, {}), "get_github_dashboard", {}, via="mcp"))
    assert '"status": "CONNECTED"' in cached
    assert CANARY not in cached
    assert CANARY not in client.get("/sharpit/api/github").text
