from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import OpenStream
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.agentsessions import Layout, session_store
from sharpit.engine.collectors.agentsessions.store import display_session_dir
from sharpit.engine.tools import TOOLS, CallContext


def write_claude_session(file: Path) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        '{"type":"user","uuid":"u1","timestamp":"2026-05-28T10:00:00Z","cwd":"/work/app",'
        '"message":{"role":"user","content":"SECRET_PROMPT"}}\n'
        '{"type":"assistant","uuid":"a1","parentUuid":"u1","timestamp":"2026-05-28T10:15:00Z","cwd":"/work/app",'
        '"message":{"role":"assistant","model":"claude-sonnet-4-20250514",'
        '"usage":{"input_tokens":100,"output_tokens":20,"cache_creation_input_tokens":5,'
        '"cache_read_input_tokens":30},"content":[{"type":"text","text":"SECRET_TEXT"},'
        '{"type":"tool_use","id":"toolu_1","name":"Bash",'
        '"input":{"command":"echo SECRET_COMMAND","file_path":"/tmp/SECRET_FILE.txt"}}]}}\n'
        '{"type":"user","uuid":"u2","parentUuid":"a1","timestamp":"2026-05-28T11:00:00Z","cwd":"/work/app",'
        '"message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_1",'
        '"content":"SECRET_OUTPUT","is_error":true}]}}\n',
        encoding="utf-8",
    )


# ported: ClaudeCodeControllerTests.sessionsReturnsUnavailableWhenDirectoryMissing
def test_claude_code_sessions_returns_unavailable_when_directory_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(missing))

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/claude-code/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["unavailableReason"] == f"Claude Code session directory not found at {display_session_dir(missing)}"
    assert data["total"] == 0


# ported: ClaudeCodeControllerTests.sessionsListsProjectJsonlWithSanitizedToolEvents
def test_claude_code_sessions_lists_project_jsonl_with_sanitized_tool_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_claude_session(tmp_path / "project-one" / "session-one.jsonl")
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/claude-code/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["total"] == 1
    session = data["sessions"][0]
    assert session["id"] == "session-one"
    assert session["filename"] == "project-one/session-one.jsonl"
    assert session["model"] == "claude-sonnet-4-20250514"
    assert session["workingDirectory"] == "/work/app"
    assert session["eventCount"] == 2
    assert session["inputTokens"] == 135
    assert session["outputTokens"] == 20
    assert session["errorCount"] == 1


# ported: ClaudeCodeControllerTests.refreshParsesOnlyMostRecentlyModifiedProjectSessions
def test_claude_code_refresh_parses_only_most_recently_modified_project_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(5):
        p = tmp_path / f"project-{i}" / f"session-{i}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f'{{"type":"assistant","timestamp":"2026-05-28T10:0{i}:00Z","message":{{"content":[{{"type":"tool_use","id":"t{i}","name":"Bash"}}]}}}}\n',
            encoding="utf-8",
        )
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_MAX_PARSED_SESSIONS", "2")

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/claude-code/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["sessions"]) == 2


# ported: ClaudeCodeControllerTests.dashboardAggregatesIsoTimestampActivity
def test_claude_code_dashboard_aggregates_iso_timestamp_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_claude_session(tmp_path / "project-one" / "session-one.jsonl")
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    # Fixed clock at 2026-05-28T12:00:00Z (1779969600000)
    store = session_store(handle.context, Layout.CLAUDE_CODE)
    store.clock = 1779969600000

    resp = client.get("/sharpit/api/claude-code/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["sessionCount"] == 1
    assert data["eventCount"] == 2
    assert data["totalInputTokens"] == 135
    assert data["totalOutputTokens"] == 20
    assert data["errorCount"] == 1
    assert data["activeLast24Hours"] == 1
    assert data["activityBuckets"][21]["eventCount"] == 1
    assert data["activityBuckets"][21]["inputTokens"] == 135
    assert data["activityBuckets"][21]["outputTokens"] == 20
    assert data["activityBuckets"][22]["eventCount"] == 1
    assert data["dailyActivityBuckets"][6]["eventCount"] == 2
    assert data["dailyActivityBuckets"][6]["inputTokens"] == 135
    assert data["dailyActivityBuckets"][6]["outputTokens"] == 20


# ported: ClaudeCodeControllerTests.rawRevealIsDisabledByDefault
def test_claude_code_raw_reveal_fails_closed_404_route_not_masking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_claude_session(tmp_path / "project-one" / "session-one.jsonl")
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/claude-code/sessions/session-one/events/toolu_1/raw")
    assert resp.status_code == 404


# ported: ClaudeCodeControllerTests.rawRevealRespectsMetadataOnlyExposure
def test_claude_code_raw_reveal_respects_metadata_only_exposure_fails_closed_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_claude_session(tmp_path / "project-one" / "session-one.jsonl")
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_ALLOW_RAW_REVEAL", "true")
    monkeypatch.setenv("SHARPIT_EXPOSE_VALUES", "METADATA_ONLY")

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/claude-code/sessions/session-one/events/toolu_1/raw")
    assert resp.status_code == 404


# ported: ClaudeCodeControllerTests.eventsFilterByCategory
def test_claude_code_events_filter_by_category(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_claude_session(tmp_path / "project-one" / "session-one.jsonl")
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/claude-code/sessions/session-one/events?category=SHELL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["events"][0]["toolName"] == "Bash"


# ported: ClaudeCodeControllerTests.summaryAndSystemLinesDoNotProducePhantomEvents
def test_claude_code_summary_and_system_lines_do_not_produce_phantom_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "project-one" / "session-quiet.jsonl"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        '{"type":"summary","uuid":"s1","summary":"SECRET_COMPACT_SUMMARY","leafUuid":"a1"}\n'
        '{"type":"system","uuid":"sys1","subtype":"compact_boundary","timestamp":"2026-05-28T09:00:00Z","compactMetadata":{"trigger":"auto","preTokens":42000}}\n'
        '{"type":"system","uuid":"sys2","subtype":"turn_duration","parentUuid":"a1","timestamp":"2026-05-28T09:00:01Z","durationMs":1234}\n'
        '{"type":"user","uuid":"u1","timestamp":"2026-05-28T10:00:00Z","cwd":"/work/app","message":{"role":"user","content":"SECRET_PROMPT"}}\n'
        '{"type":"assistant","uuid":"a2","parentUuid":"u1","timestamp":"2026-05-28T10:00:01Z","message":{"role":"assistant","model":"claude-sonnet-4-20250514","content":[{"type":"tool_use","id":"toolu_2","name":"Read","input":{"file_path":"/tmp/SECRET.txt"}}]}}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)

    store = session_store(handle.context, Layout.CLAUDE_CODE)
    detail = store.detail("session-quiet")
    assert detail is not None
    assert len(detail["recentEvents"]) == 1
    assert detail["recentEvents"][0]["toolName"] == "Read"
    detail_str = json.dumps(detail)
    assert "SECRET_COMPACT_SUMMARY" not in detail_str
    assert "SECRET_PROMPT" not in detail_str
    assert "compact_boundary" not in detail_str
    assert "turn_duration" not in detail_str


# ported: ClaudeCodeControllerTests.canonicalClaudeToolsAreCategorizedCorrectly
def test_claude_code_canonical_tools_are_categorized_correctly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "project-one" / "session-tools.jsonl"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        '{"type":"assistant","uuid":"a1","timestamp":"2026-05-28T10:00:00Z","message":{"role":"assistant","model":"claude-sonnet-4-20250514","content":[{"type":"tool_use","id":"t1","name":"WebSearch","input":{"query":"hidden"}}]}}\n'
        '{"type":"assistant","uuid":"a2","timestamp":"2026-05-28T10:00:01Z","message":{"role":"assistant","model":"claude-sonnet-4-20250514","content":[{"type":"tool_use","id":"t2","name":"TodoWrite","input":{"todos":[]}}]}}\n'
        '{"type":"assistant","uuid":"a3","timestamp":"2026-05-28T10:00:02Z","message":{"role":"assistant","model":"claude-sonnet-4-20250514","content":[{"type":"tool_use","id":"t3","name":"EnterPlanMode","input":{}}]}}\n'
        '{"type":"assistant","uuid":"a4","timestamp":"2026-05-28T10:00:03Z","message":{"role":"assistant","model":"claude-sonnet-4-20250514","content":[{"type":"tool_use","id":"t4","name":"ReadMcpResourceTool","input":{}}]}}\n'
        '{"type":"assistant","uuid":"a5","timestamp":"2026-05-28T10:00:04Z","message":{"role":"assistant","model":"claude-sonnet-4-20250514","content":[{"type":"tool_use","id":"t5","name":"mcp__github__list_issues","input":{}}]}}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)

    store = session_store(handle.context, Layout.CLAUDE_CODE)
    detail = store.detail("session-tools")
    assert detail is not None
    events = detail["recentEvents"]
    pairs = [(e["toolName"], e["category"]) for e in events]
    assert pairs == [
        ("WebSearch", "WEB"),
        ("TodoWrite", "ASK"),
        ("EnterPlanMode", "ASK"),
        ("ReadMcpResourceTool", "SKILL"),
        ("mcp__github__list_issues", "MCP"),
    ]


def test_claude_code_dashboard_golden_shape_23(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(missing))

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/claude-code/dashboard")
    assert resp.status_code == 200
    data = resp.json()

    golden_dir = Path(__file__).parents[1] / "fixtures" / "bootui" / "2.3.0" / "claude-code"
    golden = json.loads((golden_dir / "dashboard.captured.json").read_text(encoding="utf-8"))

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


# ported: CopilotControllerTests.streamRejectsBeyondConcurrentLimit
def test_stream_rejects_beyond_concurrent_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    slots = handle.context.capture.stream_slots
    assert slots is not None
    assert all(slots.acquire() for _ in range(20))
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp_claude = client.get("/sharpit/api/claude-code/stream")
    assert resp_claude.status_code == 503
    assert resp_claude.json() == {"error": "Too many concurrent sharpit streams"}

    resp_copilot = client.get("/sharpit/api/copilot/stream")
    assert resp_copilot.status_code == 503
    assert resp_copilot.json() == {"error": "Too many concurrent sharpit streams"}

    slots.release()


@pytest.mark.anyio
async def test_session_stream_sends_sessions_then_dashboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_claude_session(tmp_path / "project-one" / "session-one.jsonl")
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_STREAM_DEBOUNCE", "50ms")

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)

    stream = OpenStream(app, "/sharpit/api/claude-code/stream")
    try:
        await asyncio.wait_for(stream.started.wait(), timeout=5.0)
        assert stream.status == 200
        await asyncio.sleep(0.1)
        body = stream.body
        pos_s1 = body.find("event: sessions\n")
        pos_d1 = body.find("event: dashboard\n")
        assert 0 <= pos_s1 < pos_d1, "sessions event must appear before dashboard event"

        # Add a new session file to trigger re-emission on change
        write_claude_session(tmp_path / "project-two" / "session-two.jsonl")
        await asyncio.sleep(0.25)
        body2 = stream.body
        pos_s2 = body2.find("event: sessions\n", pos_d1 + 1)
        pos_d2 = body2.find("event: dashboard\n", pos_s2 + 1)
        assert 0 <= pos_s2 < pos_d2, "stream must re-emit sessions then dashboard when file changes"
    finally:
        stream.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stream.task


@pytest.mark.anyio
async def test_session_stream_initial_refresh_does_not_block_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from httpx import ASGITransport, AsyncClient

    write_claude_session(tmp_path / "project-one" / "session-one.jsonl")
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)

    store = session_store(handle.context, Layout.CLAUDE_CODE)
    entered_refresh = threading.Event()
    proceed = threading.Event()
    refresh_is_running = False
    real_refresh = store.refresh

    def blocking_refresh(*args, **kwargs):
        nonlocal refresh_is_running
        refresh_is_running = True
        entered_refresh.set()
        try:
            proceed.wait(timeout=0.5)
            return real_refresh(*args, **kwargs)
        finally:
            refresh_is_running = False

    monkeypatch.setattr(store, "refresh", blocking_refresh)

    stream = OpenStream(app, "/sharpit/api/claude-code/stream")
    try:
        await asyncio.to_thread(entered_refresh.wait, 2.0)
        assert entered_refresh.is_set() is True

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost")
        resp = await client.get("/sharpit/api/overview")
        assert resp.status_code == 200
        assert refresh_is_running is True, "store.refresh had already finished; event loop was blocked"
    finally:
        proceed.set()
        stream.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stream.task


@pytest.mark.anyio
async def test_stream_tick_runs_single_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sharpit.engine.collectors.agentsessions import AgentSessionSettings, Layout, SessionStore
    from sharpit.fastapi.routes.agent_sessions_stream import _agent_sessions_events

    write_claude_session(tmp_path / "project-one" / "session-one.jsonl")
    settings = AgentSessionSettings(session_state_dir=str(tmp_path))
    store = SessionStore(settings, Layout.CLAUDE_CODE)

    refresh_count = 0
    real_refresh = store.refresh

    def counting_refresh(*args, **kwargs):
        nonlocal refresh_count
        refresh_count += 1
        return real_refresh(*args, **kwargs)

    monkeypatch.setattr(store, "refresh", counting_refresh)

    gen = _agent_sessions_events(store, debounce_seconds=0.05)
    # Startup emits sessions, then dashboard
    await gen.__anext__()
    await gen.__anext__()
    init_refreshes = refresh_count

    # Trigger change so loop yields
    write_claude_session(tmp_path / "project-two" / "session-two.jsonl")
    await gen.__anext__()
    tick_refreshes = refresh_count - init_refreshes
    await gen.aclose()

    assert tick_refreshes == 1, f"Expected 1 store.refresh per stream tick, got {tick_refreshes}"


def test_claude_code_enabled_off_disables_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_claude_session(tmp_path / "project-one" / "session-one.jsonl")
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_ENABLED", "OFF")

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    resp = client.get("/sharpit/api/claude-code/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["unavailableReason"] == "Claude Code panel is disabled via configuration"

    resp_dash = client.get("/sharpit/api/claude-code/dashboard")
    assert resp_dash.status_code == 200
    data_dash = resp_dash.json()
    assert data_dash["available"] is False
    assert data_dash["unavailableReason"] == "Claude Code panel is disabled via configuration"

    panels_resp = client.get("/sharpit/api/panels")
    assert panels_resp.status_code == 200
    panels_data = panels_resp.json()
    p_claude = next(p for p in panels_data["panels"] if p["id"] == "claude-code")
    assert p_claude["available"] is False
    assert p_claude["unavailableReason"] == "Claude Code panel is disabled via configuration"


def test_claude_code_session_tools_default_limit_and_query(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for i in range(15):
        p = tmp_path / f"project-{i}" / f"session_{i:02d}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        m = "gpt-4o" if i % 2 == 0 else "claude-3-5"
        payload = (
            f'{{"type":"assistant","timestamp":"2026-05-28T10:00:{i:02d}Z","cwd":"/work/{i}",'
            f'"message":{{"model":"{m}","content":[{{"type":"tool_use","id":"t{i}","name":"Bash"}}]}}}}\n'
        )
        p.write_text(payload, encoding="utf-8")
    monkeypatch.setenv("SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR", str(tmp_path))

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    cli_resp = client.post("/sharpit/api/cli/tools/get_claude_code_sessions", json={})
    assert cli_resp.status_code == 200
    cli_data = cli_resp.json()
    assert cli_data["available"] is True
    assert cli_data["total"] == 15
    assert cli_data["returned"] == 10
    assert len(cli_data["sessions"]) == 10
    assert cli_data["page"]["limit"] == 10

    cli_filtered = client.post(
        "/sharpit/api/cli/tools/get_claude_code_sessions",
        json={"query": "claude-3-5", "limit": 5},
    ).json()
    assert cli_filtered["returned"] == 5
    for s in cli_filtered["sessions"]:
        assert s["model"] == "claude-3-5"

    tool = next(t for t in TOOLS if t.name == "get_claude_code_sessions")
    call = CallContext(handle.context, {})
    mcp_data = tool.handler(call, {"query": "claude-3-5", "limit": 5})
    assert mcp_data == cli_filtered
