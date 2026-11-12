from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.correlation import REQUEST, RequestInfo
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


def _records(
    sources: tuple[str, ...], *, ai_enabled: bool = True, span: Any = None, **options: Any
) -> tuple[dict[str, object], ...]:
    app = FastAPI()
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        runtime_journal_sources=sources,
        panels={"ai": {"enabled": ai_enabled}},
        **options,
    )
    span_buffer(handle.context).add(span or _span())
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
        "traceId",
        "requestId",
        "durationNanos",
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
    assert record["inputTokens"] == 7  # finding W7-A r2 #2: AiPayload keeps token counts numeric
    assert record["outputTokens"] == 5
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


def test_journal_keeps_only_the_ai_token_counts_numeric():
    from sharpit.engine.capture.journal import RuntimeJournal

    journal = RuntimeJournal(sources=("ai", "sql"))
    journal.offer({"source": "ai", "inputTokens": "sk-text", "outputTokens": 5, "totalTokens": 12})
    journal.offer({"source": "sql", "inputTokens": 7})
    ai_record, sql_record = journal.records("ai")[0], journal.records("sql")[0]
    assert ai_record["inputTokens"] == "******"
    assert ai_record["outputTokens"] == 5
    assert ai_record["totalTokens"] == "******"
    assert sql_record["inputTokens"] == "******"


AUTH_TOKEN = "Zq81mWv3kTnR6yHc"  # random-looking, mixed case: only the never-shown rule can hide it


@pytest.mark.parametrize("exposure", ["MASKED", "METADATA_ONLY"])
def test_ai_journal_finish_reason_never_shows_the_authentication_token(exposure: str):
    # finding W7-A r2f #1: the finish reason was lower-cased before masking, so the case-sensitive
    # never-shown check missed the token
    span = _span({"gen_ai.response.finish_reasons": [f"stop-{AUTH_TOKEN}"]})
    records = _records(("ai",), span=span, authentication_token=AUTH_TOKEN, expose_values=exposure)
    assert len(records) == 1
    assert AUTH_TOKEN.lower() not in str(records).lower()


def test_ai_journal_event_carries_the_trace_id_of_its_span_in_the_http_format():
    # the http producer's ids are lower-case 32-hex (capture/exchanges.trace_id), so the two join
    record = _records(("ai",))[0]
    assert record.get("traceId") == "0" * 31 + "1"


def test_ai_journal_event_carries_its_duration():
    record = _records(("ai",))[0]
    assert record.get("durationNanos") == 1_000_000_000


def test_ai_journal_event_has_a_request_id_key_that_is_empty_outside_a_request():
    record = _records(("ai",))[0]
    assert "requestId" in record
    assert record["requestId"] is None


def test_a_span_ended_inside_a_request_carries_that_request_id():
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, runtime_journal_sources=("ai",))
    seen: list[str | None] = []

    @app.get("/ended-in-request")
    def ended_in_request() -> dict[str, bool]:
        info = REQUEST.get()
        seen.append(info.id if info else None)
        span_buffer(handle.context).add(_span())
        return {"ok": True}

    with TestClient(app) as client:
        client.get("/ended-in-request")
    journal = handle.context.capture.journal
    assert journal is not None
    assert seen[0] is not None
    assert journal.records("ai")[0].get("requestId") == seen[0]


def test_a_span_ended_in_another_installs_request_carries_no_request_id():
    ours = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False, runtime_journal_sources=("ai",))
    theirs = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False, runtime_journal_sources=("ai",))
    token = REQUEST.set(RequestInfo("r-theirs", theirs.context.context_id, "GET", "/x", None, 0, None))
    try:
        span_buffer(ours.context).add(_span())
    finally:
        REQUEST.reset(token)
    journal = ours.context.capture.journal
    assert journal is not None
    assert journal.records("ai")[0].get("requestId") is None
