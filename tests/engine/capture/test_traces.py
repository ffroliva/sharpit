"""The span buffer and the trace DTOs (lane A-traces, Task 2; BootUI ``TracesServiceTests``).

Spans are SDK-``ReadableSpan``-shaped fakes: the SDK is not a test dependency and the buffer reads spans duck-typed.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from sharpit.engine import otel
from sharpit.engine.capture.correlation import INTERNAL
from sharpit.engine.capture.streams import SSE_TASK
from sharpit.engine.capture.traces import SpanBuffer
from sharpit.engine.masking import MASK, Exposure, Masker

MASKED = Masker(Exposure.MASKED, True)
FULL = Masker(Exposure.FULL, True)
TRACE = 0x2EBE213F5EE32D51495B4077F5F4DC74
OTHER = 0xC9BDC3CBE2A6ED25EF75355D78DB82B4


def span(
    trace_id: int = TRACE,
    span_id: int = 1,
    parent: int | None = None,
    *,
    name: str = "GET /",
    kind: str = "SERVER",
    attributes: dict[str, Any] | None = None,
    start: int = 1_000,
    end: int = 3_000,
    service: str = "api",
    status: str = "UNSET",
    events: list[Any] | None = None,
) -> Any:
    return SimpleNamespace(
        context=SimpleNamespace(trace_id=trace_id, span_id=span_id),
        parent=None if parent is None else SimpleNamespace(trace_id=trace_id, span_id=parent),
        name=name,
        kind=SimpleNamespace(name=kind),
        resource=SimpleNamespace(attributes={"service.name": service}),
        instrumentation_scope=SimpleNamespace(name="tests"),
        start_time=start,
        end_time=end,
        status=SimpleNamespace(status_code=SimpleNamespace(name=status), description=None),
        attributes=attributes or {},
        events=events or [],
    )


def event(name: str, timestamp: int, attributes: dict[str, Any]) -> Any:
    return SimpleNamespace(name=name, timestamp=timestamp, attributes=attributes)


def buffer(masker: Masker = MASKED) -> SpanBuffer:
    return SpanBuffer(masker, capacity=1000, self_path="/sharpit")


def summary(buf: SpanBuffer) -> dict[str, Any]:
    traces = buf.list(100)["traces"]
    assert len(traces) == 1
    return traces[0]


def attribute(span_dto: dict[str, Any], key: str) -> Any:
    return next(a["value"] for a in span_dto["attributes"] if a["key"] == key)


def test_summary_exposes_http_path_from_root_server_span():
    # ported: TracesServiceTests.summaryExposesHttpPathFromRootServerSpan
    buf = buffer()
    buf.add(span(attributes={"http.route": "/api/v1/accounts/{uid}/balance"}))
    assert summary(buf)["httpPath"] == "/api/v1/accounts/{uid}/balance"


def test_summary_falls_back_to_server_span_when_root_has_no_path():
    # ported: TracesServiceTests.summaryFallsBackToServerSpanWhenRootHasNoPath
    buf = buffer()
    buf.add(span(span_id=1, name="security filterchain", kind="INTERNAL", start=1_000))
    buf.add(span(span_id=2, parent=1, attributes={"url.path": "/owners"}, start=1_500))
    assert summary(buf)["httpPath"] == "/owners"


def test_summary_leaves_http_path_null_when_no_path_attribute_is_present():
    # ported: TracesServiceTests.summaryLeavesHttpPathNullWhenNoPathAttributeIsPresent
    buf = buffer()
    buf.add(span(kind="INTERNAL", name="job"))
    assert summary(buf)["httpPath"] is None


def test_list_and_detail_hide_sharpit_self_traces():
    # ported: TracesServiceTests.listAndDetailHideBootUiSelfTraces
    buf = buffer()
    buf.add(span(trace_id=OTHER, attributes={"url.path": "/sharpit/api/traces"}))
    buf.add(span(attributes={"url.path": "/owners"}))
    report = buf.list(100)
    assert [t["traceId"] for t in report["traces"]] == [f"{TRACE:032x}"]
    assert buf.detail(f"{OTHER:032x}") is None


def test_summary_masks_matrix_parameters_of_the_http_path():
    # ported: TracesServiceTests.summaryMasksMatrixParametersOfTheHttpPath
    buf = buffer()
    buf.add(span(attributes={"url.path": "/cart;jsessionid=ABC123/items"}))
    assert summary(buf)["httpPath"] == f"/cart;jsessionid={MASK}/items"


def test_summary_never_returns_the_authority_of_an_absolute_url():
    # ported: TracesServiceTests.summaryNeverReturnsTheAuthorityOfAnAbsoluteUrl
    buf = buffer()
    buf.add(span(attributes={"url.full": "https://admin:hunter2@internal.example:8443/owners?page=2"}))
    assert summary(buf)["httpPath"] == "/owners"


def test_detail_applies_the_live_exposure_policy_on_every_read():
    # ported: TracesServiceTests.detailAppliesTheLiveExposurePolicyOnEveryRead
    buf = buffer(FULL)
    buf.add(span(attributes={"db.statement": "select * from users where password = 'hunter2'"}))
    trace_id = f"{TRACE:032x}"
    first = buf.detail(trace_id)
    buf.masker = MASKED
    second = buf.detail(trace_id)
    assert first is not None
    assert second is not None
    assert "hunter2" in attribute(first["spans"][0], "db.statement")
    assert "hunter2" not in attribute(second["spans"][0], "db.statement")


def test_span_reads_mask_nested_values():
    # ported: TracesServiceTests.spanReadsMaskNestedValuesWithoutChangingStoredEvidence
    raw = span(
        attributes={
            "http.request.header.authorization": ("Bearer abc.def.ghi",),
            "db.statement": "select 1 from t where token = 'sk_live_4eC39HqLyjWDarjtT1zdp7dc'",
        },
        events=[event("exception", 2_000, {"exception.message": "login failed password=hunter2"})],
    )
    buf = buffer()
    buf.add(raw)
    detail = buf.detail(f"{TRACE:032x}")
    assert detail is not None
    text = str(detail)
    assert "abc.def.ghi" not in text
    assert "sk_live_4eC39HqLyjWDarjtT1zdp7dc" not in text
    assert "hunter2" not in text
    assert raw.events[0].attributes["exception.message"] == "login failed password=hunter2"  # stored evidence kept


def test_summary_and_span_dto_keys():
    buf = buffer()
    buf.add(span(span_id=1, start=1_000, end=5_000, attributes={"gen_ai.system": "x"}))
    buf.add(span(span_id=2, parent=1, start=2_000, end=3_000, status="ERROR", service="db", kind="CLIENT"))
    row = summary(buf)
    assert row == {
        "traceId": f"{TRACE:032x}",
        "rootSpanName": "GET /",
        "httpPath": None,
        "services": ["api", "db"],
        "startEpochNanos": 1_000,
        "endEpochNanos": 5_000,
        "durationNanos": 4_000,
        "spanCount": 2,
        "hasError": True,
        "hasAi": True,
    }
    detail = buf.detail(f"{TRACE:032x}")
    assert detail is not None
    child = detail["spans"][1]
    assert child == {
        "traceId": f"{TRACE:032x}",
        "spanId": f"{2:016x}",
        "parentSpanId": f"{1:016x}",
        "name": "GET /",
        "kind": "CLIENT",
        "serviceName": "db",
        "scope": "tests",
        "startEpochNanos": 2_000,
        "endEpochNanos": 3_000,
        "durationNanos": 1_000,
        "statusCode": "ERROR",
        "statusMessage": None,
        "attributes": [],
        "events": [],
    }


def test_event_offsets_are_relative_to_the_span_start():
    buf = buffer()
    buf.add(span(start=1_000, events=[event("retry", 1_250, {"attempt": 2})]))
    detail = buf.detail(f"{TRACE:032x}")
    assert detail is not None
    assert detail["spans"][0]["events"] == [
        {"name": "retry", "timeOffsetNanos": 250, "attributes": [{"key": "attempt", "type": "LONG", "value": "2"}]}
    ]


def test_list_is_newest_first_and_limited():
    buf = buffer()
    buf.add(span(trace_id=TRACE, start=1_000))
    buf.add(span(trace_id=OTHER, start=9_000, end=9_500))
    report = buf.list(1)
    assert [t["traceId"] for t in report["traces"]] == [f"{OTHER:032x}"]
    assert report["retained"] == 2


def test_capacity_bounds_retained_spans():
    buf = SpanBuffer(MASKED, capacity=2, self_path="/sharpit")
    for i in range(5):
        buf.add(span(trace_id=i + 1, start=i))
    assert buf.list(100)["retained"] == 2


def test_clear_empties_the_buffer():
    buf = buffer()
    buf.add(span())
    buf.clear()
    assert buf.list(100)["traces"] == []


def test_one_processor_per_provider_across_reinstall(monkeypatch: pytest.MonkeyPatch):
    provider = SimpleNamespace(processors=[])
    provider.add_span_processor = provider.processors.append
    trace = ModuleType("opentelemetry.trace")
    trace.get_tracer_provider = lambda: provider  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", ModuleType("opentelemetry.sdk.trace"))
    monkeypatch.setattr(otel, "PROCESSOR", otel.SharpitSpanProcessor())
    first, second = buffer(), buffer()
    remove_first = first.arm()
    assert remove_first is not None
    remove_first()  # uninstall
    first.arm()  # reinstall
    second.arm()  # a second app on the same provider
    otel.PROCESSOR.on_end(span())
    assert provider.processors == [otel.PROCESSOR]
    assert len(first.list(100)["traces"]) == 1
    assert len(second.list(100)["traces"]) == 1


def test_report_says_why_traces_are_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delitem(sys.modules, "opentelemetry.sdk.trace", raising=False)
    report = buffer().list(100)
    assert report["enabled"] is False
    assert report["unavailableReason"] == otel.NO_SDK


def test_sql_literals_in_db_statement_are_masked():
    # live check (real SDK): a literal under a non-secret column name leaked through mask_text alone
    buf = buffer()
    buf.add(span(attributes={"db.statement": "select * from owners where pw = 'hunter2'"}))
    detail = buf.detail(f"{TRACE:032x}")
    assert detail is not None
    assert attribute(detail["spans"][0], "db.statement") == "select * from owners where pw = ?"


def first_span(buf: SpanBuffer) -> dict[str, Any]:
    detail = buf.detail(f"{TRACE:032x}")
    assert detail is not None
    return detail["spans"][0]


def test_otel_normalised_set_cookie_header_is_masked():
    # review r1: OTel names header attributes lower case with "-" as "_"; set_cookie missed the credential list
    buf = buffer()
    buf.add(span(attributes={"http.response.header.set_cookie": ("sid=abc123; HttpOnly",)}))
    assert attribute(first_span(buf), "http.response.header.set_cookie") == f"[{MASK}]"


def test_header_attribute_values_go_through_text_masking():
    buf = buffer()
    buf.add(span(attributes={"http.request.header.x_note": ("retry after login password=hunter2",)}))
    assert "hunter2" not in attribute(first_span(buf), "http.request.header.x_note")


SQL_ERROR = (
    "IntegrityError: (psycopg.errors.UniqueViolation) duplicate key value violates unique constraint\n"
    "DETAIL:  Key (email)=(alice@example.com) already exists.\n"
    "[SQL: INSERT INTO users (email, note) VALUES (%(email)s, 'hunter2')]\n"
    "[parameters: {'email': 'alice@example.com'}]"
)


def errored_span(**kwargs: Any) -> Any:
    raw = span(status="ERROR", **kwargs)
    raw.status.description = SQL_ERROR
    return raw


def test_status_message_drops_driver_echoed_values():
    buf = buffer()
    buf.add(errored_span())
    assert "alice@example.com" not in first_span(buf)["statusMessage"]


def test_status_message_normalises_the_sql_statement():
    buf = buffer()
    buf.add(errored_span())
    assert "hunter2" not in first_span(buf)["statusMessage"]


def test_exception_event_message_gets_the_sql_handling():
    buf = buffer()
    buf.add(span(events=[event("exception", 2_000, {"exception.message": SQL_ERROR})]))
    shown = first_span(buf)["events"][0]["attributes"][0]["value"]
    assert "alice@example.com" not in shown


def test_exception_event_stacktrace_gets_the_sql_handling():
    trace = 'Traceback (most recent call last):\n  File "app.py", line 3, in <module>\n' + SQL_ERROR
    buf = buffer()
    buf.add(span(events=[event("exception", 2_000, {"exception.stacktrace": trace})]))
    shown = first_span(buf)["events"][0]["attributes"][0]["value"]
    assert "hunter2" not in shown


CAPTURING = Masker(Exposure.MASKED, True, capture_parameters=True)


def test_db_statement_parameters_hidden_unless_capture_parameters():
    buf = buffer()
    buf.add(span(attributes={"db.statement.parameters": "('alice@example.com',)"}))
    assert attribute(first_span(buf), "db.statement.parameters") == MASK


def test_db_query_parameter_hidden_unless_capture_parameters():
    buf = buffer()
    buf.add(span(attributes={"db.query.parameter.email": "alice@example.com"}))
    assert attribute(first_span(buf), "db.query.parameter.email") == MASK


def test_bind_parameter_attributes_shown_with_capture_parameters():
    buf = buffer(CAPTURING)
    buf.add(span(attributes={"db.query.parameter.email": "alice@example.com"}))
    assert attribute(first_span(buf), "db.query.parameter.email") == "alice@example.com"


def test_full_exposure_without_capture_parameters_still_hides_sql_literals():
    # SQL Trace keys literals on capture_parameters, not on the exposure (review r1)
    buf = buffer(FULL)
    buf.add(span(attributes={"db.statement": "select * from owners where pw = 'hunter2'"}))
    assert attribute(first_span(buf), "db.statement") == "select * from owners where pw = ?"


def test_capture_parameters_shows_sql_literals():
    buf = buffer(CAPTURING)
    buf.add(span(attributes={"db.statement": "select * from owners where name = 'alice'"}))
    assert attribute(first_span(buf), "db.statement") == "select * from owners where name = 'alice'"


def test_detail_applies_the_live_capture_parameters_policy_on_every_read():
    # ported: TracesServiceTests.detailAppliesTheLiveExposurePolicyOnEveryRead (supersedes the FULL-exposure version)
    buf = buffer(CAPTURING)
    buf.add(span(attributes={"db.statement": "select * from owners where name = 'alice'"}))
    first = attribute(first_span(buf), "db.statement")
    buf.masker = MASKED
    second = attribute(first_span(buf), "db.statement")
    assert "alice" in first
    assert "alice" not in second


def test_span_name_goes_through_text_masking():
    buf = buffer()
    buf.add(span(name="login user=alice password=hunter2"))
    assert "hunter2" not in first_span(buf)["name"]


def test_root_span_name_goes_through_text_masking():
    buf = buffer()
    buf.add(span(name="login user=alice password=hunter2"))
    assert "hunter2" not in summary(buf)["rootSpanName"]


def test_event_name_goes_through_text_masking():
    buf = buffer()
    buf.add(span(events=[event("retry token=s3cr3tvalue1", 1_500, {})]))
    assert "s3cr3tvalue1" not in first_span(buf)["events"][0]["name"]


SELF_SERVER = {"url.path": "/sharpit/api/traces"}


def test_spans_of_sharpit_internal_work_never_reach_the_buffer():
    buf = buffer()
    token = INTERNAL.set(True)
    try:
        buf.add(span(kind="CLIENT", name="SELECT"))
    finally:
        INTERNAL.reset(token)
    assert buf.list(100)["retained"] == 0


def test_spans_of_sharpit_event_streams_never_reach_the_buffer():
    buf = buffer()
    token = SSE_TASK.set(True)
    try:
        buf.add(span(kind="INTERNAL", name="stream"))
    finally:
        SSE_TASK.reset(token)
    assert buf.list(100)["retained"] == 0


def test_a_sharpit_server_span_takes_no_capacity():
    buf = SpanBuffer(MASKED, capacity=1, self_path="/sharpit")
    buf.add(span(attributes={"url.path": "/owners"}))
    buf.add(span(trace_id=OTHER, attributes=SELF_SERVER))
    assert [t["traceId"] for t in buf.list(100)["traces"]] == [f"{TRACE:032x}"]


def test_the_self_path_check_strips_the_root_path():
    buf = SpanBuffer(MASKED, capacity=10, self_path="/sharpit", root_path="/proxy")
    buf.add(span(attributes={"url.path": "/proxy/sharpit/api/traces"}))
    assert buf.list(100)["traces"] == []


def test_children_of_a_sharpit_request_take_no_capacity():
    buf = SpanBuffer(MASKED, capacity=1, self_path="/sharpit")
    processor = otel.SharpitSpanProcessor()
    processor.sinks = (buf,)
    processor.on_end(span(attributes={"url.path": "/owners"}))
    server = span(trace_id=OTHER, span_id=1, attributes=SELF_SERVER)
    processor.on_start(server)
    processor.on_end(span(trace_id=OTHER, span_id=2, parent=1, kind="INTERNAL", name="http send"))
    processor.on_end(server)
    assert [t["traceId"] for t in buf.list(100)["traces"]] == [f"{TRACE:032x}"]
