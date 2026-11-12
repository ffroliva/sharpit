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


def test_sql_journal_event_content_is_this_exact_dict(monkeypatch: pytest.MonkeyPatch):
    """W5a P-sql r2: the hot-path rewrite changes no field; the clocks are frozen, so every value is known."""
    from sharpit.engine.sources import dispatch  # noqa: PLC0415
    from sharpit.engine.sqltext import Dialect  # noqa: PLC0415

    handle, _ = _install(sql_trace_capture_call_site=False)
    monkeypatch.setattr("time.time_ns", lambda: 1_700_000_000_123_456_789)
    monkeypatch.setattr("time.perf_counter_ns", lambda: 987_654_321)
    event = dispatch.SqlEvent(
        "sqlalchemy", "select a from t where b = 'x' and c = ?", ("p",), False, None, 0, 3_500_000, 1, None, "c1",
        None, Dialect.SQLITE,
    )  # fmt: skip
    dispatch.deliver(event, [handle.context])
    assert _records(handle) == (
        {
            "source": "sql",
            "sql": "select a from t where b = ? and c = ?",
            "traceId": None,
            "requestId": None,
            "thread": "MainThread",
            "durationNanos": 3_500_000,
            "startedAt": 1_700_000_000_120,
            "dataSource": None,
            "failed": False,
            "phase": None,
            "completedNanos": 3_500_000,  # r3: started_ns + duration_ns, the statement's end, before any work
            "codePathStamp": 0,
            "provenance": "EXECUTION",
            "batchSize": 1,
            "callSite": None,
        },
    )


@pytest.mark.parametrize(
    ("info", "phase", "site", "trace_id"),
    [
        (None, None, None, None),
        (None, "STARTUP", "app.db:load:12", None),
        ("r-1", None, "app.db:load:12", None),
        ("r-1", None, None, None),
        ("r-1", None, None, "4bf92f3577b34da6a3ce929d0e0e4736"),
    ],
)
def test_sql_journal_event_size_is_what_the_flat_walk_charges(
    monkeypatch: pytest.MonkeyPatch, info: str | None, phase: str | None, site: str | None, trace_id: str | None
):
    """The producer charges the event's size itself (no walk per statement): it must equal the journal's own walk."""
    from sharpit.engine import otel  # noqa: PLC0415
    from sharpit.engine.capture.journal import _flat  # noqa: PLC0415  # pyright: ignore[reportPrivateUsage]
    from sharpit.engine.sources import dispatch  # noqa: PLC0415
    from sharpit.engine.sqltext import Dialect  # noqa: PLC0415

    monkeypatch.setattr(otel, "current_trace_id", lambda: trace_id)
    handle, _ = _install()
    recorder = handle.context.capture.sql_trace
    recorder.lifespan_phase = phase
    request = RequestInfo(info, handle.context.context_id, "GET", "/x", None, 0, None) if info else None
    event = dispatch.SqlEvent(
        "sqlalchemy", "select 1", None, True, 4, 0, 7, 1, None, None, None, Dialect.SQLITE
    )  # fmt: skip
    built, size = dispatch._journal_event(  # pyright: ignore[reportPrivateUsage]
        handle.context, recorder, event, "select ?", request, "worker-7", site
    )
    assert built["traceId"] == trace_id
    assert size == _flat(built)[1]
    assert tuple(built) == getattr(dispatch, "_SQL_KEYS", None)  # the size constant is derived from these keys


def _event(**fields: Any) -> Any:
    from sharpit.engine.sources import dispatch  # noqa: PLC0415
    from sharpit.engine.sqltext import Dialect  # noqa: PLC0415

    values = {
        "source": "sqlalchemy", "sql": "select 1", "parameters": None, "executemany": False, "batch_size": None,
        "started_ns": 0, "duration_ns": 7, "rowcount": 1, "error": None, "connection_id": None, "engine": None,
        "dialect": Dialect.SQLITE,
    }  # fmt: skip
    return dispatch.SqlEvent(**(values | fields))


# ported: PausedPanelPublishingTests.aPausedOrIdleSqlTracePanelKeepsPublishingStatementsAndConnections
def test_sql_journal_event_offered_while_the_sql_trace_panel_is_paused():
    """W5a P-sql r3: BootUI keeps the journal recording while the panel is paused (SqlTraceRecorder.java:730-731)."""
    handle, engine = _install()
    recorder = handle.context.capture.sql_trace
    recorder.set_recording(False)
    _run(engine)
    assert len(_records(handle)) == 1
    assert recorder.rows() == []


# ported: PausedPanelPublishingTests.aPausedSqlTracePanelPublishesNothingWhenTheJournalDoesNotRecordSql
def test_sql_journal_paused_panel_and_sql_not_a_journal_source_records_nothing():
    handle, engine = _install(sources=("http",))
    handle.context.capture.sql_trace.set_recording(False)
    _run(engine)
    # the statement is not offered at all; its (recording) transaction is counted dropped (W5a P-transaction)
    assert handle.context.capture.journal.status()["dropped"] == {"transaction": 1}


def test_sql_journal_phase_is_null_outside_a_request_even_in_the_lifespan():
    """W5a P-sql r3: BootUI's RequestPhase is FILTERS/HANDLER/RESPONSE in a request, null outside (SqlPayload.java)."""
    from sharpit.engine.sources import dispatch  # noqa: PLC0415

    handle, _ = _install()
    handle.context.capture.sql_trace.lifespan_phase = "STARTUP"
    dispatch.deliver(_event(), [handle.context])
    assert _records(handle)[0]["phase"] is None


def test_sql_journal_batch_size_of_a_sqlite3_executemany_fed_a_generator_is_unknown_zero():
    """W5a P-sql r3: a batch whose size is not known is 0, never read as unbatched (SqlTraceRecorder.java:650-652)."""
    import sqlite3  # noqa: PLC0415

    from sharpit.engine.sources import sqlite  # noqa: PLC0415

    handle, _ = _install()
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("create table g (n integer)")
        conn.executemany("insert into g values (?)", ((i,) for i in range(4)))
        conn.close()
    finally:
        sqlite.detach_all()
    batches = [r["batchSize"] for r in _records(handle) if str(r["sql"]).startswith("insert")]
    assert batches == [0]


def test_sql_journal_a_raising_offer_still_records_the_trace_row_and_is_not_an_sql_hook_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """W5a P-sql r3: the journal offer has its own guard, so its failure is reported as the journal's."""
    handle, engine = _install()
    journal = handle.context.capture.journal

    def boom(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("journal bug")

    monkeypatch.setattr(journal, "offer_flat", boom)
    with caplog.at_level("WARNING", logger="sharpit"):
        _run(engine)
    assert len(handle.context.capture.sql_trace.rows()) == 1
    assert "sql statement" not in caplog.text
    assert "sql journal" in caplog.text


def test_sql_journal_event_request_id_only_for_a_request_of_its_own_context():
    """The context check in ``_journal_event`` itself: routing already guarantees it, the event does not rely on it."""
    from sharpit.engine.sources import dispatch  # noqa: PLC0415

    handle, _ = _install()
    recorder = handle.context.capture.sql_trace
    other = RequestInfo("r-other", "another-context", "GET", "/x", None, 0, None)
    own = RequestInfo("r-own", handle.context.context_id, "GET", "/x", None, 0, None)
    built, _ = dispatch._journal_event(handle.context, recorder, _event(), "select ?", other, "t", None)  # pyright: ignore[reportPrivateUsage]
    assert built["requestId"] is None
    built, _ = dispatch._journal_event(handle.context, recorder, _event(), "select ?", own, "t", None)  # pyright: ignore[reportPrivateUsage]
    assert built["requestId"] == "r-own"
