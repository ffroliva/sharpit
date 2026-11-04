"""The activity, exceptions and sql-trace main reports against their 2.2.0 goldens, with rows in them.

An empty report proves nothing here: the golden's item keys are only reached once a list has items.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from golden import ROOT, assert_parity  # noqa: E402
from sharpit import install  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api"


@pytest.fixture
def client(tmp_path: Any) -> Iterator[TestClient]:
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    def query(n: int) -> dict[str, int]:
        with engine.connect() as connection:
            connection.execute(sa.text("select 1"))
        return {"n": n}

    def boom() -> None:
        raise RuntimeError("capture parity")

    app = FastAPI()
    app.add_api_route("/q/{n}", query)
    app.add_api_route("/boom", boom)
    install(app, enabled="ON", show_banner=False, state_dir=str(tmp_path), engines=[engine])
    with TestClient(
        app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False, follow_redirects=False
    ) as test_client:
        assert test_client.get("/q/7").status_code == 200
        assert test_client.get("/boom").status_code == 500
        yield test_client


def _report(client: TestClient, panel: str) -> dict[str, Any]:
    response = client.get(f"{API}/{panel}")
    assert response.status_code == 200
    return response.json()


def _request_id(client: TestClient, path: str) -> str:
    rows = _report(client, "http-exchanges")["exchanges"]
    return next(row["requestId"] for row in rows if row["path"] == path)


def _golden_type_counts() -> dict[str, int]:
    return json.loads((ROOT / "activity" / "captured.json").read_text(encoding="utf-8"))["typeCounts"]


def test_activity_report_populated_golden_parity(client: TestClient):
    report = _report(client, "activity")
    counts = report["typeCounts"]
    assert counts["REQUEST"] == 2
    assert counts["SQL"] >= 1
    assert counts["EXCEPTION"] == 1
    # typeCounts maps the types seen, so the golden's keys are that capture's data, not DTO keys: sharpit's feed has no
    # TRANSACTION, SECURITY, MESSAGING or MARKER entries. An unknown type would still fail here.
    assert set(counts) <= set(_golden_type_counts())
    assert_parity("activity", "captured", {**report, "typeCounts": {**_golden_type_counts(), **counts}})


def test_activity_exception_entry_names_its_group(client: TestClient):
    group = _report(client, "exceptions")["groups"][0]
    entries = _report(client, "activity")["entries"]
    entry = next(e for e in entries if e["type"] == "EXCEPTION")
    assert "exceptionGroupId" in entry
    assert entry["exceptionGroupId"] == group["id"]


def test_activity_entries_outside_an_exception_have_no_group_and_no_badges(client: TestClient):
    entries = [e for e in _report(client, "activity")["entries"] if e["type"] != "EXCEPTION"]
    assert entries
    assert all("exceptionGroupId" in e for e in entries)
    assert all("badges" in e for e in entries)
    assert {e["exceptionGroupId"] for e in entries} == {None}
    assert [e["badges"] for e in entries] == [[] for _ in entries]


def test_activity_kpis_count_the_latency_samples(client: TestClient):
    kpis = _report(client, "activity")["kpis"]
    assert "latencySampleCount" in kpis
    assert kpis["latencySampleCount"] == 2


def test_activity_kpis_name_the_slowest_route(client: TestClient):
    kpis = _report(client, "activity")["kpis"]
    assert "slowestEndpointRoute" in kpis
    route = {"/q/7": "/q/{n}", "/boom": "/boom"}[kpis["slowestEndpoint"]]
    assert kpis["slowestEndpointRoute"] == route
    assert kpis["slowestEndpointRouteId"] == f"GET {route}"
    assert kpis["slowestEndpointRouteSource"] == "FRAMEWORK_TEMPLATE"


def test_activity_kpis_without_a_request_have_no_route():
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    kpis = TestClient(app, base_url="http://localhost", client=LOCAL).get(f"{API}/activity").json()["kpis"]
    assert "latencySampleCount" in kpis
    assert kpis["latencySampleCount"] == 0
    assert kpis["slowestEndpointRoute"] is None
    assert kpis["slowestEndpointRouteId"] is None
    assert kpis["slowestEndpointRouteSource"] is None


def test_exceptions_report_populated_golden_parity(client: TestClient):
    report = _report(client, "exceptions")
    assert report["groups"]
    assert_parity("exceptions", "captured", report)


def test_exceptions_group_carries_the_last_request_id(client: TestClient):
    group = _report(client, "exceptions")["groups"][0]
    assert "lastRequestId" in group
    assert group["lastRequestId"] == _request_id(client, "/boom")
    assert group["lastExecutionId"] is None


def test_exception_logged_outside_a_request_keeps_golden_parity(client: TestClient):
    try:
        raise ValueError("outside any request")
    except ValueError:
        logging.getLogger("capture.parity").exception("logged outside a request")
    report = _report(client, "exceptions")
    outside = [g for g in report["groups"] if g["exceptionClassName"].endswith("ValueError")]
    assert len(outside) == 1
    assert "lastRequestId" in outside[0]
    assert outside[0]["lastRequestId"] is None
    assert_parity("exceptions", "captured", report)


def test_sql_trace_report_populated_golden_parity(client: TestClient):
    report = _report(client, "sql-trace")
    assert report["entries"]
    assert_parity("sql-trace", "captured", report)


def test_sql_trace_timestamp_is_epoch_ms(client: TestClient):
    before = time.time_ns() // 1_000_000
    assert client.get("/q/8").status_code == 200
    after = time.time_ns() // 1_000_000
    stamp = _report(client, "sql-trace")["entries"][0]["timestamp"]
    assert isinstance(stamp, int)
    assert before <= stamp <= after


def test_sql_trace_entry_carries_its_request_id(client: TestClient):
    entry = _report(client, "sql-trace")["entries"][0]
    assert "requestId" in entry
    assert entry["requestId"] == _request_id(client, "/q/7")


def test_request_profile_sql_rows_use_epoch_ms_and_the_new_keys(client: TestClient):
    profile = _report(client, f"activity/request/{_request_id(client, '/q/7')}")
    row = profile["sql"][0]
    assert isinstance(row["timestamp"], int)
    assert row["requestId"] == _request_id(client, "/q/7")
    assert (row["executionId"], row["threadKind"], row["requestPhase"]) == (None, None, None)
