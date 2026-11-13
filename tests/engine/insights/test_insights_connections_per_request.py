"""Runtime Insights ``connections-per-request`` over the journal's ``http`` and ``connection`` sources.

BootUI ``ConnectionsPerRequest.java:24-41`` (evaluation) and ``:101-132`` (``maxHeldTogether``). The synthetic runs
write the connection event with the keys the P-connection producer writes (``sqla/connections._offer``); the
real-install test runs a FastAPI app on a pooled sqlite file engine, so the producer, the join and the pool size are the
production ones.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.masking import Exposure, Masker

KIND = "connections-per-request"
MS = 1_000_000
Row = dict[str, Any]
PoolSizes = Callable[[str], int | None]


def connection(data_source: str | None, checkout_ns: int, held_ns: int) -> Row:
    """``ObservationFixtures.connection``: a connection of ``data_source`` held ``held_ns`` from ``checkout_ns``."""
    return {
        "source": "connection", "epochMillis": 1, "durationNanos": held_ns, "traceId": None, "thread": "MainThread",
        "failedOrSlow": False, "dataSource": data_source, "waitNanos": 0, "statements": 1, "checkoutNanos": checkout_ns,
    }  # fmt: skip


class Run:
    def __init__(self, exposure: Exposure = Exposure.MASKED, pool_sizes: PoolSizes | None = None) -> None:
        self.journal = RuntimeJournal(masker=Masker(exposure, True))
        self.requests = 0
        self.pool_sizes = pool_sizes

    def request(self, route: str, *children: Row) -> str:
        self.requests += 1
        request_id = f"r{self.requests}"
        method, _, template = route.partition(" ")
        info = RequestInfo(request_id, "ctx", method, template, None, 0, 30_000_000)
        for child in children:
            self.journal.offer({**child, "requestId": request_id})
        self.journal.offer(http_event(info, [], 1_000_000, 200, template))
        return request_id

    def service(self) -> InsightsService:
        return InsightsService(self.journal, pool_sizes=self.pool_sizes)

    def check(self) -> Row:
        return next(c for c in self.service().report()["checks"] if c["kind"] == KIND)

    def rows(self) -> list[Row]:
        return [o for o in self.service().report()["observations"] if o["kind"] == KIND]


def by_route(run: Run) -> dict[str, Row]:
    return {str(r["subject"]): r for r in run.rows()}


def row_of(run: Run, route: str) -> Row:
    found = by_route(run)
    assert route in found, f"no finding for {route}: {sorted(found)}"
    return found[route]


def sizes(**by_name: int) -> PoolSizes:
    return by_name.get


# ported: RuntimeInsightsServiceTests.connectionsHeldTogetherAreFoundAndBackToBackConnectionsAreNot
def test_connections_held_together_are_found_and_back_to_back_connections_are_not() -> None:
    run = Run(pool_sizes=lambda name: 10 if name == "db" else None)
    # Nested: an inner connection checked out and released while the outer one is held.
    run.request("POST /api/orders", connection("db", 1_000, 50_000_000), connection("db", 10_000_000, 5_000_000))
    # Sequential: the second checked out exactly when the first was released.
    run.request("POST /api/payments", connection("db", 0, 10_000_000), connection("db", 10_000_000, 10_000_000))
    # Two data sources at once are two pools, each holding one.
    run.request("POST /api/report", connection("db", 0, 10_000_000), connection("audit", 1_000, 5_000_000))
    found = by_route(run)
    assert set(found) == {"POST /api/orders"}
    row = found["POST /api/orders"]
    assert row["sentence"] == "`POST /api/orders` held 2 connections of `db` at the same time in 1 of 1 request."
    estimate = str(row["whatToCheck"][1])  # type: ignore[index]
    for part in ("pool of 10 connections", "10 concurrent requests", "estimate", "not proof"):
        assert part in estimate
    unsized = Run()
    unsized.request("POST /api/orders", connection("db", 1_000, 50_000_000), connection("db", 10_000_000, 5_000_000))
    assert "floor((P - 1) / 1) + 1" in str(row_of(unsized, "POST /api/orders")["whatToCheck"][1])  # type: ignore[index]


# ported: RuntimeInsightsServiceTests.connectionEstimateRoundsUpWithThreeHeldAndOneRequestCanExhaustASmallerPool
def test_connection_estimate_rounds_up_with_three_held_and_one_request_can_exhaust_a_smaller_pool() -> None:
    def estimate(pool: int) -> str:
        run = Run(pool_sizes=lambda name: pool)
        run.request(
            "POST /api/orders",
            connection("db", 0, 30 * MS),
            connection("db", 1_000, 20 * MS),
            connection("db", 2_000, 10 * MS),
        )
        return str(row_of(run, "POST /api/orders")["whatToCheck"][1])  # type: ignore[index]

    assert "5 concurrent requests" in estimate(10)
    assert "1 concurrent request can" in estimate(1)


# BootUI fixture ObservationFixtures.connectionsPerRequest (positive): a REQUIRES_NEW connection inside the outer one
def test_connections_per_request_the_whole_finding_row() -> None:
    run = Run(pool_sizes=sizes(db=10))
    run.request(
        "POST /api/insights/orders/{id}/confirm", connection("db", 10 * MS, 5 * MS), connection("db", 1_000, 50 * MS)
    )
    row = row_of(run, "POST /api/insights/orders/{id}/confirm")
    assert row["eligible"] == 1
    assert row["affected"] == 1
    assert row["exemplarRequestIds"] == ["r1"]
    assert row["whatToCheck"] == [
        "Check for a REQUIRES_NEW transaction, or a second call to the data source, inside an open transaction "
        "(Transactions).",
        "With a pool of 10 connections and the observed maximum of 2 held per request, 10 concurrent requests can "
        "exhaust the pool while waiting for another connection. This is a hold-and-wait estimate, not proof of a "
        "deadlock (Database Connection Pools).",
    ]
    assert row["limitations"] == [
        "Counts logical connections the application obtained. The estimate assumes nested checkouts, not parallel "
        "independent work; other pool users can exhaust it at lower concurrency.",
        "The estimate uses the pool's current maximum size.",
    ]
    detail = run.service().insight(str(row["id"]))
    assert detail["columns"] == ["Request", "Connections held together"]
    assert [r["cells"] for r in detail["rows"]] == [["r1", "2"]]


def test_connections_per_request_without_a_pool_size_says_so() -> None:
    run = Run(pool_sizes=sizes(other=4))  # a name it does not know: no size
    run.request("GET /a", connection("db", 0, 10 * MS), connection("db", 1_000, 2 * MS))
    row = row_of(run, "GET /a")
    assert row["limitations"][1] == "The pool's maximum size is unavailable; the estimate uses P."  # type: ignore[index]


@pytest.mark.parametrize("pool", [0, -3])
def test_connections_per_request_a_non_positive_pool_size_is_unknown(pool: int) -> None:
    run = Run(pool_sizes=lambda name: pool)  # ``InsightsSnapshot.poolSize``: size <= 0 is empty
    run.request("GET /a", connection("db", 0, 10 * MS), connection("db", 1_000, 2 * MS))
    assert "floor((P - 1)" in str(row_of(run, "GET /a")["whatToCheck"][1])  # type: ignore[index]


def test_connections_per_request_a_failing_pool_size_lookup_is_unknown() -> None:
    def boom(name: str) -> int | None:
        raise RuntimeError(name)

    run = Run(pool_sizes=boom)  # ``InsightsSnapshot.poolSize`` swallows a RuntimeException
    run.request("GET /a", connection("db", 0, 10 * MS), connection("db", 1_000, 2 * MS))
    assert "floor((P - 1)" in str(row_of(run, "GET /a")["whatToCheck"][1])  # type: ignore[index]


def test_connections_per_request_rows_run_most_held_first_and_exemplars_are_the_top_three() -> None:
    run = Run(pool_sizes=sizes(db=10))
    two = (connection("db", 0, 10 * MS), connection("db", 1_000, 2 * MS))
    three = (*two, connection("db", 2_000, 1 * MS))
    ids = [
        run.request("GET /a", *two),
        run.request("GET /a", *three),
        run.request("GET /a", *two),
        run.request("GET /a", *two),
    ]
    run.request("GET /a", connection("db", 0, 10 * MS))  # one connection: not a row
    row = row_of(run, "GET /a")
    assert row["sentence"] == "`GET /a` held 3 connections of `db` at the same time in 4 of 5 requests."
    assert row["exemplarRequestIds"] == [ids[1], ids[0], ids[2]]
    detail = run.service().insight(str(row["id"]))
    assert [r["cells"] for r in detail["rows"]] == [[ids[1], "3"], [ids[0], "2"], [ids[2], "2"], [ids[3], "2"]]
    assert "maximum of 3 held per request, 5 concurrent requests" in str(row["whatToCheck"][1])  # type: ignore[index]


def test_connections_per_request_one_finding_per_route_and_data_source() -> None:
    run = Run(pool_sizes=sizes(db=10, audit=2))
    run.request(
        "GET /a", connection("db", 0, 9 * MS), connection("db", 1_000, 2 * MS), connection("audit", 0, 9 * MS),
        connection("audit", 1_000, 2 * MS),
    )  # fmt: skip
    run.request("GET /b", connection("db", 0, 9 * MS), connection("db", 1_000, 2 * MS))
    rows = run.rows()
    assert sorted((r["subject"], str(r["sentence"]).split(" of `")[1][:5]) for r in rows) == [
        ("GET /a", "audit"), ("GET /a", "db` a"), ("GET /b", "db` a"),
    ]  # fmt: skip
    assert len({r["id"] for r in rows}) == 3
    assert run.check()["eligibleRequests"] == 2
    assert run.check()["findings"] == 3


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ((0, 10), (10, 10)),  # back to back: a release comes before a checkout at the same instant
        ((0, 5), (6, 5)),  # a gap
    ],
)
def test_connections_per_request_sequential_connections_are_not_held_together(
    first: tuple[int, int], second: tuple[int, int]
) -> None:
    run = Run()
    run.request(
        "GET /a", connection("db", first[0] * MS, first[1] * MS), connection("db", second[0] * MS, second[1] * MS)
    )
    assert run.rows() == []
    check = run.check()
    assert check["status"] == "EVALUATED"
    assert check["eligibleRequests"] == 1


def test_connections_per_request_a_connection_with_no_name_or_clock_is_counted_apart() -> None:
    run = Run()
    run.request("GET /a", connection(None, 0, 10 * MS), connection("db", 1_000, 2 * MS), connection("db", -1, 1 * MS))
    assert run.rows() == []  # one nameless, one without a checkout time: neither is told apart, neither counts
    reason = str(run.check()["reason"])
    assert "2 connections had no data source name or checkout time, so they are not counted as held together" in reason
    run = Run()
    run.request("GET /a", connection(None, 0, 10 * MS))
    assert "1 connection had no data source name or checkout time, so it is not counted" in str(run.check()["reason"])


def test_connections_per_request_all_counted_leaves_no_uncounted_note() -> None:
    run = Run()
    run.request("GET /a", connection("db", 0, 10 * MS))
    assert run.check()["reason"] is None


def test_connections_per_request_metadata_only_withholds_and_says_so() -> None:
    run = Run(Exposure.METADATA_ONLY)  # the journal nulls ``requestId`` at this exposure
    run.request("GET /a", connection("db", 0, 10 * MS), connection("db", 1_000, 2 * MS))
    check = run.check()
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == (
        "Request ids are withheld at METADATA_ONLY exposure, so connections cannot be placed in a request "
        "(SHARPIT_EXPOSE_VALUES)."
    )
    assert run.rows() == []


def test_connections_per_request_a_dropped_connection_event_makes_the_check_partial() -> None:
    run = Run()
    run.request("GET /a", connection("db", 0, 10 * MS), connection("db", 1_000, 2 * MS))
    run.journal.count_dropped("connection")
    assert run.check()["status"] == "PARTIAL"


def test_connections_per_request_a_connection_of_no_request_joins_nothing() -> None:
    run = Run()
    run.journal.offer({**connection("db", 0, 10 * MS), "requestId": "nobody"})
    run.journal.offer({**connection("db", 1_000, 2 * MS), "requestId": "nobody"})
    run.request("GET /a")
    assert run.rows() == []
    assert run.check()["eligibleRequests"] == 1
