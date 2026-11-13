"""W5a P-connection: one ``connection`` journal event per logical connection the application releases (BootUI
``ConnectionPayload``, ``SqlTraceRecorder.checkoutConnection`` / ``releaseConnection``)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.correlation import REQUEST, RequestInfo, internal  # noqa: E402
from sharpit.engine.collectors.insights.service import insights_service  # noqa: E402
from sharpit.engine.collectors.insights.snapshot import PRODUCED_SOURCES  # noqa: E402
from sharpit.engine.collectors.pools import pools_report  # noqa: E402
from sharpit.fastapi.capture import HOOK_SQLA_LISTENERS  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

NOT_RECORDED = "The runtime journal does not record the {} source (SHARPIT_RUNTIME_JOURNAL_SOURCES)."
PASSWORD_CANARY = "zq-password-canary-77"
FIELDS = {
    "source", "epochMillis", "durationNanos", "traceId", "thread", "requestId", "failedOrSlow", "dataSource",
    "waitNanos", "statements", "checkoutNanos",
}  # fmt: skip


@pytest.fixture(autouse=True)
def clean_listeners() -> Iterator[None]:
    sqla.detach_all()
    yield
    sqla.detach_all()


def _install(sources: tuple[str, ...] = ("connection", "sql"), engine: Any = None, **options: Any) -> Any:
    engine = engine or sa.create_engine("sqlite://")
    handle = install(
        FastAPI(),
        enabled="ON",
        show_banner=False,
        config_scan=False,
        engines=[engine],
        runtime_journal_sources=sources,
        **options,
    )
    handle.engine = engine
    return handle


def _records(handle: Any, source: str = "connection") -> tuple[dict[str, object], ...]:
    journal = handle.context.capture.journal
    assert journal is not None
    return journal.records(source)


def _only(handle: Any, source: str = "connection") -> dict[str, object]:
    records = _records(handle, source)
    assert len(records) == 1
    return records[0]


def _use(engine: Any, statements: int = 1) -> None:
    with engine.connect() as conn:
        for n in range(statements):
            conn.execute(sa.text("select :n"), {"n": n})


def _request(handle: Any, request_id: str) -> Any:
    return REQUEST.set(RequestInfo(request_id, handle.context.context_id, "GET", "/x", None, 0, None))


# ported: SqlTracingProxiesTests.publishesEachLogicalConnectionOnceWithItsWaitHoldStatementsAndCheckoutRequest
def test_connection_journal_event_offered_once_per_release_with_bootui_fields():
    handle = _install()
    token = _request(handle, "0123456789abcdef")
    try:
        before = time.perf_counter_ns()
        _use(handle.engine, 2)
    finally:
        REQUEST.reset(token)
    record = _only(handle)
    assert set(record) == FIELDS
    assert record["source"] == "connection"
    assert record["requestId"] == "0123456789abcdef"
    assert record["thread"] == "MainThread"
    assert record["statements"] == 2
    assert record["waitNanos"] == 0
    assert record["failedOrSlow"] is False
    assert isinstance(record["durationNanos"], int)
    assert record["durationNanos"] >= 0
    assert record["checkoutNanos"] >= before


def test_connection_journal_statements_count_the_connections_own_statements():
    handle = _install()
    _use(handle.engine, 2)
    with handle.engine.connect() as conn:
        conn.execute(sa.text("select 1"))
        with internal():
            conn.execute(sa.text("select 2"))  # sharpit's own statement is not the application's
        conn.execute(sa.text("select 3"))
        conn.execute(sa.text("select 4"))
    assert [r["statements"] for r in _records(handle)] == [2, 3]


# ported: SqlTracingProxiesTests.publishesEachLogicalConnectionOnceWithItsWaitHoldStatementsAndCheckoutRequest
def test_connection_journal_checkout_nanos_on_the_sql_clock():
    handle = _install()
    _use(handle.engine)
    connection, statement = _only(handle), _only(handle, "sql")
    checkout, held, completed = connection["checkoutNanos"], connection["durationNanos"], statement["completedNanos"]
    assert isinstance(checkout, int)
    assert isinstance(held, int)
    assert isinstance(completed, int)
    assert checkout <= completed  # the statement ran after the checkout, on the same perf_counter clock
    assert completed <= checkout + held  # and before the release


@pytest.mark.parametrize("exposure", ["MASKED", "FULL"])
def test_connection_journal_data_source_never_carries_the_url_or_password(exposure: str):
    engine = sa.create_engine("sqlite://")
    engine.url = engine.url.set(
        username="app", password=PASSWORD_CANARY, host="db.example", database="orders", query={"password": PASSWORD_CANARY}
    )
    handle = _install(engine=engine, expose_values=exposure)
    _use(engine)
    record = _only(handle)
    assert PASSWORD_CANARY not in json.dumps(record)
    assert "app:" not in str(record["dataSource"])
    assert record["dataSource"] == pools_report(handle.context)["pools"][0]["beanName"]  # the panel's name, not the URL


def test_connection_journal_second_checkin_is_ignored():
    handle = _install()
    with handle.engine.connect() as conn:
        record = conn.connection._connection_record  # noqa: SLF001
    assert len(_records(handle)) == 1
    from sharpit.engine.sqla import connections  # noqa: PLC0415

    connections.checkin(None, record)
    assert len(_records(handle)) == 1


def test_connection_journal_not_offered_for_sharpit_internal_work():
    handle = _install()
    with internal():
        _use(handle.engine)
    assert _records(handle) == ()
    _use(handle.engine)  # control: the same release outside sharpit's own work is offered
    assert len(_records(handle)) == 1


def test_connection_journal_not_offered_when_source_disabled():
    disabled = _install(sources=("http",))
    _use(disabled.engine)
    assert _records(disabled) == ()
    assert disabled.context.capture.journal.status()["dropped"] == {"connection": 1}
    enabled = _install()  # control: the same release is offered when the source is enabled
    _use(enabled.engine)
    assert len(_records(enabled)) == 1


# ported: PausedPanelPublishingTests.aPausedOrIdleSqlTracePanelKeepsPublishingStatementsAndConnections
def test_connection_journal_is_offered_while_the_panel_is_paused():
    handle = _install()
    handle.context.capture.sql_trace.recording = False
    _use(handle.engine)
    assert len(_records(handle)) == 1
    assert handle.context.capture.sql_trace.report([])["totalCaptured"] == 0


def test_connection_journal_carries_the_request_id_of_this_install_only():
    ours, theirs = _install(), _install()
    token = REQUEST.set(RequestInfo("r-theirs", theirs.context.context_id, "GET", "/x", None, 0, None))
    try:
        _use(ours.engine)
    finally:
        REQUEST.reset(token)
    token = _request(ours, "r-ours")
    try:
        _use(ours.engine)
    finally:
        REQUEST.reset(token)
    assert [r["requestId"] for r in _records(ours)] == [None, "r-ours"]
    assert "r-theirs" not in json.dumps(_records(ours))


def test_connection_journal_a_failing_build_never_reaches_the_host(monkeypatch: pytest.MonkeyPatch):
    handle = _install()
    recorder = handle.context.capture.sql_trace

    def boom(_nanos: int) -> bool:
        raise RuntimeError("build failed")

    monkeypatch.setattr(recorder, "slow_held", boom, raising=False)
    with handle.engine.connect() as conn:
        assert conn.execute(sa.text("select 1")).scalar() == 1  # the host's work and its release both complete
    assert _records(handle) == ()
    monkeypatch.undo()
    _use(handle.engine)  # control: the next release is offered
    assert len(_records(handle)) == 1


def test_connection_journal_failed_or_slow_follows_the_slow_query_threshold():
    handle = _install(sql_trace_slow_query_threshold_millis=1)
    with handle.engine.connect() as conn:
        conn.execute(sa.text("select 1"))
        time.sleep(0.01)
    _use(handle.engine)
    assert [r["failedOrSlow"] for r in _records(handle)] == [True, False]


def test_connection_journal_source_not_produced_when_the_listener_cannot_run():
    handle = _install()
    assert "connection" in PRODUCED_SOURCES
    kind = "connections-per-request"
    armed = next(c for c in insights_service(handle.context).report()["checks"] if c["kind"] == kind)
    assert armed["reason"] != NOT_RECORDED.format("connection")  # the producer runs: the source is recorded
    handle.context.capture.wiring.suspend_hook(HOOK_SQLA_LISTENERS)
    suspended = next(c for c in insights_service(handle.context).report()["checks"] if c["kind"] == kind)
    assert suspended["status"] == "NOT_APPLICABLE"
    assert suspended["reason"] == NOT_RECORDED.format("connection")
    handle.context.capture.wiring.resume_hook(HOOK_SQLA_LISTENERS)
    _use(handle.engine)
    assert len(_records(handle)) == 1
