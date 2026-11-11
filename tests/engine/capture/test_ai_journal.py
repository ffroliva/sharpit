from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.traces import span_buffer


def _span(attributes: dict[str, Any] | None = None) -> Any:
    return SimpleNamespace(
        context=SimpleNamespace(trace_id=1, span_id=2),
        kind=SimpleNamespace(name="INTERNAL"),
        name="chat",
        start_time=60_000_000_000,
        end_time=61_000_000_000,
        status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET")),
        attributes={
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-test",
            "gen_ai.usage.input_tokens": 7,
            "gen_ai.usage.output_tokens": 5,
            "gen_ai.response.finish_reasons": ["STOP"],
            "gen_ai.input.messages": "prompt canary must not enter the journal",
            **(attributes or {}),
        },
    )


def _records(sources: tuple[str, ...], *, ai_enabled: bool = True) -> tuple[dict[str, object], ...]:
    app = FastAPI()
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        runtime_journal_sources=sources,
        panels={"ai": {"enabled": ai_enabled}},
    )
    span_buffer(handle.context).add(_span())
    journal = handle.context.capture.journal
    assert journal is not None
    return journal.records("ai")


def test_ai_journal_event_is_metadata_only():
    records = _records(("ai",))
    assert len(records) == 1
    record = records[0]
    assert record["source"] == "ai"
    assert set(record) - {"source"} == {
        "operation",
        "provider",
        "model",
        "inputTokens",
        "outputTokens",
        "finishReason",
        "failed",
        "spanId",
        "completedNanos",
        "codePathStamp",
    }
    assert record["operation"] == "chat"
    assert record["provider"] == "openai"
    assert record["model"] == "gpt-test"
    assert record["inputTokens"] == "******"
    assert record["outputTokens"] == "******"
    assert record["failed"] is False
    assert record["codePathStamp"] == 0
    assert "prompt canary must not enter the journal" not in str(record)


def test_ai_journal_follows_journal_sources_not_panel():
    panel_disabled = _records(("ai",), ai_enabled=False)
    assert len(panel_disabled) == 1
    source_disabled = _records(("sql",), ai_enabled=False)
    assert source_disabled == ()


def test_ai_journal_finish_reason_normalised():
    # ported: AiCallEventsTests.aFrameworksNamesTokensAndFinishReasonsAreNormalized
    records = _records(("ai",))
    assert len(records) == 1
    assert records[0]["finishReason"] == "stop"
