from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest

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
    parsed = parse_session(session_file, 2000)
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
    parsed = parse_session(session_file, 2000)
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
    parsed = parse_session(events_file, 2000)
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
    parsed = parse_session(events_file, 2000)
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
    parsed_bad = parse_session(bad_bytes_file, 2000)
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
    parsed_partial = parse_session(partial_file, 2000)
    assert parsed_partial.summary["schemaDrift"] is True
    assert len(parsed_partial.events) == 1
    assert parsed_partial.events[0]["toolName"] == "grep"


def test_session_state_dir_shown_unexpanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sharpit.engine.collectors.agentsessions import AgentSessionSettings
    from sharpit.engine.collectors.agentsessions.store import SessionStore

    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    settings = AgentSessionSettings(session_state_dir="~/.copilot/session-state")
    store = SessionStore(settings, Layout.COPILOT)
    sessions_dto = store.sessions()
    assert sessions_dto["sessionStateDir"] == "~/.copilot/session-state"
    assert "~/.copilot/session-state" in str(sessions_dto["unavailableReason"])
    assert str(fake_home) not in sessions_dto["sessionStateDir"]


def test_legacy_parser_raw_by_id_stores_path_and_line_tuple(tmp_path: Path) -> None:
    legacy_file = tmp_path / "legacy_session.json"
    legacy_file.write_text(
        '{"events":[{"type":"shell","tool":"bash","timestamp":1000,"summary":"run"}]}',
        encoding="utf-8",
    )
    parsed = parse_session(legacy_file, 2000)
    assert len(parsed.events) == 1
    ev_id = parsed.events[0]["id"]
    raw_val = parsed.raw_by_id.get(ev_id)
    assert isinstance(raw_val, tuple), f"raw_by_id expected tuple, got {type(raw_val)}"
    assert raw_val[0] == legacy_file


def test_path_hint_caps_extension_length() -> None:
    from sharpit.engine.collectors.agentsessions._common import path_hint

    assert path_hint("document.verylongextension") == "*.verylongexte"
    assert path_hint("test.py") == "*.py"
    assert path_hint("no_extension") is None


@pytest.mark.anyio
async def test_agent_sessions_sanitisation_leaks_no_prompts_or_secrets(tmp_path: Path) -> None:
    from sharpit.engine.collectors.agentsessions import AgentSessionSettings
    from sharpit.engine.collectors.agentsessions.store import SessionStore
    from sharpit.engine.context import SharpitContext
    from sharpit.engine.tools import CallContext
    from sharpit.engine.tools04.claude_code import TOOLS as CLAUDE_TOOLS
    from sharpit.engine.tools04.copilot import TOOLS as COPILOT_TOOLS
    from sharpit.fastapi.routes.agent_sessions_stream import _agent_sessions_events
    from sharpit.settings import SharpitSettings

    # 1. Claude Code transcript
    claude_proj = tmp_path / "claude" / "project-secrets"
    claude_proj.mkdir(parents=True, exist_ok=True)
    claude_file = claude_proj / "secret-session.jsonl"
    claude_file.write_text(
        '{"type":"user","uuid":"u1","timestamp":"2026-05-28T10:00:00Z","cwd":"/work/app",'
        '"message":{"role":"user","content":"USER_PROMPT_SECRET_xyz"}}\n'
        '{"type":"assistant","uuid":"a1","timestamp":"2026-05-28T10:00:01Z",'
        '"message":{"model":"claude-3-5","content":['
        '{"type":"tool_use","id":"t1","name":"Bash","input":{"cmd":"SECRET_INPUT_CMD_abc"}},'
        '{"type":"text","text":"sk-ant-api03-SECRET_KEY_123"}'
        "]}}\n"
        '{"type":"assistant","uuid":"a2","timestamp":"2026-05-28T10:00:02Z",'
        '"message":{"model":"claude-3-5","content":['
        '{"type":"tool_result","tool_use_id":"t1","output":"AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE_SECRET\\nDATABASE_URL=postgres://user:super_secret_pw@db.internal:5432/production"}'
        "]}}\n",
        encoding="utf-8",
    )

    # 2. Copilot transcripts (JSONL session directory + legacy .json)
    copilot_dir = tmp_path / "copilot"
    copilot_sess = copilot_dir / "copilot-secret-sess"
    copilot_sess.mkdir(parents=True, exist_ok=True)
    (copilot_sess / "events.jsonl").write_text(
        '{"id":"cs-start","type":"session.start","timestamp":"2026-05-28T10:00:00Z","data":{"model":"gpt-4o","context":{"cwd":"/work/copilot"}}}\n'
        '{"id":"cs-edit","type":"tool.execution_start","timestamp":"2026-05-28T10:05:00Z","data":{"toolName":"apply_patch","input":{"patch":"SECRET_INPUT_CMD_abc"}}}\n'
        '{"id":"cs-msg","type":"assistant.message","timestamp":"2026-05-28T10:10:00Z","data":{"turnId":"turn-1","content":"sk-ant-api03-SECRET_KEY_123"}}\n'
        '{"id":"cs-env","type":"tool.execution_complete","timestamp":"2026-05-28T10:15:00Z","data":{"toolName":"shell","output":"AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE_SECRET\\nDATABASE_URL=postgres://user:super_secret_pw@db.internal:5432/production"}}\n'
        '{"id":"cs-user","type":"user.message","timestamp":"2026-05-28T10:20:00Z","data":{"content":"USER_PROMPT_SECRET_xyz"}}\n',
        encoding="utf-8",
    )
    (copilot_dir / "legacy-secret.json").write_text(
        '{"updated_at":1700000000,"events":['
        '{"type":"user","summary":"USER_PROMPT_SECRET_xyz"},'
        '{"type":"tool","tool":"shell","input":"SECRET_INPUT_CMD_abc","output":"AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE_SECRET"},'
        '{"type":"assistant","summary":"sk-ant-api03-SECRET_KEY_123"}'
        "]}",
        encoding="utf-8",
    )

    secrets = [
        "USER_PROMPT_SECRET_xyz",
        "SECRET_INPUT_CMD_abc",
        "sk-ant-api03-SECRET_KEY_123",
        "AKIAIOSFODNN7EXAMPLE_SECRET",
        "super_secret_pw",
        "AWS_SECRET_ACCESS_KEY",
        "DATABASE_URL",
    ]

    payloads: list[str] = []

    # Check Claude Code
    claude_store = SessionStore(AgentSessionSettings(session_state_dir=str(tmp_path / "claude")), Layout.CLAUDE_CODE)
    payloads.append(json.dumps(claude_store.sessions()))
    payloads.append(json.dumps(claude_store.dashboard()))
    payloads.append(json.dumps(claude_store.detail("secret-session")))
    payloads.append(json.dumps(claude_store.events("secret-session", category=None, since=None, limit=100)))

    claude_ctx = SharpitContext(
        SharpitSettings(claude_code_session_state_dir=str(tmp_path / "claude")),
        None,
        None,
        None,
        None,
        None,
        None,
    )
    claude_call_ctx = CallContext(claude_ctx, {})
    tool_claude_sess = next(t for t in CLAUDE_TOOLS if t.name == "get_claude_code_sessions")
    payloads.append(json.dumps(tool_claude_sess.handler(claude_call_ctx, {"limit": 10})))

    claude_stream_events: list[tuple[str, str | None, str]] = []
    async for ev in _agent_sessions_events(claude_store, 0.05):
        claude_stream_events.append(ev)
        if len(claude_stream_events) >= 2:
            break
    payloads.append(json.dumps(claude_stream_events))

    # Check Copilot
    copilot_store = SessionStore(AgentSessionSettings(session_state_dir=str(copilot_dir)), Layout.COPILOT)
    payloads.append(json.dumps(copilot_store.sessions()))
    payloads.append(json.dumps(copilot_store.dashboard()))
    payloads.append(json.dumps(copilot_store.detail("copilot-secret-sess")))
    payloads.append(json.dumps(copilot_store.events("copilot-secret-sess", category=None, since=None, limit=100)))

    copilot_ctx = SharpitContext(
        SharpitSettings(copilot_session_state_dir=str(copilot_dir)),
        None,
        None,
        None,
        None,
        None,
        None,
    )
    copilot_call_ctx = CallContext(copilot_ctx, {})
    tool_copilot_sess = next(t for t in COPILOT_TOOLS if t.name == "get_copilot_sessions")
    payloads.append(json.dumps(tool_copilot_sess.handler(copilot_call_ctx, {"limit": 10})))

    copilot_stream_events: list[tuple[str, str | None, str]] = []
    async for ev in _agent_sessions_events(copilot_store, 0.05):
        copilot_stream_events.append(ev)
        if len(copilot_stream_events) >= 2:
            break
    payloads.append(json.dumps(copilot_stream_events))

    for p in payloads:
        for secret in secrets:
            assert secret not in p, f"Secret leaked in payload: {secret}"
