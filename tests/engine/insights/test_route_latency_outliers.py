"""Ported route latency outlier comparisons over the retained HTTP journal."""

from __future__ import annotations

import json
import secrets
from typing import Any

from fastapi.testclient import TestClient
from tests.engine.insights.test_insights_k1 import ORDERS, Run

from fastapi import FastAPI
from sharpit import install

API = "/sharpit/api/runtime-insights"
KIND = "route-latency-outliers"


def _row(run: Run) -> dict[str, Any] | None:
    return next((row for row in run.report()["observations"] if row["kind"] == KIND), None)


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
