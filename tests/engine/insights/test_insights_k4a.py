"""Runtime Insights K4a: ``safe-method-dml`` and ``lazy-sql-after-handler`` over the http and sql journal sources.

The synthetic runs write the http event with ``http_event`` and the sql event with the keys the P-sql producer writes
(``sources/dispatch._journal_event``); the real-install tests run a FastAPI app with a sqlite engine. sharpit's sql
event carries the masked statement shape, never the statement, and no handler-end mark, so ``safe-method-dml`` reads the
verb only and ``lazy-sql-after-handler`` is not applicable.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.kinds import lazy_sql_after_handler as lazy
from sharpit.engine.collectors.insights.kinds import safe_method_dml as safe
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.masking import Exposure, Masker

SAFE, LAZY = "safe-method-dml", "lazy-sql-after-handler"
PRODUCT = "GET /api/products/{id}"
SITE = "app/views.py:12 in bump"
Row = dict[str, object]


def sql(text: str | None, *, failed: bool = False, provenance: str = "EXECUTION", site: str | None = SITE) -> Row:
    return {
        "source": "sql", "sql": text, "traceId": None, "thread": "MainThread", "durationNanos": 1_000_000,
        "startedAt": 1, "dataSource": None, "failed": failed, "phase": None, "completedNanos": 20_000_000,
        "codePathStamp": 0, "provenance": provenance, "batchSize": 1, "callSite": site,
    }  # fmt: skip


class Run:
    def __init__(self, exposure: Exposure = Exposure.MASKED) -> None:
        self.journal = RuntimeJournal(masker=Masker(exposure, True))
        self.requests = 0

    def request(self, route: str, *children: Row, status: int = 200) -> str:
        self.requests += 1
        request_id = f"r{self.requests}"
        method, _, template = route.partition(" ")
        info = RequestInfo(request_id, "ctx", method, template.replace("{id}", "42"), None, 0, 30_000_000)
        for child in children:
            self.journal.offer({**child, "requestId": request_id})
        self.journal.offer(http_event(info, [], 1_000_000, status, template))
        return request_id

    def report(self) -> Row:
        return InsightsService(self.journal).report()

    def check(self, kind: str = SAFE) -> Row:
        return next(c for c in self.report()["checks"] if c["kind"] == kind)  # type: ignore[attr-defined]

    def rows(self, kind: str = SAFE) -> list[Row]:
        return [o for o in self.report()["observations"] if o["kind"] == kind]  # type: ignore[attr-defined]


def one(rows: list[Row]) -> Row:
    assert len(rows) == 1
    return rows[0]


# ported: RuntimeInsightsServiceTests.writesInGetRequestsAreAskedAboutAndWritesInPostsOrFailedWritesAreNot
def test_safe_method_dml_writes_in_get_requests_are_asked_about() -> None:
    run = Run()
    run.request(PRODUCT, sql("update product_views set n = n + ? where id = ?"))
    run.request("POST /api/orders", sql("insert into orders (id) values (?)"))
    run.request("GET /api/cart", sql("delete from carts where id = ?", failed=True))
    rows = run.rows()
    assert [r["subject"] for r in rows] == [PRODUCT]
    row = rows[0]
    assert row["status"] == "OBSERVED"
    assert "in 1 of 1 request" in str(row["sentence"])
    assert str(row["sentence"]).endswith("or a change the caller asked for?")
    assert run.check()["eligibleRequests"] == 2  # the GETs: the POST is not eligible, the failed write is not a finding


def test_safe_method_dml_seeded_case_and_counterexample() -> None:
    run = Run()
    run.request(PRODUCT, sql("update views set n = ?"), sql("insert into audit (id) values (?)"), sql("select 1"))
    run.request(PRODUCT, sql("update views set n = ?"))
    run.request(PRODUCT, sql("select * from product where id = ?"))  # counterexample: a read-only GET
    run.request("HEAD /api/products/{id}", sql("select 1"))  # a different route, no write
    row = one(run.rows())
    assert row["subject"] == PRODUCT
    assert row["sentence"] == (
        f"`{PRODUCT}` executed writes (UPDATE, INSERT) in 2 of 3 requests: an incidental write, such as an audit or a "
        "counter, or a change the caller asked for?"
    )
    assert row["eligible"] == 3
    assert row["affected"] == 2
    assert row["exemplarRequestIds"] == ["r1", "r2"]
    assert len(row["whatToCheck"]) == 2  # type: ignore[arg-type]
    assert run.check()["status"] == "EVALUATED"
    assert run.check()["eligibleRequests"] == 4
    detail = InsightsService(run.journal).insight(str(row["id"]))
    assert detail["columns"] == ["Request", "Status", "Executions", "Call site"]  # type: ignore[index]
    assert [r["cells"] for r in detail["rows"]] == [["r1", "200", "2", SITE], ["r2", "200", "1", SITE]]  # type: ignore[index]


@pytest.mark.parametrize(("method", "eligible"), [("GET", True), ("HEAD", True), ("POST", False), ("PUT", False),
                                                  ("PATCH", False), ("DELETE", False), ("OPTIONS", False)])  # fmt: skip
def test_safe_method_dml_only_get_and_head_are_safe(method: str, eligible: bool) -> None:
    run = Run()
    run.request(f"{method} /api/x", sql("update t set n = ?"))
    assert run.check()["status"] == ("EVALUATED" if eligible else "INSUFFICIENT")
    assert len(run.rows()) == int(eligible)
    assert run.check()["eligibleRequests"] == int(eligible)


@pytest.mark.parametrize(
    ("text", "verb"),
    [
        ("update t set n = ?", "UPDATE"),
        ("  INSERT INTO t VALUES (?)", "INSERT"),
        ("Delete from t where id = ?", "DELETE"),
        ("MERGE INTO t USING s ON ?", "MERGE"),
        ("select * from t", None),
        ("with x as (select 1) insert into t select * from x", None),  # BootUI reads the first keyword only
        ("upsert t set n = ?", None),
        ("updated_at = ?", None),
    ],
)
def test_safe_method_dml_reads_the_first_keyword(text: str, verb: str | None) -> None:
    run = Run()
    run.request(PRODUCT, sql(text))
    rows = run.rows()
    assert run.check()["status"] == "EVALUATED"
    if verb is None:
        assert rows == []
    else:
        assert f"({verb})" in str(rows[0]["sentence"])


@pytest.mark.parametrize("provenance", ["UNKNOWN", "PREPARATION"])
def test_safe_method_dml_counts_executions_only(provenance: str) -> None:
    run = Run()
    run.request(PRODUCT, sql("insert into audit (id) values (?)", provenance=provenance))
    assert run.rows() == []
    assert run.check()["status"] == "EVALUATED"


@pytest.mark.parametrize("text", ["******", "[statement hidden: unsupported database]", None, ""])
def test_safe_method_dml_says_when_a_statement_cannot_be_read(text: str | None) -> None:
    run = Run()
    run.request(PRODUCT, sql(text), sql("select 1"))
    check = run.check()
    assert check["status"] == "EVALUATED"
    assert "1 statement in a GET or HEAD request could not be read as a statement" in str(check["reason"])
    assert run.rows() == []  # and it is not a clean result: the reason names what went uncounted


def test_safe_method_dml_text_uses_journal_fields_only() -> None:
    run = Run()
    run.request(PRODUCT, sql("update audit_secret_table set hits = hits + ? where owner = ?"))
    row = one(run.rows())
    detail = InsightsService(run.journal).insight(str(row["id"]))
    dumped = json.dumps([run.report(), detail])
    assert "audit_secret_table" not in dumped  # the verb and the call site are read; the statement is not shown
    assert "hits" not in dumped
    assert "masked statement shape" in json.dumps(row["limitations"])


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.FULL])
def test_safe_method_dml_limitation_names_what_is_failed_and_what_is_shape_only(exposure: Exposure) -> None:
    run = Run(exposure)
    run.request(PRODUCT, sql("update t set n = ?"))
    row = one(run.rows())
    assert row["limitations"] == list(safe.LIMITATIONS)


def test_safe_method_dml_metadata_only_withholds_and_says_so() -> None:
    run = Run(Exposure.METADATA_ONLY)  # the journal nulls ``requestId`` at this exposure
    run.request(PRODUCT, sql("update t set n = ?"))
    check = run.check()
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == safe.IDS_WITHHELD
    assert "SHARPIT_EXPOSE_VALUES" in safe.IDS_WITHHELD
    assert run.rows() == []


def test_safe_method_dml_a_dropped_event_makes_the_check_partial() -> None:
    run = Run()
    run.request(PRODUCT, sql("update t set n = ?"))
    run.journal.count_dropped("sql")
    assert run.check()["status"] == "PARTIAL"


# the lazy kind: sharpit marks no handler end, so a statement cannot be placed in the response write


def test_lazy_sql_after_handler_is_not_applicable_with_a_fixed_reason() -> None:
    run = Run()
    for _ in range(3):  # BootUI's seeded case: the same statement in three requests; sharpit cannot place it
        run.request(PRODUCT, sql("select * from owner_pets where owner_id = ?"))
    check = run.check(LAZY)
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == lazy.NOT_APPLICABLE
    assert "handler" in lazy.NOT_APPLICABLE
    assert run.rows(LAZY) == []


def test_lazy_sql_after_handler_seeded_case_and_counterexample() -> None:
    seeded, empty = Run(), Run()
    seeded.request(PRODUCT, sql("select 1"))
    empty.request(PRODUCT)  # counterexample: no SQL at all
    for run in (seeded, empty):
        check = run.check(LAZY)
        assert (check["status"], check["findings"], check["eligibleRequests"]) == ("NOT_APPLICABLE", 0, 0)
        assert check["reason"] == lazy.NOT_APPLICABLE  # never a clean "nothing found" over data it cannot place


# ported: ObservationHonestyHarnessTests.everyKindAgainstEveryFixture (a kind whose capture does not exist answers
# not applicable whatever was recorded)
@pytest.mark.parametrize("exposure", list(Exposure))
def test_lazy_sql_after_handler_metadata_only_withholds_and_says_so(exposure: Exposure) -> None:
    run = Run(exposure)
    run.request(PRODUCT, sql("select 1"))
    check = run.check(LAZY)
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == lazy.NOT_APPLICABLE  # the same fixed reason at every exposure: ids do not matter to it


def test_lazy_sql_after_handler_text_uses_journal_fields_only() -> None:
    run = Run()
    run.request(PRODUCT, sql("select * from audit_secret_table where owner = ?"))
    check = run.check(LAZY)
    assert check["reason"] == lazy.NOT_APPLICABLE
    dumped = json.dumps(check)
    assert "audit_secret_table" not in dumped
    assert PRODUCT not in dumped


# real installs: a FastAPI app with sharpit and a sqlite engine

sa = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.collectors.insights.service import insights_service  # noqa: E402

LITERAL_CANARY = "zq-literal-canary-" + "63"
PARAMETER_CANARY = "zq-parameter-canary-" + "64"


@pytest.fixture(autouse=True)
def clean_listeners() -> Iterator[None]:
    sqla.detach_all()
    yield
    sqla.detach_all()


def _app(exposure: str) -> tuple[TestClient, Any]:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(sa.text("create table views (id integer, n integer, note text)"))
        conn.execute(sa.text("insert into views values (1, 0, 'x')"))
    app = FastAPI()

    @app.get("/views/{view_id}")
    async def bump(view_id: int) -> dict[str, int]:
        with engine.begin() as conn:
            conn.execute(
                sa.text(f"update views set n = n + 1, note = '{LITERAL_CANARY}' where id = :id and note != :p"),
                {"id": view_id, "p": PARAMETER_CANARY},
            )
        return {"ok": 1}

    @app.get("/plain/{view_id}")
    async def plain(view_id: int) -> dict[str, int]:
        with engine.begin() as conn:
            conn.execute(sa.text("select n from views where id = :id"), {"id": view_id})
        return {"ok": 1}

    handle = install(
        app, enabled="ON", show_banner=False, config_scan=False, engines=[engine], expose_values=exposure,
        runtime_journal_sources=("http", "sql"),
    )  # fmt: skip
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)), handle.context


def _report(ctx: Any) -> Row:
    return insights_service(ctx).report()


def test_safe_method_dml_real_install_a_get_that_runs_an_update() -> None:
    client, ctx = _app("MASKED")
    assert client.get("/views/1").status_code == 200
    assert client.get("/plain/1").status_code == 200
    report = _report(ctx)
    row = one([o for o in report["observations"] if o["kind"] == SAFE])  # type: ignore[attr-defined]
    assert row["subject"] == "GET /views/{view_id}"
    assert "(UPDATE)" in str(row["sentence"])
    assert row["affected"] == 1
    check = next(c for c in report["checks"] if c["kind"] == SAFE)  # type: ignore[attr-defined]
    assert check["eligibleRequests"] == 2


@pytest.mark.parametrize("exposure", ["MASKED", "FULL", "METADATA_ONLY"])
def test_safe_method_dml_sql_literal_canary_never_shown(exposure: str) -> None:
    client, ctx = _app(exposure)
    client.get("/views/1")
    report = _report(ctx)
    rows = [o for o in report["observations"] if o["kind"] == SAFE]  # type: ignore[attr-defined]
    dumped = json.dumps(report)
    for row in rows:
        dumped += json.dumps(insights_service(ctx).insight(str(row["id"])))
    assert LITERAL_CANARY not in dumped
    assert PARAMETER_CANARY not in dumped
    check = next(c for c in report["checks"] if c["kind"] == SAFE)  # type: ignore[attr-defined]
    if exposure == "METADATA_ONLY":
        assert check["reason"] == safe.IDS_WITHHELD
        assert rows == []
    else:
        assert len(rows) == 1


@pytest.mark.parametrize("exposure", ["MASKED", "FULL", "METADATA_ONLY"])
def test_lazy_sql_after_handler_sql_literal_canary_never_shown(exposure: str) -> None:
    client, ctx = _app(exposure)
    client.get("/views/1")
    report = _report(ctx)
    check = next(c for c in report["checks"] if c["kind"] == LAZY)  # type: ignore[attr-defined]
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == lazy.NOT_APPLICABLE
    assert LITERAL_CANARY not in json.dumps(report)
    assert PARAMETER_CANARY not in json.dumps(report)


def test_lazy_sql_after_handler_real_install_is_not_applicable() -> None:
    # sharpit cannot see a response model's serialization trigger a lazy load: it marks no handler end
    client, ctx = _app("MASKED")
    for _ in range(3):
        client.get("/plain/1")
    report = _report(ctx)
    check = next(c for c in report["checks"] if c["kind"] == LAZY)  # type: ignore[attr-defined]
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == lazy.NOT_APPLICABLE
    assert [o for o in report["observations"] if o["kind"] == LAZY] == []  # type: ignore[attr-defined]
