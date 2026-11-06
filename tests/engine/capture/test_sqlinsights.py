"""``sqlinsights``: SQL Trace rankings and route attribution (lane A-sqltrace-insights, Task 1).

Ported from BootUI ``SqlTraceInsightsServiceTests``; sharpit offers only the ``TRACE_ID`` correlation (the SQL row's
``traceId`` is the capture middleware's request id, joined to the exchange row's ``id``).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from sharpit.engine.capture.exchanges import HttpExchangeBuffer, exchange_row
from sharpit.engine.capture.sqlinsights import insights_report, mask_route, percentile
from sharpit.engine.capture.sqlscan import normalize
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqla import TRACING_DISABLED
from sharpit.engine.sqltext import Dialect

MASKED = Masker(Exposure.MASKED, True)
WITH_PARAMETERS = Masker(Exposure.MASKED, True, capture_parameters=True)


def _recorder(masker: Masker = MASKED, max_entries: int = 100) -> SqlTraceRecorder:
    return SqlTraceRecorder(masker, max_entries=max_entries)


def _record(recorder: SqlTraceRecorder, sql: str, millis: int, **kw: Any) -> None:
    fields: dict[str, Any] = {"dialect": Dialect.UNSUPPORTED, **kw}
    recorder.record(sql, duration_ns=millis * 1_000_000, thread="main", connection_id="c1", **fields)


def _exchanges(*requests: tuple[str, str, str]) -> HttpExchangeBuffer:
    buffer = HttpExchangeBuffer(100)
    for request_id, method, path in requests:
        buffer.add(
            exchange_row(
                MASKED,
                request_id=request_id,
                started_epoch_ns=1,
                method=method,
                path=path,
                query_string=b"",
                status=200,
                duration_ms=1,
                size=0,
                client=None,
                user=None,
                request_headers=[],
                response_headers=[],
            )
        )
    return buffer


def test_reports_unavailable_when_tracing_is_off():
    # ported: SqlTraceInsightsServiceTests.reportsUnavailableWhenTracingIsOff
    report = insights_report(None, _exchanges(), TRACING_DISABLED)
    assert report["available"] is False
    assert report["unavailableReason"] == TRACING_DISABLED
    assert report["statements"] == []
    assert report["attribution"]["available"] is False


def test_still_ranks_statements_when_the_runtime_cannot_supply_request_evidence():
    # ported: SqlTraceInsightsServiceTests.stillRanksStatementsWhenTheRuntimeCannotSupplyRequestEvidence
    recorder = _recorder()
    _record(recorder, "select * from orders where id = 1", 30)
    report = insights_report(recorder, None, None)
    assert report["available"] is True
    assert len(report["statements"]) == 1
    assert report["attribution"]["available"] is False
    assert report["attribution"]["routes"] == []
    assert report["attribution"]["unattributed"]["executions"] == 0


def test_describes_the_bounded_window_the_rankings_cover():
    # ported: SqlTraceInsightsServiceTests.describesTheBoundedWindowTheRankingsCover
    recorder = _recorder()
    _record(recorder, "select * from a where id = 1", 30)
    _record(recorder, "select * from a where id = 2", 10)
    report = insights_report(recorder, _exchanges(), None)
    window = report["window"]
    assert window["retainedStatements"] == 2
    assert window["bufferSize"] == 100
    assert window["totalCaptured"] == 2
    assert window["totalDurationMillis"] == 40
    assert window["oldestTimestamp"] is not None
    assert window["newestTimestamp"] is not None
    assert report["distinctStatements"] == 1
    assert report["topPerCriterion"] == 10


def test_warns_when_older_executions_have_already_been_evicted():
    # ported: SqlTraceInsightsServiceTests.warnsWhenOlderExecutionsHaveAlreadyBeenEvicted
    recorder = _recorder(max_entries=2)
    for sql in ("select 1", "select 2", "select 3"):
        _record(recorder, sql, 5)
    report = insights_report(recorder, _exchanges(), None)
    assert report["window"]["retainedStatements"] == 2
    assert report["window"]["evicted"] == 1
    assert any("aged out" in note for note in report["notes"])


def test_says_the_figures_describe_the_retained_window_rather_than_lifetime_totals():
    # ported: SqlTraceInsightsServiceTests.saysTheFiguresDescribeTheRetainedWindowRatherThanLifetimeTotals
    recorder = _recorder()
    _record(recorder, "select 1", 5)
    report = insights_report(recorder, _exchanges(), None)
    assert any("not lifetime metrics" in note for note in report["notes"])


def test_reports_paused_recording_so_a_stale_window_is_not_mistaken_for_a_quiet_system():
    # ported: SqlTraceInsightsServiceTests.reportsPausedRecordingSoAStaleWindowIsNotMistakenForAQuietSystem
    recorder = _recorder()
    _record(recorder, "select 1", 5)
    recorder.set_recording(False)
    report = insights_report(recorder, _exchanges(), None)
    assert report["capturing"] is False
    assert any("paused" in note for note in report["notes"])


def test_never_exposes_bound_parameters_even_when_capture_is_on():
    # ported: SqlTraceInsightsServiceTests.neverExposesBoundParametersEvenWhenParameterCaptureIsOn
    recorder = _recorder(WITH_PARAMETERS)
    _record(recorder, "select * from users where email = 'ada@example.com'", 5)
    _record(recorder, "select * from users where email = ?", 5, parameters=("ada@example.com",))
    report = insights_report(recorder, _exchanges(), None)
    assert [s["sql"] for s in report["statements"]] == ["select * from users where email = ?"]
    assert "ada@example.com" not in json.dumps(report)


def test_attributes_recorded_statements_to_the_supplied_requests():
    # ported: SqlTraceInsightsServiceTests.attributesRecordedStatementsToTheSuppliedRequests
    recorder = _recorder()
    _record(recorder, "select * from orders", 12, request_id="r1")
    report = insights_report(recorder, _exchanges(("r1", "GET", "/api/orders")), None)
    attribution = report["attribution"]
    assert [r["route"] for r in attribution["routes"]] == ["/api/orders"]
    assert attribution["supportedCorrelations"] == ["TRACE_ID"]
    assert attribution["routes"][0]["traceCorrelated"] == 1


def test_rankings_are_deterministic_on_ties():
    recorder = _recorder()
    for sql in ("select * from b", "select * from a", "select * from c"):
        _record(recorder, sql, 4)
    first = insights_report(recorder, _exchanges(), None)
    second = insights_report(recorder, _exchanges(), None)
    assert [s["id"] for s in first["statements"]] == ["select * from a", "select * from b", "select * from c"]
    assert json.dumps(first) == json.dumps(second)


def test_unattributed_bucket_reason():
    recorder = _recorder()
    _record(recorder, "select 1", 3)  # outside any request
    _record(recorder, "select 2", 3, request_id="evicted")  # its exchange is no longer retained
    report = insights_report(recorder, _exchanges(("r1", "GET", "/orders")), None)
    attribution = report["attribution"]
    assert attribution["routes"] == []
    assert attribution["unattributed"]["executions"] == 2
    assert attribution["unattributed"]["reason"].startswith("No captured request could have issued these statements")


def test_top_for_names_the_criteria_verbatim():
    recorder = _recorder()
    _record(recorder, "select 1", 3, success=False)
    report = insights_report(recorder, _exchanges(), None)
    assert [s["topFor"] for s in report["statements"]] == [
        ["TOTAL_DURATION", "MAX_DURATION", "EXECUTIONS", "AVG_DURATION", "ERROR_COUNT", "P95_DURATION", "P99_DURATION"]
    ]


def test_only_the_top_ten_per_criterion_are_listed():
    recorder = _recorder()
    for table in range(15):
        _record(recorder, f"select * from t{table:02d}", 1)
    report = insights_report(recorder, _exchanges(), None)
    assert len(report["statements"]) == 10
    assert report["statementsTruncated"] is True
    assert report["distinctStatements"] == 15
    assert any(note.startswith("Only the top 10 statements per ranking criterion") for note in report["notes"])


def test_route_without_template_is_grouped_by_masked_path():
    recorder = _recorder()
    _record(recorder, "select * from orders where id = 7", 2, request_id="r1")
    _record(recorder, "select * from orders where id = 8", 2, request_id="r2")
    exchanges = _exchanges(("r1", "get", "/orders/7"), ("r2", "GET", "/orders/8"))
    routes = insights_report(recorder, exchanges, None)["attribution"]["routes"]
    assert [(r["id"], r["routeSource"], r["requests"]) for r in routes] == [("GET /orders/{value}", "MASKED_PATH", 2)]


def test_n_plus_one_flag_on_repeated_select():
    recorder = _recorder()
    for _ in range(5):
        _record(recorder, "select * from pets where owner_id = 1", 1)
    statements = insights_report(recorder, _exchanges(), None)["statements"]
    assert [s["potentialNPlusOne"] for s in statements] == [True]


def test_percentile_is_nearest_rank():
    assert percentile(list(range(1, 21)), 95) == 19


@pytest.mark.parametrize("dialect", [Dialect.POSTGRESQL, Dialect.MYSQL_FAMILY, Dialect.UNSUPPORTED])
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM users WHERE id = 1",
        "select * from users where password = 'hunter2'",
        "UPDATE t SET token = 'abc' WHERE id = 2",
        "select * from t where api_key = 'abc' and id = 7",
    ],
    ids=["number", "password", "token", "key"],
)
def test_other_dialects_rank_by_the_stored_text_normalized(dialect: Dialect, sql: str):
    """Task 19 moves SQLite's identity only: elsewhere the stored text, normalized again, stays the id."""
    recorder = _recorder(WITH_PARAMETERS)
    _record(recorder, sql, 4, dialect=dialect)
    [row] = insights_report(recorder, _exchanges(), None)["statements"]
    stored = WITH_PARAMETERS.mask_text(sql)
    assert stored is not None
    assert row["id"] == normalize(stored, dialect).fingerprint


def test_a_sqlite_statement_with_no_identity_is_not_ranked():
    recorder = _recorder()  # no key: ruling 4, not grouped
    _record(recorder, 'select "id" from "users"', 4, dialect=Dialect.SQLITE)
    _record(recorder, 'select "id" from "orders"', 4, dialect=Dialect.SQLITE)
    assert insights_report(recorder, _exchanges(), None)["statements"] == []


def test_mask_route_masks_value_segments():
    assert mask_route("/orders/123/items/null/a1b2/report.pdf") == "/orders/{value}/items/{value}/{value}/report.pdf"
