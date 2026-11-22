"""Ported route latency outlier comparisons over the retained HTTP journal."""

from __future__ import annotations

import json
import secrets
from typing import Any

from fastapi.testclient import TestClient
from tests.engine.insights.test_insights_k1 import ORDERS, Run

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights import snapshot as snapshot_module
from sharpit.engine.collectors.insights.registry import KINDS
from sharpit.engine.collectors.insights.snapshot import project

API = "/sharpit/api/runtime-insights"
KIND = "route-latency-outliers"


def _row(run: Run) -> dict[str, Any] | None:
    return next((row for row in run.report()["observations"] if row["kind"] == KIND), None)


def _evaluate_child_evidence(
    source: str,
    evidence: dict[str, object] | None,
    supporting_evidence: tuple[str, dict[str, object]] | None = None,
    baseline_evidence: dict[str, object] | None = None,
    baseline_source: str | None = None,
) -> Any | None:
    sources = {"http", "sql", "connection", "cache", "rest-client", "orm"}
    journal = RuntimeJournal(sources=sources)
    for index, duration in enumerate((350, 15, 15, 15, 15, 15, 240), start=1):
        start = index * 1_000_000_000
        route = ORDERS.partition(" ")[2]
        info = RequestInfo(f"r{index}", "ctx", "GET", "/api/orders/42", route, start, start + duration * 1_000_000)
        journal.offer(http_event(info, [], 1_700_000_000_000 + index * 1000, 200, route))
    if evidence is not None:
        journal.offer({**evidence, "source": source, "requestId": "r7"})
    if baseline_evidence is not None:
        journal.offer({**baseline_evidence, "source": baseline_source or source, "requestId": "r6"})
    if supporting_evidence is not None:
        journal.offer({**supporting_evidence[1], "source": supporting_evidence[0], "requestId": "r7"})
    observation = next(kind for kind in KINDS if kind.kind == KIND)
    findings = observation.evaluate(project(journal)).findings
    return findings[0] if findings else None


def _record_optional_sources(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        snapshot_module,
        "PRODUCED_SOURCES",
        snapshot_module.PRODUCED_SOURCES | {"connection", "cache", "rest-client", "orm"},
    )


def test_connection_evidence_requires_a_recorded_child_and_reports_wait(monkeypatch: Any) -> None:
    _record_optional_sources(monkeypatch)
    assert _evaluate_child_evidence("connection", None) is None
    finding = _evaluate_child_evidence("connection", {"waitNanos": 20_000_000})
    assert finding is not None
    assert "20 ms connection wait" in finding.sentence


def test_cache_evidence_requires_a_recorded_child_and_reports_misses(monkeypatch: Any) -> None:
    _record_optional_sources(monkeypatch)
    assert _evaluate_child_evidence("cache", None) is None
    finding = _evaluate_child_evidence("cache", {"operation": "MISS"})
    assert finding is not None
    assert "+1 cache miss" in finding.sentence


def test_rest_evidence_requires_a_recorded_child_and_reports_calls(monkeypatch: Any) -> None:
    _record_optional_sources(monkeypatch)
    assert _evaluate_child_evidence("rest-client", None) is None
    finding = _evaluate_child_evidence("rest-client", {"durationNanos": 12_000_000})
    assert finding is not None
    assert "+1 REST client call (+12 ms)" in finding.sentence


def test_rest_evidence_compares_duration_when_call_counts_match(monkeypatch: Any) -> None:
    _record_optional_sources(monkeypatch)
    finding = _evaluate_child_evidence(
        "rest-client",
        {"durationNanos": 15_000_000},
        baseline_evidence={"durationNanos": 1_000_000},
    )
    assert finding is not None
    assert "+14 ms in REST client calls" in finding.sentence


def test_orm_evidence_requires_a_recorded_child_and_reports_flushes(monkeypatch: Any) -> None:
    _record_optional_sources(monkeypatch)
    assert _evaluate_child_evidence("orm", None) is None
    finding = _evaluate_child_evidence("orm", {"flushes": 1, "partialFlushes": 1, "entitiesInContext": 8})
    assert finding is not None
    assert "+1 auto-flush" in finding.sentence


def test_orm_entity_counts_stay_unknown_when_any_orm_evidence_is_unmeasured(monkeypatch: Any) -> None:
    _record_optional_sources(monkeypatch)
    finding = _evaluate_child_evidence(
        "cache",
        {"operation": "MISS"},
        ("orm", {"entitiesInContext": -1}),
        {"entitiesInContext": 3},
        baseline_source="orm",
    )
    assert finding is not None
    assert "Peak entities in context" not in [row[0] for row in finding.rows]


def test_orm_flushes_without_auto_flushes_are_reported(monkeypatch: Any) -> None:
    _record_optional_sources(monkeypatch)
    finding = _evaluate_child_evidence("orm", {"flushes": 1, "partialFlushes": 0})
    assert finding is not None
    assert "+1 Hibernate flush" in finding.sentence


def test_orm_entity_counts_below_baseline_are_rows_but_not_highlights(monkeypatch: Any) -> None:
    _record_optional_sources(monkeypatch)
    finding = _evaluate_child_evidence(
        "orm",
        {"flushes": 1, "entitiesInContext": 7},
        ("cache", {"operation": "MISS"}),
        {"flushes": 1, "entitiesInContext": 8},
    )
    assert finding is not None
    assert [row for row in finding.rows if row[0] == "Peak entities in context"] == [
        ["Peak entities in context", "7", "8", "-1"]
    ]


def test_sql_execution_without_a_statement_still_proves_the_call(monkeypatch: Any) -> None:
    _record_optional_sources(monkeypatch)
    finding = _evaluate_child_evidence("sql", {"provenance": "EXECUTION", "durationNanos": 15_000_000, "sql": ""})
    assert finding is not None
    assert "+1 SQL execution (+15 ms)" in finding.sentence


# ported: RouteLatencyOutliersTests.comparesRouteSlowestOutlierAgainstClosestWarm2xxBaselineAndExcludesColdFirstRequest
def test_route_latency_outliers_uses_warm_median_threshold_and_excludes_first_request() -> None:
    run = Run()
    try:
        run.request(ORDERS, 350)  # the slow first retained request is cold, never an outlier
        warm_ids = [run.request(ORDERS, 15, (2, 1)) for _ in range(5)]
        outlier = run.request(ORDERS, 115, (2, 1), (4, 1), (6, 1))
        row = _row(run)
        assert row is not None
        assert row["status"] == "OBSERVED"
        assert row["subject"] == ORDERS
        assert row["exemplarRequestIds"] == [outlier, warm_ids[-1]]
        assert "+2 SQL executions" in row["sentence"]
        rows = run.cells(row)
        assert [cells[0] for cells in rows] == ["Request", "Duration (ms)", "SQL executions", "Distinguishing SQL"]
        assert rows[-1][1] == "select ?"
    finally:
        run.close()


def test_route_latency_outliers_uses_four_times_the_warm_median() -> None:
    run = Run()
    try:
        run.request(ORDERS, 350)
        for _ in range(5):
            run.request(ORDERS, 150, (2, 1))
        run.request(ORDERS, 600, (2, 1), (4, 1), (6, 1))
        row = _row(run)
        assert row is not None
        assert "warm median 150 ms" in row["sentence"]
        assert "+2 SQL executions" in row["sentence"]
    finally:
        run.close()


def test_route_latency_outliers_reports_preliminary_evidence_before_five_warm_requests() -> None:
    run = Run()
    try:
        run.request(ORDERS, 350)
        run.request(ORDERS, 15, (2, 1))
        run.request(ORDERS, 240, (2, 1), (4, 1))
        row = _row(run)
        assert row is not None
        assert row["status"] == "INSUFFICIENT"
        assert "comparing against a warm baseline needs 5" in row["sentence"]
    finally:
        run.close()


def test_route_latency_outliers_requires_a_child_work_difference() -> None:
    run = Run()
    try:
        run.request(ORDERS, 15)
        for _ in range(5):
            run.request(ORDERS, 15)
        run.request(ORDERS, 115)
        assert _row(run) is None
    finally:
        run.close()


def test_route_latency_outliers_groups_case_insensitive_sql_shapes() -> None:
    run = Run()
    try:
        run.request(ORDERS, 350)
        for _ in range(5):
            run.request(ORDERS, 15, (2, 1), text="select 1")
        run.request(ORDERS, 115, (2, 1), text="SELECT 1")
        assert _row(run) is None
    finally:
        run.close()


def test_route_latency_outliers_optional_sources_can_be_unavailable() -> None:
    run = Run(("http",))
    try:
        run.request(ORDERS, 15)
        for _ in range(5):
            run.request(ORDERS, 15)
        run.request(ORDERS, 240)
        assert _row(run) is None
        check = next(c for c in run.report()["checks"] if c["kind"] == KIND)
        assert check["status"] == "EVALUATED"
    finally:
        run.close()


def test_route_latency_outliers_output_uses_the_masked_route() -> None:
    run = Run()
    try:
        canary = secrets.token_hex(16)
        run.request(ORDERS, 15, path=f"/api/orders/{canary}", matched=False)
        for _ in range(5):
            run.request(ORDERS, 15, (2, 1), path=f"/api/orders/{canary}", matched=False)
        run.request(ORDERS, 240, (2, 1), (4, 1), path=f"/api/orders/{canary}", matched=False)
        report = json.dumps(run.report())
        assert canary not in report
        assert _row(run) is not None
    finally:
        run.close()


def test_route_latency_outliers_read_has_no_side_effects(no_side_effects: Any) -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop opens a self-pipe socket.
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), follow_redirects=False)
    assert client.get(API).status_code == 200
    assert no_side_effects.violations == []
