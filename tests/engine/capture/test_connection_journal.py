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
NOT_ARMED = (
    "The {} source is enabled in the runtime journal, but its listener is not armed here "
    "(SQLAlchemy is not imported or its listeners are suspended): nothing is recorded."
)
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


def _by_value(value: object) -> object:
    """A copy compared by value: a dict's items, a slotted object's slots (a ``Checkout``), else the value."""
    if isinstance(value, dict):
        return {k: _by_value(v) for k, v in value.items()}
    slots = getattr(type(value), "__slots__", ())
    return {s: getattr(value, s, None) for s in slots} if slots else value


def _request(handle: Any, request_id: str) -> Any:
    return REQUEST.set(RequestInfo(request_id, handle.context.context_id, "GET", "/x", None, 0, None))


# ported: SqlTracingProxiesTests.publishesEachLogicalConnectionOnceWithItsWaitHoldStatementsAndCheckoutRequest
def test_connection_journal_event_offered_once_per_release_with_bootui_fields():
    # a threshold no hold reaches: a cold first connection on a slow runner held it past the 100 ms default (the slow
    # verdict itself has its own test), so ``failedOrSlow is False`` below does not depend on the runner's speed
    handle = _install(sql_trace_slow_query_threshold_millis=60_000)
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
    assert record["statements"] == -1  # unknown: see the deviation row; counting costs every statement
    assert record["waitNanos"] == 0
    assert record["failedOrSlow"] is False
    assert isinstance(record["durationNanos"], int)
    assert record["durationNanos"] >= 0
    assert record["checkoutNanos"] >= before


# deviation (r5): the statement path pays nothing for the count; -1 is "unknown", as BootUI gives checkoutNanos
def test_connection_journal_statement_count_is_unknown_and_statements_keep_no_connection_state():
    handle = _install()
    with handle.engine.connect() as conn:
        fairy = conn.connection
        conn.execute(sa.text("select 0"))  # warm: SQLAlchemy creates its own lazy attributes on first use

        def state() -> dict[str, object]:
            # the fairy keeps its state in __slots__ and the pool record, so compare the record's info by value too
            return {"fairy": _by_value(vars(fairy)), "record": _by_value(fairy._connection_record.info)}

        before = state()
        conn.execute(sa.text("select 1"))
        conn.execute(sa.text("select 2"))
        assert state() == before  # a statement writes nothing on the connection, under any key: no per-statement count
    _use(handle.engine, 3)
    assert [r["statements"] for r in _records(handle)] == [-1, -1]


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
        username="app",
        password=PASSWORD_CANARY,
        host="db.example",
        database="orders",
        query={"password": PASSWORD_CANARY},
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

    connections.checkin(record.dbapi_connection, record)  # a live release: None is skipped
    assert len(_records(handle)) == 1


def test_connection_journal_a_stale_checkout_is_not_offered_at_a_later_release():
    # review finding: a state left by a checkout whose checkin listener was gone must not surface at the next release
    from sharpit.engine.sqla import connections  # noqa: PLC0415

    handle = _install()
    with handle.engine.connect() as conn:
        record = conn.connection._connection_record  # noqa: SLF001
    baseline = len(_records(handle))
    record.info[connections.CHECKOUT_KEY] = connections.Checkout(
        [handle.context], handle.engine.pool, None
    )  # left behind
    with internal():
        connections.checkout(None, record, None)  # sharpit's own reuse of the record follows nothing
    connections.checkin(record.dbapi_connection, record)  # a live release: None is skipped
    assert len(_records(handle)) == baseline


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
    dropped = disabled.context.capture.journal.status()["dropped"]
    assert "connection" not in dropped  # BootUI follows and counts nothing then
    assert not sqla.attached()["checkout"]  # and no pool listener runs for it
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
    assert [r["requestId"] for r in _records(ours)] == ["r-ours"]
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


# ported: SqlTraceRecorder.isSlow (the threshold is the SQL Trace slow-query threshold, 100 ms by default)
def test_connection_journal_failed_or_slow_follows_the_slow_query_threshold():
    handle = _install()
    recorder = handle.context.capture.sql_trace
    assert recorder.slow_held(99_999_999) is False
    assert recorder.slow_held(100_000_000) is True
    recorder.slow_query_threshold_millis = 0  # 0 disables slow marking
    assert recorder.slow_held(10**12) is False
    recorder.slow_query_threshold_millis = 100
    with handle.engine.connect() as conn:
        conn.execute(sa.text("select 1"))
        time.sleep(0.12)
    recorder.slow_query_threshold_millis = 10**9  # the control release cannot be slow, however loaded the runner
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
    assert suspended["reason"] == NOT_ARMED.format("connection")  # the setting is right: the listener is what is off
    handle.context.capture.wiring.resume_hook(HOOK_SQLA_LISTENERS)
    _use(handle.engine)
    assert len(_records(handle)) == 1


def test_connection_journal_a_source_the_setting_leaves_out_keeps_the_setting_reason():
    handle = _install(sources=("http",))
    kind = "connections-per-request"
    check = next(c for c in insights_service(handle.context).report()["checks"] if c["kind"] == kind)
    assert check["reason"] == NOT_RECORDED.format("connection")


def test_connection_journal_routes_a_release_without_scanning_the_registered_engines():
    handle = _install()
    registry = handle.context.capture.engine_registry
    scans = []

    class Counting(tuple):  # type: ignore[type-arg]
        __slots__ = ()

        def __iter__(self):
            scans.append(1)
            return super().__iter__()

    _use(handle.engine, 0)  # warm: the first release may learn which engine owns the pool
    registry._snapshot = Counting(registry._snapshot)  # type: ignore[attr-defined]
    scans.clear()
    for _ in range(5):
        _use(handle.engine, 0)
    assert len(_records(handle)) == 6
    assert scans == []


def test_connection_journal_a_pool_that_is_none_has_no_engine_name():
    handle = _install()
    registry = handle.context.capture.engine_registry
    try:
        name = registry.name_of_pool(None)  # a proxy with no ``_pool`` is no engine's pool, not an error
    except TypeError as exc:
        name = f"raised {exc}"
    assert name is None


def test_connection_journal_unarmed_optional_read_says_the_listener_is_off():
    handle = _install(sources=("connection", "sql", "http"))
    handle.context.capture.wiring.suspend_hook(HOOK_SQLA_LISTENERS)
    check = next(c for c in insights_service(handle.context).report()["checks"] if c["kind"] == "route-time-breakdown")
    assert "whose listener is not armed here" in str(check["reason"])
    assert NOT_RECORDED.format("connection") not in str(check["reason"])


def test_connection_journal_two_installs_each_journal_their_own_engines_release_outside_a_request():
    ours, theirs = _install(), _install()
    _use(ours.engine, 0)
    assert len(_records(ours)) == 1
    assert _records(theirs) == ()


def test_connection_journal_a_checkout_that_failed_after_the_listener_ran_offers_no_event():
    # review finding: a user checkout listener that raises makes SQLAlchemy check the record in again; the application
    # never obtained that connection, and BootUI's ``checkoutConnection`` only runs after ``getConnection`` returned
    handle = _install()

    def refuse(*_args: object) -> None:
        raise RuntimeError("tenant hook failed")

    sa.event.listen(sa.pool.Pool, "checkout", refuse)  # registered after sharpit's, so it runs after it
    try:
        with pytest.raises(RuntimeError, match="tenant hook failed"):
            handle.engine.connect()
    finally:
        sa.event.remove(sa.pool.Pool, "checkout", refuse)
    assert _records(handle) == ()


def _horizon(handle: Any) -> int | None:
    journal = handle.context.capture.journal
    assert journal is not None
    return journal.view([])[3]


# ported: EvidenceRing.lost (the loss start rides each event; #181)
def test_connection_journal_offers_the_loss_start_the_ring_would_compute(monkeypatch: pytest.MonkeyPatch):
    handle = _install()
    journal = handle.context.capture.journal
    offered: list[tuple[dict[str, object], int]] = []
    original = journal.offer_flat

    def spy(event: Any, size: int | None = None, started: int = -1) -> bool:
        offered.append((event, started))
        return original(event, size, started)

    monkeypatch.setattr(journal, "offer_flat", spy)
    token = _request(handle, "0123456789abcdef")
    try:
        _use(handle.engine)
    finally:
        REQUEST.reset(token)
    _use(handle.engine)  # no request, no trace: it names no unit of work
    (named, started), (unnamed, none) = [pair for pair in offered if pair[0]["source"] == "connection"]
    assert started == named["epochMillis"]
    assert none == 0
    assert unnamed["requestId"] is None


def test_connection_event_eviction_moves_the_horizon_to_its_start():
    handle = _install(("connection",), runtime_journal_max_events=1)
    token = _request(handle, "0123456789abcdef")
    try:
        _use(handle.engine)
    finally:
        REQUEST.reset(token)
    first = _only(handle)
    _use(handle.engine)  # the ring holds one event: the first connection is evicted
    assert _horizon(handle) == min(first["epochMillis"], int(time.time() * 1000))


def test_connection_event_of_no_request_does_not_move_the_horizon():
    handle = _install(("connection",), runtime_journal_max_events=1)
    _use(handle.engine)
    _use(handle.engine)
    assert _horizon(handle) is None


# code-review (#184, fc37f10c): a connection checked out before the hook is suspended and released after it is not
# journaled into the suspended capture
def test_connection_released_after_the_hook_is_suspended_is_not_journaled():
    handle = _install()
    conn = handle.engine.connect()
    conn.execute(sa.text("select 1"))
    handle.context.capture.wiring.suspend_hook(HOOK_SQLA_LISTENERS)
    conn.close()
    assert _records(handle) == ()
    handle.context.capture.wiring.resume_hook(HOOK_SQLA_LISTENERS)
    _use(handle.engine)
    assert len(_records(handle)) == 1  # and the producer works again after the resume
