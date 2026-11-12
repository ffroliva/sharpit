"""W5a P-sql: one ``sql`` journal event per executed statement, literal- and parameter-free (BootUI ``SqlPayload``)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.correlation import REQUEST, RequestInfo, internal  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

LITERAL_CANARY = "zq-literal-canary-81"
PARAMETER_CANARY = "zq-parameter-canary-42"
SELECT = f"select * from (select 1 as n) where 'x' = '{LITERAL_CANARY}' or n = :n"


@pytest.fixture(autouse=True)
def clean_listeners() -> Iterator[None]:
    sqla.detach_all()
    yield
    sqla.detach_all()


def _install(sources: tuple[str, ...] = ("sql",), **options: Any) -> Any:
    engine = sa.create_engine("sqlite://")
    handle = install(
        FastAPI(),
        enabled="ON",
        show_banner=False,
        config_scan=False,
        engines=[engine],
        runtime_journal_sources=sources,
        **options,
    )
    return handle, engine


def _run(engine: Any, statement: str = SELECT, parameters: Any = None) -> None:
    with engine.connect() as conn:
        conn.execute(sa.text(statement), parameters if parameters is not None else {"n": PARAMETER_CANARY})


def _records(handle: Any) -> tuple[dict[str, object], ...]:
    journal = handle.context.capture.journal
    assert journal is not None
    return journal.records("sql")


# ported: SqlTraceRecorderTests.publishesEachRecordedStatementToTheJournalWithItsCorrelationButNoBindValues
def test_sql_journal_event_offered_once_per_statement_with_bootui_fields():
    handle, engine = _install()
    _run(engine)
    records = _records(handle)
    assert len(records) == 1
    record = records[0]
    assert set(record) == {
        "source",
        "sql",
        "traceId",
        "requestId",
        "thread",
        "durationNanos",
        "startedAt",
        "dataSource",
        "failed",
        "phase",
        "completedNanos",
        "codePathStamp",
        "provenance",
        "batchSize",
        "callSite",
    }
    assert record["source"] == "sql"
    assert record["sql"] == "select * from (select ? as n) where ? = ? or n = ?"
    assert record["failed"] is False
    assert record["provenance"] == "EXECUTION"
    assert record["batchSize"] == 1
    assert record["codePathStamp"] == 0
    assert isinstance(record["durationNanos"], int)
    assert record["durationNanos"] >= 0


@pytest.mark.parametrize("exposure", ["MASKED", "FULL"])
def test_sql_journal_literal_and_parameter_canary_never_reaches_the_journal(exposure: str):
    handle, engine = _install(expose_values=exposure, sql_trace_capture_parameters=True)
    _run(engine)
    records = _records(handle)
    assert len(records) == 1
    assert LITERAL_CANARY not in json.dumps(records)
    assert PARAMETER_CANARY not in json.dumps(records)


def test_sql_journal_event_not_offered_for_sharpit_internal_work():
    handle, engine = _install()
    with internal():
        _run(engine)
    assert _records(handle) == ()


def test_sql_journal_event_not_offered_when_source_disabled():
    handle, engine = _install(sources=("http",))
    _run(engine)
    assert _records(handle) == ()
    assert handle.context.capture.sql_trace.report([])["totalCaptured"] == 1


def test_sql_journal_event_carries_the_request_id_of_this_install_only():
    ours, engine = _install()
    theirs, _ = _install()
    token = REQUEST.set(RequestInfo("r-ours", ours.context.context_id, "GET", "/x", None, 0, None))
    try:
        _run(engine)
    finally:
        REQUEST.reset(token)
    token = REQUEST.set(RequestInfo("r-theirs", theirs.context.context_id, "GET", "/x", None, 0, None))
    try:
        _run(engine)
    finally:
        REQUEST.reset(token)
    assert [r["requestId"] for r in _records(ours)] == ["r-ours"]
    assert "r-theirs" not in json.dumps(_records(ours))


def test_sql_journal_error_statement_offered_with_its_outcome():
    handle, engine = _install()
    with pytest.raises(sa.exc.OperationalError):
        _run(engine, "select * from no_such_table where id = :n")
    records = _records(handle)
    assert len(records) == 1
    assert records[0]["failed"] is True
    assert records[0]["provenance"] == "EXECUTION"


# ported: SqlTraceRecorderTests.thePublishedBatchSizeIsOneForAnOrdinaryExecutionTheSubmittedCountForABatchAndUnknownForAPreparation  # noqa: E501
def test_sql_journal_executemany_records_its_batch_size():
    handle, engine = _install()
    with engine.begin() as conn:
        conn.execute(sa.text("create table t (a integer)"))
        conn.execute(sa.text("insert into t (a) values (:a)"), [{"a": 1}, {"a": 2}, {"a": 3}])
    batches = [r["batchSize"] for r in _records(handle) if str(r["sql"]).startswith("insert")]
    assert batches == [3]
