from __future__ import annotations

import contextlib
from pathlib import Path

from sharpit.engine.collectors.agentsessions.parser import Layout, parse_session


def test_sanitized_summary_does_not_leak_sensitive_fields(tmp_path: Path) -> None:
    # ported: CopilotControllerTests.sanitizedSummaryDoesNotLeakSensitiveFields
    session_file = tmp_path / "s1.json"
    session_file.write_text(
        """{"events":[
          {"type":"shell","tool":"bash","timestamp":1,
           "args":["rm","-rf","/secret"],
           "output":"super secret output",
           "prompt":"top-secret prompt",
           "path":"/work/passwords.txt"}
        ]}""",
        encoding="utf-8",
    )
    parsed = parse_session(session_file, Layout.COPILOT, 2000)
    assert len(parsed.events) == 1
    event = parsed.events[0]
    summary = event["summary"]
    assert "super secret output" not in summary
    assert "top-secret prompt" not in summary
    assert "passwords" not in summary
    assert "rm -rf" not in summary
    assert summary == "SHELL · bash · *.txt"


def test_session_detail_flags_schema_drift_for_unknown_shape(tmp_path: Path) -> None:
    # ported: CopilotControllerTests.sessionDetailFlagsSchemaDriftForUnknownShape
    session_file = tmp_path / "weird.json"
    session_file.write_text('{"hello":"world"}', encoding="utf-8")
    parsed = parse_session(session_file, Layout.COPILOT, 2000)
    assert parsed.summary["schemaDrift"] is True
    assert parsed.summary["eventCount"] == 0


def test_failure_events_include_inherited_tool_names(tmp_path: Path) -> None:
    # ported: CopilotControllerTests.failureEventsIncludeInheritedToolNames
    session_dir = tmp_path / "s1"
    session_dir.mkdir()
    events_file = session_dir / "events.jsonl"
    events_file.write_text(
        '{"id":"start","type":"tool.execution_start","timestamp":1,"data":{"toolName":"create"}}\n'
        '{"id":"failed","parentId":"start","type":"tool.execution_complete","timestamp":2,"data":{"success":false}}\n',
        encoding="utf-8",
    )
    parsed = parse_session(events_file, Layout.COPILOT, 2000)
    assert len(parsed.failure_events) == 1
    fail = parsed.failure_events[0]
    assert fail["toolName"] == "create"
    assert "create" in fail["summary"]
    assert "failed" in fail["summary"]


def test_copilot_jsonl_sessions_sanitized(tmp_path: Path) -> None:
    session_dir = tmp_path / "session-1"
    session_dir.mkdir()
    events_file = session_dir / "events.jsonl"
    events_file.write_text(
        '{"id":"e1","type":"session.start","timestamp":"2026-05-28T07:00:00Z",'
        '"data":{"model":"gpt-5.5","context":{"cwd":"/work/project","repository":"jdubois/boot-ui","branch":"main"}}}\n'
        '{"id":"e2","type":"user.message","timestamp":"2026-05-28T07:00:01Z",'
        '"data":{"content":"secret prompt","transformedContent":"secret transformed prompt"}}\n'
        '{"id":"e3","type":"tool.execution_start","timestamp":"2026-05-28T07:00:02Z",'
        '"data":{"toolName":"apply_patch","success":true,"arguments":{"command":"do not expose this"}}}\n'
        '{"id":"e4","type":"tool.execution_complete","timestamp":"2026-05-28T07:00:03Z",'
        '"data":{"toolName":"apply_patch","success":false,'
        '"input":{"toolResult":{"textResultForLlm":"secret output"}}}}\n',
        encoding="utf-8",
    )
    parsed = parse_session(events_file, Layout.COPILOT, 2000)
    assert parsed.summary["id"] == "session-1"
    assert parsed.summary["model"] == "gpt-5.5"
    assert parsed.summary["workingDirectory"] == "/work/project"
    # tool start and complete (session.start and user.message are not tool events)
    assert parsed.summary["eventCount"] == 2
    assert parsed.summary["errorCount"] == 1
    recent_types = [e["type"] for e in parsed.events]
    assert "user.message" not in recent_types
    for e in parsed.events:
        text = str(e)
        assert "secret prompt" not in text
        assert "secret transformed prompt" not in text
        assert "secret output" not in text
        assert "do not expose this" not in text


def test_session_files_confined_and_bounded(tmp_path: Path) -> None:
    # 1. Top-level symlink skipped
    real_file = tmp_path / "real.json"
    real_file.write_text('{"events":[{"type":"t","tool":"grep","timestamp":1}]}', encoding="utf-8")
    symlink_file = tmp_path / "symlink.json"
    with contextlib.suppress(OSError, NotImplementedError):
        symlink_file.symlink_to(real_file)

    # 2. 32 MiB + 1 file (built sparse) skipped
    big_file = tmp_path / "oversized.json"
    with open(big_file, "wb") as f:
        f.seek(32 * 1024 * 1024 + 1)
        f.write(b" ")
    assert big_file.stat().st_size > 32 * 1024 * 1024

    # 3. Undecodable bytes
    bad_bytes_file = tmp_path / "bad_bytes.json"
    bad_bytes_file.write_bytes(b'{"events": [\xff\xfe invalid utf8]}')
    parsed_bad = parse_session(bad_bytes_file, Layout.COPILOT, 2000)
    assert parsed_bad.summary["schemaDrift"] is True

    # 4. Partial last line in jsonl
    partial_jsonl_dir = tmp_path / "partial"
    partial_jsonl_dir.mkdir()
    partial_file = partial_jsonl_dir / "events.jsonl"
    partial_file.write_text(
        '{"id":"e1","type":"tool.execution_start","timestamp":1,"data":{"toolName":"grep"}}\n'
        '{"id":"e2","type":"tool.execution_com',
        encoding="utf-8",
    )
    parsed_partial = parse_session(partial_file, Layout.COPILOT, 2000)
    assert parsed_partial.summary["schemaDrift"] is True
    assert len(parsed_partial.events) == 1
    assert parsed_partial.events[0]["toolName"] == "grep"


def test_session_state_dir_shown_unexpanded(tmp_path: Path) -> None:
    from sharpit.engine.collectors.agentsessions import AgentSessionSettings
    from sharpit.engine.collectors.agentsessions.store import SessionStore

    settings = AgentSessionSettings(session_state_dir="~/.copilot/session-state")
    store = SessionStore(settings, Layout.COPILOT)
    sessions_dto = store.sessions()
    assert sessions_dto["sessionStateDir"] == "~/.copilot/session-state"
    assert "~/.copilot/session-state" in str(sessions_dto["unavailableReason"])
    assert str(Path.home()) not in sessions_dto["sessionStateDir"]
