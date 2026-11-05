"""The span buffer and the trace DTOs (lane A-traces, Task 2; BootUI ``TracesServiceTests``).

Spans are SDK-``ReadableSpan``-shaped fakes: the SDK is not a test dependency and the buffer reads spans duck-typed.
"""

from __future__ import annotations

import sys
import time
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from sharpit.engine import otel
from sharpit.engine.capture import traces
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


def test_span_reads_mask_nested_values():
    # ported: TracesServiceTests.spanReadsMaskNestedValuesWithoutChangingStoredEvidence
    raw = span(
        attributes={
            "http.request.header.authorization": ("Bearer abc.def.ghi",),
            "db.statement": "select 1 from t where token = 'sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc'",
        },
        events=[event("exception", 2_000, {"exception.message": "login failed password=hunter2"})],
    )
    buf = buffer()
    buf.add(raw)
    detail = buf.detail(f"{TRACE:032x}")
    assert detail is not None
    text = str(detail)
    assert "abc.def.ghi" not in text
    assert "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc" not in text
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


def test_double_quoted_value_in_db_statement_is_a_placeholder():
    # 0.3.0 leak: a double-quoted value (MySQL string literal) passed through normalize_sql verbatim
    buf = buffer()
    buf.add(span(attributes={"db.statement": 'select * from owners where pw = "hunter2"'}))
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


@pytest.mark.parametrize("separator", ["\r", "\r\n", "\u2028", "\x85"])
def test_sql_exception_message_drops_driver_detail_for_line_separators(separator: str):
    message = (
        "(psycopg.errors.UniqueViolation) duplicate key value violates unique constraint"
        + separator
        + "DETAIL:  Key (email)=(alice@example.com) already exists."
        + separator
        + "[SQL: INSERT INTO users (email) VALUES (%(email)s)]"
    )
    buf = buffer()
    buf.add(span(events=[event("exception", 2_000, {"exception.message": message})]))
    shown = first_span(buf)["events"][0]["attributes"][0]["value"]
    assert "alice@example.com" not in shown


def test_exception_event_stacktrace_gets_the_sql_handling():
    trace = 'Traceback (most recent call last):\n  File "app.py", line 3, in <module>\n' + SQL_ERROR
    buf = buffer()
    buf.add(span(events=[event("exception", 2_000, {"exception.stacktrace": trace})]))
    shown = first_span(buf)["events"][0]["attributes"][0]["value"]
    assert "hunter2" not in shown


def test_sql_exception_stacktrace_keeps_python_frames():
    trace = 'Traceback (most recent call last):\n  File "app.py", line 3, in <module>\n' + SQL_ERROR
    buf = buffer()
    buf.add(span(events=[event("exception", 2_000, {"exception.stacktrace": trace})]))
    shown = first_span(buf)["events"][0]["attributes"][0]["value"]
    assert 'File "app.py", line 3' in shown


def test_non_sql_stacktrace_keeps_its_frames():
    trace = 'Traceback (most recent call last):\n  File "app.py", line 3, in <module>\nValueError: boom'
    buf = buffer()
    buf.add(span(events=[event("exception", 2_000, {"exception.stacktrace": trace})]))
    shown = first_span(buf)["events"][0]["attributes"][0]["value"]
    assert shown == trace


def test_non_sql_exception_message_uses_text_masking_only():
    message = "ValueError: invalid literal for int() with base 10: 'abc'"
    buf = buffer()
    buf.add(span(events=[event("exception", 2_000, {"exception.message": message})]))
    shown = first_span(buf)["events"][0]["attributes"][0]["value"]
    assert shown == message


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


def plant_provider(monkeypatch: pytest.MonkeyPatch, provider: Any) -> ModuleType:
    trace = ModuleType("opentelemetry.trace")
    trace._TRACER_PROVIDER = provider  # type: ignore[attr-defined]
    trace.get_tracer_provider = lambda: provider  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", ModuleType("opentelemetry.sdk.trace"))
    monkeypatch.setattr(otel, "PROCESSOR", otel.SharpitSpanProcessor())
    return trace


def sdk_provider() -> Any:
    provider = SimpleNamespace(processors=[])
    provider.add_span_processor = provider.processors.append
    return provider


def test_reason_when_the_attacher_never_ran(monkeypatch: pytest.MonkeyPatch):
    # review r1: no lifespan and no capture middleware means no attach chance; that is not a late provider
    plant_provider(monkeypatch, sdk_provider())
    assert buffer().list(100)["unavailableReason"] == traces.NEVER_ATTACHED


def test_reason_after_detach(monkeypatch: pytest.MonkeyPatch):
    plant_provider(monkeypatch, sdk_provider())
    buf = buffer()
    remover = buf.arm()
    assert remover is not None
    remover()
    assert buf.list(100)["unavailableReason"] == traces.DETACHED


def test_reason_when_the_provider_was_set_late(monkeypatch: pytest.MonkeyPatch):
    trace = plant_provider(monkeypatch, None)
    trace.get_tracer_provider = lambda: None  # type: ignore[attr-defined]
    buf = buffer()
    assert buf.arm() is None
    provider = sdk_provider()
    trace._TRACER_PROVIDER = provider  # type: ignore[attr-defined]
    trace.get_tracer_provider = lambda: provider  # type: ignore[attr-defined]
    assert buf.list(100)["unavailableReason"] == traces.NOT_ARMED


# derived: release council fix round 2: an OTel span names its database, so its text is read as that database's
@pytest.mark.parametrize("key", ["db.system", "db.system.name"])
@pytest.mark.parametrize("system", ["mysql", "mariadb"])
def test_mysql_span_statement_uses_the_mysql_scan(key: str, system: str):
    buf = buffer()
    buf.add(span(attributes={key: system, "db.statement": "select 1 # password hunter2"}))

    detail = buf.detail(f"{TRACE:032x}")

    assert detail is not None
    assert attribute(detail["spans"][0], "db.statement") == "select ?"


def test_mysql_span_sql_error_uses_the_mysql_scan():
    buf = buffer()
    message = "(pymysql.err.ProgrammingError) (1064, 'x')\n[SQL: select 0xDEADBEEF]"
    buf.add(span(attributes={"db.system": "mysql", "exception.message": message}))

    detail = buf.detail(f"{TRACE:032x}")

    assert detail is not None
    assert "DEADBEEF" not in attribute(detail["spans"][0], "exception.message")


def test_a_span_of_another_database_keeps_the_generic_scan():
    buf = buffer()
    buf.add(span(attributes={"db.system": "postgresql", "db.statement": "select a # b from t"}))

    detail = buf.detail(f"{TRACE:032x}")

    assert detail is not None
    assert attribute(detail["spans"][0], "db.statement") == "select a # b from t"


# derived: release council probe p3_sql.py: an HTTP span has no ``db.system``, its error still names the driver
@pytest.mark.parametrize(
    "driver",
    [
        "pymysql.err.ProgrammingError",
        "MySQLdb.ProgrammingError",
        "MySQLdb._exceptions.ProgrammingError",
        "mysql.connector.errors.ProgrammingError",
        "asyncmy.errors.ProgrammingError",
        "mariadb.ProgrammingError",
    ],
)
@pytest.mark.parametrize("key", ["exception.message", "exception.stacktrace"])
def test_a_mysql_driver_error_on_a_span_without_a_database_uses_the_mysql_scan(driver: str, key: str):
    buf = buffer()
    message = f"({driver}) (1064, 'x')\n[SQL: select 0xDEADBEEF # password hunter2\nfrom t]"
    buf.add(span(attributes={"http.route": "/x", key: message}))

    detail = buf.detail(f"{TRACE:032x}")

    assert detail is not None
    assert "hunter2" not in attribute(detail["spans"][0], key)


def test_a_postgres_driver_error_on_a_span_without_a_database_keeps_the_generic_scan():
    buf = buffer()
    message = "(psycopg.errors.SyntaxError) x\n[SQL: select a # b from t]"
    buf.add(span(attributes={"http.route": "/x", "exception.message": message}))

    detail = buf.detail(f"{TRACE:032x}")

    assert detail is not None
    assert "[SQL: select a # b from t]" in attribute(detail["spans"][0], "exception.message")


# derived: this round's regex audit: ``[SQL: `` with no ``]`` after it scanned to the end from every occurrence
@pytest.mark.parametrize("text", ["[SQL: " * 15_000, "] " + "[SQL: " * 15_000], ids=["no-closer", "closer-first"])
def test_sql_error_scan_stays_fast_without_a_closer(text: str):
    buf = buffer()
    buf.add(span(attributes={"exception.message": text}))

    started = time.process_time()
    detail = buf.detail(f"{TRACE:032x}")

    assert time.process_time() - started < 1
    assert detail is not None


# derived: delete-the-control on the substitution: a closed ``[SQL: `` lets the unclosed ones after it reach the sub
def test_sql_error_scan_stays_fast_after_a_closed_statement():
    buf = buffer()
    buf.add(span(attributes={"exception.message": "[SQL: select 1] " + "[SQL: " * 15_000}))

    started = time.process_time()
    detail = buf.detail(f"{TRACE:032x}")

    assert time.process_time() - started < 1
    assert detail is not None


def shown_message(message: str) -> str:
    buf = buffer()
    buf.add(span(attributes={"exception.message": message}))
    detail = buf.detail(f"{TRACE:032x}")
    assert detail is not None
    return attribute(detail["spans"][0], "exception.message")


BACKGROUND = "(Background on this error at: https://sqlalche.me/e/20/f405)"
BACKGROUND_NORMALISED = "(Background on this error at: https://sqlalche.me/e/?/f405)"


# derived: release council fix round 3, p_first_bracket.py: the block ended at the first ``]``, a subscript's, and the
# literals after it were neither normalised nor masked
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("(a.Error) x\n[SQL: SELECT a[1], 'hunter2' FROM t]", "(a.Error) x\n[SQL: SELECT a[?], ? FROM t]"),
        ("(a.Error) x\n[SQL: SELECT ARRAY[1], 4111111111111111]", "(a.Error) x\n[SQL: SELECT ARRAY[?], ?]"),
        ("(a.Error) x\n[SQL: SELECT a[1]\n, 'hunter2' FROM t]", "(a.Error) x\n[SQL: SELECT a[?] , ? FROM t]"),
        (
            f"(a.Error) x\n[SQL: SELECT a[1], 'hunter2']\n[parameters: ('p4ss', [1])]\n{BACKGROUND}",
            f"(a.Error) x\n[SQL: SELECT a[?], ?] [parameters: {MASK}] {BACKGROUND_NORMALISED}",
        ),
        (
            "(a.Error) x\n[SQL: SELECT a[1], 'hunter2']\n[SQL parameters hidden due to hide_parameters=True]",
            "(a.Error) x\n[SQL: SELECT a[?], ?] [SQL parameters hidden due to hide_parameters=?]",
        ),
        (
            "(a.Error) x\n[SQL: SELECT a[1], 'one']\n(b.Error) y\n[SQL: SELECT b[2], 'two']",
            "(a.Error) x\n[SQL: SELECT a[?], ?] (b.Error) y [SQL: SELECT b[?], ?]",
        ),
        (
            "(a.Error) x\n[SQL: SELECT a[1], 'one']\nThe above exception was the direct cause of [this]",
            "(a.Error) x\n[SQL: SELECT a[?], ?] The above exception was the direct cause of [this]",
        ),
        ("(a.Error) x\n[SQL: SELECT 'hunter2'", "(a.Error) x\n[SQL: SELECT ?"),
    ],
    ids=["subscript", "array", "multi-line", "parameters", "hidden", "two-blocks", "text-after", "no-closer"],
)
def test_sql_error_block_runs_past_a_bracket_in_the_statement(message: str, expected: str):
    assert shown_message(message) == expected


@pytest.mark.parametrize(
    "text",
    ["[SQL: a[1] " * 15_000, "[SQL: x]\n[parameters: y]\n" * 4_000, "\n[SQL: " * 15_000],
    ids=["inline-blocks", "closed-blocks", "line-blocks"],
)
def test_sql_error_block_scan_stays_fast(text: str):
    started = time.process_time()
    shown_message(text)
    assert time.process_time() - started < 1
