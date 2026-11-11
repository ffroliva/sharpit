from __future__ import annotations

import builtins
import json
import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.agentsessions.store import display_session_dir
from sharpit.engine.tools import CallContext
from sharpit.engine.tools04.copilot import TOOLS as COPILOT_TOOLS
from sharpit.settings import load_settings


def test_sessions_panel_disabled_reads_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("SHARPIT_PANELS_COPILOT_ENABLED", "false")
    session_file = tmp_path / "abc.json"
    session_file.write_text('{"events":[]}', encoding="utf-8")

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    real_open = builtins.open
    real_scandir = os.scandir
    accessed = False

    def spy_open(*args, **kwargs):
        nonlocal accessed
        if str(tmp_path) in str(args[0]):
            accessed = True
        return real_open(*args, **kwargs)

    def spy_scandir(*args, **kwargs):
        nonlocal accessed
        if args and str(tmp_path) in str(args[0]):
            accessed = True
        return real_scandir(*args, **kwargs)

    with patch("builtins.open", side_effect=spy_open), patch("os.scandir", side_effect=spy_scandir):
        resp = client.get("/sharpit/api/copilot/sessions")
        assert resp.status_code == 403
        resp = client.get("/sharpit/api/copilot/dashboard")
        assert resp.status_code == 403
        assert not accessed


def test_sessions_returns_unavailable_when_directory_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: CopilotControllerTests.sessionsReturnsUnavailableWhenDirectoryMissing
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(missing))

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/copilot/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["total"] == 0
    assert f"Copilot CLI session directory not found at {display_session_dir(missing)}" in data["unavailableReason"]


def test_dashboard_returns_unavailable_when_directory_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: CopilotControllerTests.dashboardReturnsUnavailableWhenDirectoryMissing
    missing = tmp_path / "missing"
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(missing))

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/copilot/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["sessionCount"] == 0
    assert len(data["activityBuckets"]) == 0


def test_sessions_and_dashboard_use_home_relative_session_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ported: CopilotControllerTests.sessionsAndDashboardUseHomeRelativeSessionDirectory
    session_state_dir = tmp_path / ".copilot" / "session-state"
    session_state_dir.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("SHARPIT_COPILOT_SESSION_STATE_DIR", raising=False)

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/copilot/sessions")
    assert resp.status_code == 200
    assert resp.json()["sessionStateDir"] == "~/.copilot/session-state"

    resp = client.get("/sharpit/api/copilot/dashboard")
    assert resp.status_code == 200
    assert resp.json()["sessionStateDir"] == "~/.copilot/session-state"


def test_sessions_lists_parsed_sessions_with_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: CopilotControllerTests.sessionsListsParsedSessionsWithCounts
    session_file = tmp_path / "abc123.json"
    session_file.write_text(
        """{
          "model": "gpt-4o",
          "cwd": "/work",
          "events": [
            {"type":"tool_call","tool":"apply_patch","timestamp":1700000000,"success":true,"path":"/work/App.java"},
            {"type":"tool_call","tool":"mcp.fetch","timestamp":1700000001,"success":false,"url":"https://example.com/x"},
            {"type":"tool_call","tool":"grep","timestamp":1700000002,"success":true}
          ]
        }""",
        encoding="utf-8",
    )
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/copilot/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["total"] == 1
    assert data["returned"] == 1
    assert data["sessions"][0]["id"] == "abc123"
    assert data["sessions"][0]["model"] == "gpt-4o"
    assert data["sessions"][0]["workingDirectory"] == "/work"
    assert data["sessions"][0]["eventCount"] == 3
    assert data["sessions"][0]["errorCount"] == 1


def test_session_detail_returns_404_for_unknown_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: CopilotControllerTests.sessionDetailReturns404ForUnknownId
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/copilot/sessions/unknown")
    assert resp.status_code == 404
    assert resp.content == b""


def test_raw_reveal_returns_404_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: CopilotControllerTests.rawRevealReturns404WhenDisabled
    (tmp_path / "s1.json").write_text('{"events":[{"type":"t","tool":"apply_patch","timestamp":1}]}', encoding="utf-8")
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("SHARPIT_COPILOT_ALLOW_RAW_REVEAL", "false")

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/copilot/sessions/s1/events/t0-i0-apply_patch/raw")
    assert resp.status_code == 404
    assert resp.content == b""


def test_raw_reveal_respects_metadata_only_exposure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: CopilotControllerTests.rawRevealRespectsMetadataOnlyExposure
    (tmp_path / "s1.json").write_text('{"events":[{"type":"t","tool":"apply_patch","timestamp":1}]}', encoding="utf-8")
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("SHARPIT_EXPOSE_VALUES", "METADATA_ONLY")

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/copilot/sessions/s1/events/t0-i0-apply_patch/raw")
    assert resp.status_code == 404
    assert resp.content == b""


def test_copilot_raw_reveal_default_off() -> None:
    settings = load_settings({}, {})
    assert settings.copilot_allow_raw_reveal is False


def test_copilot_dashboard_golden_shape_23(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "absent"
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(missing))

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/copilot/dashboard")
    assert resp.status_code == 200
    data = resp.json()

    golden_path = Path(__file__).parents[1] / "fixtures" / "bootui" / "2.3.0" / "copilot" / "dashboard.captured.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))

    assert set(data.keys()) == set(golden.keys())
    assert len(data.keys()) == 21
    assert data["available"] == golden["available"]
    assert data["sessionCount"] == golden["sessionCount"]
    assert data["eventCount"] == golden["eventCount"]
    assert data["turnCount"] == golden["turnCount"]
    assert data["errorCount"] == golden["errorCount"]
    assert data["activeLast24Hours"] == golden["activeLast24Hours"]
    assert data["activeLast7Days"] == golden["activeLast7Days"]
    assert data["sessionsWithSchemaDrift"] == golden["sessionsWithSchemaDrift"]
    assert data["totalInputTokens"] == golden["totalInputTokens"]
    assert data["totalOutputTokens"] == golden["totalOutputTokens"]
    assert data["lastActivityEpochMillis"] == golden["lastActivityEpochMillis"]


def test_session_tools_default_limit_and_query(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for i in range(15):
        (tmp_path / f"session_{i:02d}.json").write_text(
            json.dumps(
                {
                    "model": "gpt-4o" if i % 2 == 0 else "claude-3-5",
                    "cwd": f"/work/{i}",
                    "status": "active" if i < 10 else "completed",
                    "events": [{"type": "t", "tool": "grep", "timestamp": 1700000000 + i}],
                }
            ),
            encoding="utf-8",
        )
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    # CLI invoke
    cli_resp = client.post("/sharpit/api/cli/tools/get_copilot_sessions", json={})
    assert cli_resp.status_code == 200
    cli_data = cli_resp.json()
    assert cli_data["available"] is True
    assert cli_data["total"] == 15
    assert cli_data["returned"] == 10
    assert len(cli_data["sessions"]) == 10
    assert cli_data["page"]["limit"] == 10

    # Query filter via CLI
    cli_filtered = client.post(
        "/sharpit/api/cli/tools/get_copilot_sessions",
        json={"query": "claude-3-5", "limit": 5},
    ).json()
    assert cli_filtered["returned"] == 5
    for s in cli_filtered["sessions"]:
        assert s["model"] == "claude-3-5"

    # MCP tool via CallContext
    tool = next(t for t in COPILOT_TOOLS if t.name == "get_copilot_sessions")
    call = CallContext(handle.context, {})
    mcp_data = tool.handler(call, {"query": "claude-3-5", "limit": 5})
    assert mcp_data == cli_filtered


def test_sessions_reads_start_no_sharpit_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "s1.json").write_text('{"events":[{"type":"t","tool":"apply_patch","timestamp":1}]}', encoding="utf-8")
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("SHARPIT_STREAM_MAX_SECONDS", "0.05s")

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    real_start = threading.Thread.start
    started_sharpit_threads: list[str] = []

    def spy_start(self, *args, **kwargs):
        target = getattr(self, "_target", None)
        target_mod = getattr(target, "__module__", "")
        run_mod = getattr(self.run, "__module__", "")
        if target_mod.startswith("sharpit.") or run_mod.startswith("sharpit."):
            started_sharpit_threads.append(f"{self.name}: target={target_mod}, run={run_mod}")
        return real_start(self, *args, **kwargs)

    with patch.object(threading.Thread, "start", spy_start):
        resp = client.get("/sharpit/api/copilot/sessions")
        assert resp.status_code == 200
        client.get("/sharpit/api/copilot/dashboard")
        client.get("/sharpit/api/copilot/sessions/s1")
        client.get("/sharpit/api/copilot/sessions/s1/events")
        client.get("/sharpit/api/copilot/stream")

        client.get("/sharpit/api/claude-code/sessions")
        client.get("/sharpit/api/claude-code/dashboard")
        client.get("/sharpit/api/claude-code/sessions/s1")
        client.get("/sharpit/api/claude-code/sessions/s1/events")
        client.get("/sharpit/api/claude-code/stream")

        call = CallContext(handle.context, {})
        tool = next(t for t in COPILOT_TOOLS if t.name == "get_copilot_sessions")
        tool.handler(call, {"limit": 5})

    assert started_sharpit_threads == []


def test_copilot_enabled_off_disables_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "s1.json").write_text('{"events":[{"type":"t"}]}', encoding="utf-8")
    monkeypatch.setenv("SHARPIT_COPILOT_SESSION_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("SHARPIT_COPILOT_ENABLED", "OFF")

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/copilot/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["unavailableReason"] == "Copilot panel is disabled via configuration"

    resp_dash = client.get("/sharpit/api/copilot/dashboard")
    assert resp_dash.status_code == 200
    data_dash = resp_dash.json()
    assert data_dash["available"] is False
    assert data_dash["unavailableReason"] == "Copilot panel is disabled via configuration"

    panels_resp = client.get("/sharpit/api/panels")
    assert panels_resp.status_code == 200
    panels_data = panels_resp.json()
    assert panels_data["panels"]["copilot"]["available"] is False
    assert panels_data["panels"]["copilot"]["unavailableReason"] == "Copilot panel is disabled via configuration"
