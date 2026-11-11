from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

from sharpit.engine.collectors.agentsessions import AgentSessionSettings, Layout, SessionStore


def test_refresh_parses_only_most_recently_modified_sessions(tmp_path: Path) -> None:
    # ported: CopilotControllerTests.refreshParsesOnlyMostRecentlyModifiedSessions
    old = tmp_path / "old.json"
    middle = tmp_path / "middle.json"
    new = tmp_path / "new.json"
    old.write_text('{"updated_at":1700000000,"events":[{"type":"t"}]}', encoding="utf-8")
    middle.write_text('{"updated_at":1700000001,"events":[{"type":"t"}]}', encoding="utf-8")
    new.write_text('{"updated_at":1700000002,"events":[{"type":"t"}]}', encoding="utf-8")
    os.utime(old, (1, 1))
    os.utime(middle, (2, 2))
    os.utime(new, (3, 3))

    settings = AgentSessionSettings(session_state_dir=str(tmp_path), max_parsed_sessions=2)
    store = SessionStore(settings, Layout.COPILOT)
    store.refresh()

    res = store.sessions()
    assert res["total"] == 2
    assert [s["id"] for s in res["sessions"]] == ["new", "middle"]
    assert len(res["warnings"]) == 1
    assert "Loaded the 2 most recently modified Copilot session files out of 3" in res["warnings"][0]


def test_sessions_list_can_filter_by_activity_window(tmp_path: Path) -> None:
    # ported: CopilotControllerTests.sessionsListCanFilterByActivityWindow
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text('{"updated_at":1700000000,"events":[{"type":"t"}]}', encoding="utf-8")
    new.write_text('{"updated_at":1700000100,"events":[{"type":"t"}]}', encoding="utf-8")

    settings = AgentSessionSettings(session_state_dir=str(tmp_path))
    store = SessionStore(settings, Layout.COPILOT)
    res = store.sessions(since=1700000050000, until=1700000200000)
    assert res["total"] == 1
    assert res["sessions"][0]["id"] == "new"


def test_dashboard_aggregates_jsonl_sessions(tmp_path: Path) -> None:
    # ported: CopilotControllerTests.dashboardAggregatesJsonlSessions
    first_session = tmp_path / "s1"
    second_session = tmp_path / "s2"
    first_session.mkdir()
    second_session.mkdir()
    (first_session / "events.jsonl").write_text(
        '{"id":"s1-start","type":"session.start","timestamp":"2026-05-28T10:00:00Z","data":{"model":"gpt-5.5","context":{"cwd":"/work/one"}}}\n'
        '{"id":"s1-edit","type":"tool.execution_start","timestamp":"2026-05-28T10:15:00Z","data":{"toolName":"apply_patch","success":true}}\n'
        '{"id":"s1-message","type":"assistant.message","timestamp":"2026-05-28T10:30:00Z","data":{"turnId":"turn-1","outputTokens":9,"content":"hidden"}}\n'
        '{"id":"s1-search","type":"tool.execution_complete","timestamp":"2026-05-28T11:00:00Z","data":{"toolName":"grep","success":false}}\n'
        '{"id":"s1-shutdown","type":"session.shutdown","timestamp":"2026-05-28T11:30:00Z","data":{"tokenDetails":{"input":{"tokenCount":334},"cache_read":{"tokenCount":800},"cache_write":{"tokenCount":100},"output":{"tokenCount":15}},"modelMetrics":{"gpt-5.5":{"usage":{"inputTokens":0,"outputTokens":0,"cacheReadTokens":900}}}}}\n',
        encoding="utf-8",
    )
    (second_session / "events.jsonl").write_text(
        '{"id":"s2-start","type":"session.start","timestamp":"2026-05-27T12:30:00Z","data":{"model":"gpt-4o","context":{"cwd":"/work/two"}}}\n'
        '{"id":"s2-mcp","type":"tool.execution_start","timestamp":"2026-05-27T13:00:00Z","data":{"toolName":"mcp.fetch","success":true}}\n'
        '{"id":"s2-message","type":"assistant.message","timestamp":"2026-05-27T13:15:00Z","data":{"turnId":"turn-1","outputTokens":7,"content":"hidden"}}\n',
        encoding="utf-8",
    )

    settings = AgentSessionSettings(session_state_dir=str(tmp_path))
    fixed_now_millis = 1779969600000  # 2026-05-28T12:00:00Z
    store = SessionStore(settings, Layout.COPILOT, clock=lambda: fixed_now_millis)

    dash = store.dashboard()
    assert dash["available"] is True
    assert dash["sessionCount"] == 2
    assert dash["eventCount"] == 6
    assert dash["totalInputTokens"] == 1234
    assert dash["totalOutputTokens"] == 22
    assert dash["errorCount"] == 1
    assert dash["activeLast24Hours"] == 2
    assert dash["activeLast7Days"] == 2
    assert dash["sessionsWithSchemaDrift"] == 0
    assert dash["categoryCounts"][0]["label"] == "OTHER"
    assert dash["categoryCounts"][0]["count"] == 3
    assert dash["topTools"][0]["label"] == "apply_patch"
    assert dash["modelCounts"][0]["count"] == 1
    assert len(dash["activityBuckets"]) == 24
    assert dash["activityBuckets"][0]["outputTokens"] == 7
    assert dash["activityBuckets"][22]["inputTokens"] == 1234
    assert dash["activityBuckets"][22]["outputTokens"] == 15
    assert len(dash["dailyActivityBuckets"]) == 7
    assert dash["dailyActivityBuckets"][5]["eventCount"] == 2
    assert dash["dailyActivityBuckets"][5]["outputTokens"] == 7
    assert dash["dailyActivityBuckets"][6]["eventCount"] == 4
    assert dash["dailyActivityBuckets"][6]["errorCount"] == 1
    assert dash["dailyActivityBuckets"][6]["inputTokens"] == 1234
    assert dash["dailyActivityBuckets"][6]["outputTokens"] == 15
    assert len(dash["recentSessions"]) == 2
    assert dash["recentSessions"][0]["inputTokens"] == 1234
    assert dash["recentSessions"][0]["outputTokens"] == 15
    assert dash["recentSessions"][1]["outputTokens"] == 7

    detail = store.detail("s1")
    assert detail is not None
    assert detail["summary"]["inputTokens"] == 1234
    assert detail["summary"]["outputTokens"] == 15
    assert detail["turns"][1]["outputTokens"] == 9


def test_events_filter_by_category_and_limit(tmp_path: Path) -> None:
    # ported: CopilotControllerTests.eventsFilterByCategoryAndLimit
    session_file = tmp_path / "s1.json"
    session_file.write_text(
        """{"events":[
          {"type":"t","tool":"apply_patch","timestamp":1},
          {"type":"t","tool":"grep","timestamp":2},
          {"type":"t","tool":"mcp.list","timestamp":3}
        ]}""",
        encoding="utf-8",
    )

    settings = AgentSessionSettings(session_state_dir=str(tmp_path))
    store = SessionStore(settings, Layout.COPILOT)
    events_dto = store.events("s1", category="MCP")
    assert events_dto is not None
    assert events_dto["total"] == 1
    assert events_dto["events"][0]["toolName"] == "mcp.list"
    assert events_dto["events"][0]["category"] == "MCP"


def test_copilot_session_list_capped(tmp_path: Path) -> None:
    old = tmp_path / "old.json"
    middle = tmp_path / "middle.json"
    new = tmp_path / "new.json"
    old.write_text('{"updated_at":1700000000,"events":[{"type":"t"}]}', encoding="utf-8")
    middle.write_text('{"updated_at":1700000001,"events":[{"type":"t"}]}', encoding="utf-8")
    new.write_text('{"updated_at":1700000002,"events":[{"type":"t"}]}', encoding="utf-8")

    settings = AgentSessionSettings(session_state_dir=str(tmp_path), max_sessions=2)
    store = SessionStore(settings, Layout.COPILOT)
    res = store.sessions()
    assert res["total"] == 3
    assert res["returned"] == 2
    assert res["maxSessions"] == 2
    assert res["sessions"][0]["id"] == "new"
    assert res["sessions"][1]["id"] == "middle"
    assert res["warnings"][0] == "Showing the 2 most recent Copilot sessions out of 3."


def test_session_parse_cache_skips_unchanged_files(tmp_path: Path) -> None:
    s1 = tmp_path / "s1.json"
    s1.write_text('{"updated_at":1700000000,"events":[{"type":"t","tool":"grep"}]}', encoding="utf-8")

    settings = AgentSessionSettings(session_state_dir=str(tmp_path))
    store = SessionStore(settings, Layout.COPILOT)

    import builtins

    real_open = builtins.open
    open_count = 0

    def spy_open(*args, **kwargs):
        nonlocal open_count
        path = str(args[0])
        if str(tmp_path) in path:
            open_count += 1
        return real_open(*args, **kwargs)

    with patch("builtins.open", side_effect=spy_open):
        store.refresh()
        assert open_count == 1
        open_count = 0

        # Second refresh: file unchanged, so open_count must stay 0
        store.refresh()
        assert open_count == 0

        # Touch the file
        time.sleep(0.01)
        s1.write_text('{"updated_at":1700000001,"events":[{"type":"t","tool":"grep"}]}', encoding="utf-8")

        # Third refresh: file touched, so it must be opened once
        store.refresh()
        assert open_count == 1
