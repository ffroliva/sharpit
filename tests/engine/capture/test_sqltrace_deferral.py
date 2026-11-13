"""The SQL Trace recorder stores a compact, already-masked row and builds the readable row only on read (perf lane B).

The listener's budget is per statement, so recording must not build the 19-key row dict; masking still happens at
record time, so the compact row holds nothing raw; and a read over a full ring must not hold the writers' lock while
it builds the readable rows.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any, cast

import pytest

from sharpit.engine.capture import sqltrace, transactions
from sharpit.engine.capture.sqltrace import (  # pyright: ignore[reportPrivateUsage]
    _PARAMETERS,  # noqa: PLC2701
    _PHASE,  # noqa: PLC2701
    SqlTraceRecorder,
    compact_dto,
    materialize,
)
from sharpit.engine.capture.transactions import TransactionRecorder
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.sqltext import Dialect

CANARY = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiJkZWZlciJ9" + "." + "c2lnbmF0dXJl" + "LWRlZmVy"
PASSWORD = "plain" + "-pass-" + "deferral"
COMPACT_WIDTH = 18


def _record(recorder: SqlTraceRecorder, sql: str = "select 1", **kw: Any) -> None:
    fields: dict[str, Any] = {
        "duration_ns": 1_000_000,
        "thread": "main",
        "connection_id": "c1",
        "dialect": Dialect.POSTGRESQL,
        **kw,
    }
    recorder.record(sql, **fields)


def _stored(recorder: SqlTraceRecorder) -> list[object]:
    return list(recorder._entries)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - the stored form itself


def _strings(value: object) -> list[str]:
    """Every string reachable from a stored row: tuples, lists, dicts and NamedTuples (``Shape``)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        items: list[object] = [*value.keys(), *value.values()]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        return [s for item in items for s in _strings(item)]
    if isinstance(value, list | tuple):
        return [s for item in cast(Sequence[object], value) for s in _strings(item)]
    return []


def test_recording_a_statement_builds_no_row_dict():
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True))
    _record(recorder, "select * from pets where id = 1", parameters={"id": 1}, request_id="r1")
    (stored,) = _stored(recorder)
    assert not isinstance(stored, dict), "the ring holds the 19-key row dict built at record time"
    assert isinstance(stored, tuple), "the ring holds something other than the compact tuple"
    assert len(cast(tuple[object, ...], stored)) == COMPACT_WIDTH, "the compact row has lost or gained a position"


@pytest.mark.parametrize("capture", [False, True])
@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY])
def test_the_compact_row_holds_no_raw_sql_or_parameter_value(exposure: Exposure, capture: bool):
    recorder = SqlTraceRecorder(Masker(exposure, True, capture_parameters=capture))
    _record(recorder, f"update users set token = '{CANARY}' where note = '{PASSWORD}'")
    _record(
        recorder,
        "update users set token = %(token)s, password = %(password)s",
        parameters={"token": CANARY, "password": PASSWORD},
    )
    _record(recorder, "insert into t (a) values (%s)", parameters=[(CANARY,), (PASSWORD,)], executemany=True)
    error = RuntimeError(f"token={CANARY} [SQL: update users set password = '{PASSWORD}']")
    _record(recorder, f"update users set password = '{PASSWORD}'", error=error, success=False)
    stored = " ".join(_strings(_stored(recorder)))
    assert CANARY[:12] not in stored, "a planted token reached the stored row"
    assert "eyJzdWIi" not in stored, "a fragment of a planted token reached the stored row"
    if not capture:  # capture on shows non-secret values by design; a password-named one is masked either way
        assert PASSWORD not in stored, "a planted literal reached the stored row with parameter capture off"


def test_a_full_ring_read_does_not_hold_the_recorder_lock_while_building_rows(monkeypatch: pytest.MonkeyPatch):
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True), max_entries=50)
    for n in range(50):
        _record(recorder, f"select * from pets where id = {n}")
    real = getattr(sqltrace, "compact_dto", None)
    building = threading.Event()
    recorded = threading.Event()

    def slow(*args: Any) -> dict[str, Any]:
        if not building.is_set():
            building.set()
            assert recorded.wait(5), "a host statement waited for a read that was building rows"
        assert real is not None
        return real(*args)

    monkeypatch.setattr(sqltrace, "compact_dto", slow, raising=False)
    writer = threading.Thread(
        target=lambda: (building.wait(5), _record(recorder, "select 2"), recorded.set()), daemon=True
    )
    writer.start()
    report = recorder.report([])
    writer.join(5)
    assert building.is_set(), "report() did not build the readable rows through ``compact_dto``"
    assert recorded.is_set(), "the concurrent statement did not complete"
    assert len(report["entries"]) == 50, "the read is the ring as copied, before the concurrent statement"
    assert "select ?" not in [e["sql"] for e in report["entries"]], "the read saw the statement recorded during it"
    assert recorder.rows()[-1]["sql"] == "select ?", "the concurrent statement is not in the ring after the read"


def test_a_password_named_parameter_is_stored_as_the_mask_under_parameter_capture():
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, capture_parameters=True))
    _record(recorder, "update users set password = %(password)s", parameters={"password": PASSWORD, "id": 7})
    (stored,) = _stored(recorder)
    parameters = cast(tuple[Any, ...], stored)[_PARAMETERS]
    assert f"password={MASK}" in parameters, "the compact row does not hold the mask for the password parameter"
    assert PASSWORD not in " ".join(_strings(stored)), "the planted password is in the compact row"


@pytest.mark.parametrize(
    ("rowcount", "error", "affected"),
    [(5, None, 5), (0, None, 0), (-1, None, None), (5, RuntimeError("boom"), None)],
)
def test_affected_rows_follow_base_a_failed_or_negative_count_reports_none(
    rowcount: int, error: BaseException | None, affected: int | None
):
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True))
    _record(recorder, "update pets set name = 'x'", rowcount=rowcount, error=error)
    assert recorder.rows()[0]["affectedRows"] == affected
    assert recorder.report([])["entries"][0]["affectedRows"] == affected


def test_the_timestamp_is_taken_before_the_parameters_are_rendered(monkeypatch: pytest.MonkeyPatch):
    clock = iter(range(1_000, 1_000_000, 1_000))
    monkeypatch.setattr(sqltrace, "time", SimpleNamespace(time_ns=lambda: next(clock)))
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, capture_parameters=True))
    real = recorder._parameters  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def slow_render(parameters: object, executemany: bool) -> list[str]:
        next(clock)  # rendering takes time: a clock read after it is later than one before it
        return real(parameters, executemany)

    monkeypatch.setattr(recorder, "_parameters", slow_render)
    _record(recorder, "select * from pets where id = %s", parameters=(1,))
    assert recorder.rows()[0]["timestamp"] == 1_000, "the timestamp was taken after the parameters were rendered"


def test_slow_is_decided_at_record_for_the_entry_and_at_read_for_the_stats():
    """Base: the entry's ``slow`` is the verdict when it was recorded; ``stats.slowQueries`` uses today's threshold."""
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True), slow_query_threshold_millis=100)
    _record(recorder, "select 1", duration_ns=150_000_000)
    _record(recorder, "select 2", duration_ns=50_000_000)
    recorder.slow_query_threshold_millis = 1_000
    report = recorder.report([])
    assert [e["slow"] for e in reversed(report["entries"])] == [True, False], "an entry re-decided slow at read"
    assert [r["slow"] for r in recorder.rows()] == [True, False], "rows() re-decided slow at read"
    assert report["stats"]["slowQueries"] == 0, "stats.slowQueries kept the record-time verdict, not today's threshold"
    recorder.slow_query_threshold_millis = 40
    assert recorder.report([])["stats"]["slowQueries"] == 2, "stats.slowQueries ignored the lowered threshold"


def test_the_lifespan_phase_is_gated_once_at_record():
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True))
    recorder.lifespan_phase = "STARTUP"
    _record(recorder, "select 1", request_id="req-1")
    _record(recorder, "select 2")
    request_row, lifespan_row = (cast(tuple[Any, ...], s) for s in _stored(recorder))
    assert request_row[_PHASE] is None, "a request's row stores the lifespan phase and leaves the gate to every read"
    assert lifespan_row[_PHASE] == "STARTUP"


def test_the_counters_are_read_under_the_writers_lock():
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True), max_entries=1)
    taken: list[int] = []
    real = recorder._lock  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    class Probe:
        def __enter__(self) -> object:
            taken.append(1)
            return real.__enter__()

        def __exit__(self, *exc: object) -> object:
            return real.__exit__(*exc)

    _record(recorder)
    _record(recorder)
    recorder._lock = Probe()  # type: ignore[assignment]  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    counters = recorder.counters()
    assert (counters.captured, counters.evicted) == (2, 1)
    assert taken == [1], "counters() must read both numbers in one acquisition of the lock"


def _distinct_recorder() -> SqlTraceRecorder:
    """Three rows; no field of a row shares its value with another field (the bools differ on some row)."""
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, capture_parameters=True), slow_query_threshold_millis=3)
    recorder.lifespan_phase = "STARTUP"
    _record(  # id 1: no request, during STARTUP; slow, not prepared, ok
        recorder, "select 1", duration_ns=4_321_000, thread="thread-a", connection_id="conn-a", rowcount=11,
        call_site="app.one:f:1",
    )  # fmt: skip
    _record(  # id 2: no request, during STARTUP; the only row with an error; fast, prepared, failed
        recorder, "update pets set name = %s", duration_ns=1_234_567, thread="thread-b", connection_id="conn-b",
        parameters=("rex",), error=RuntimeError("boom-err"), rowcount=6, call_site="app.two:g:2",
    )  # fmt: skip
    _record(  # id 3: a request's row during STARTUP; slow, prepared, failed without an error, a batch
        recorder, "insert into pets (name) values (%s)", duration_ns=7_654_321, thread="thread-x",
        connection_id="conn-y", parameters=[("rex",), ("fido",)], executemany=True, success=False, rowcount=5,
        batch_size=9, request_id="req-7", call_site="app.mod:fn:42",
    )  # fmt: skip
    return recorder


# the values both views carry, by statement id
_SHARED = {
    1: {
        "id": 1, "sql": "select ?", "statementType": "STATEMENT", "category": "SELECT", "durationMicros": 4_321,
        "durationMillis": 4, "success": True, "errorMessage": None, "affectedRows": 11, "batchSize": 0,
        "connectionId": "conn-a", "thread": "thread-a", "slow": True, "parameters": [], "traceId": None,
        "callSite": "app.one:f:1",
    },
    2: {
        "id": 2, "sql": "update pets set name = ?", "statementType": "PREPARED", "category": "UPDATE",
        "durationMicros": 1_234, "durationMillis": 1, "success": False, "errorMessage": "boom-err",
        "affectedRows": None, "batchSize": 0, "connectionId": "conn-b", "thread": "thread-b", "slow": False,
        "parameters": ["'rex'"], "traceId": None, "callSite": "app.two:g:2",
    },
    3: {
        "id": 3, "sql": "insert into pets (name) values (?)", "statementType": "PREPARED", "category": "INSERT",
        "durationMicros": 7_654, "durationMillis": 7, "success": False, "errorMessage": None, "affectedRows": 5,
        "batchSize": 9, "connectionId": "conn-y", "thread": "thread-x", "slow": True,
        "parameters": ["'rex'", "'fido'"], "traceId": "req-7", "callSite": "app.mod:fn:42",
    },
}  # fmt: skip
_PHASES = {1: "STARTUP", 2: "STARTUP", 3: None}  # a request's row has no lifespan phase
_REQUESTS = {1: None, 2: None, 3: "req-7"}


def test_every_entry_key_carries_its_own_recorded_value():
    """A swapped position in the compact row shows as the wrong value under a key, in the report AND in ``rows()``."""
    recorder = _distinct_recorder()
    entries = {e["id"]: e for e in recorder.report([])["entries"]}
    rows = {r["id"]: r for r in recorder.rows()}
    for n, expected in _SHARED.items():
        entry, row = entries[n], rows[n]
        assert {k: entry[k] for k in expected} == expected, f"report entry {n}"
        assert {k: row[k] for k in expected} == expected, f"rows() row {n}"
        assert (entry["requestId"], entry["requestPhase"]) == (_REQUESTS[n], _PHASES[n]), f"report entry {n} request"
        assert row["phase"] == _PHASES[n], f"rows() row {n} phase"
        assert (entry["executionId"], entry["threadKind"]) == (None, None)
        assert entry["timestamp"] == row["timestamp"] // 1_000_000, f"timestamp ms of {n}"


def test_the_entry_and_the_readable_row_agree_on_every_shared_key():
    recorder = _distinct_recorder()
    for stored in _stored(recorder):
        compact = cast(Any, stored)
        built, entry = materialize(compact), compact_dto(compact)
        shared = (built.keys() & entry.keys()) - {"timestamp"}
        assert {"id", "success", "slow", "connectionId", "thread", "errorMessage"} <= shared
        assert {k: entry[k] for k in shared} == {k: built[k] for k in shared}


def test_the_recorder_returns_the_entries_newest_first_without_a_report():
    recorder = _distinct_recorder()
    assert recorder.entries() == recorder.report([])["entries"]  # pyright: ignore[reportAttributeAccessIssue]


def test_one_call_returns_a_requests_statements_and_entries_together():
    recorder = _distinct_recorder()
    _record(recorder, "select 9", request_id="req-8")
    statements, entries = recorder.request_view("req-7")  # pyright: ignore[reportAttributeAccessIssue]
    assert [s["id"] for s in statements] == [3]
    assert [e["id"] for e in entries] == [3]
    assert "shape" in statements[0]
    assert "requestId" in entries[0]
    assert recorder.request_view("nobody") == ([], [])  # pyright: ignore[reportAttributeAccessIssue]


def test_the_transactions_report_reads_the_entries_without_building_a_sql_report(monkeypatch: pytest.MonkeyPatch):
    masker = Masker(Exposure.MASKED, True)
    trace = SqlTraceRecorder(masker)
    _record(trace)

    def forbidden(*args: Any) -> dict[str, Any]:
        raise AssertionError("context_report built the stats and top statements it never reads")

    monkeypatch.setattr(trace, "report", forbidden)
    capture = SimpleNamespace(transactions=TransactionRecorder(masker, application=lambda: None), sql_trace=trace)
    settings = SimpleNamespace(sql_trace_enabled=True, transactions_enabled=True)
    report = transactions.context_report(cast(Any, SimpleNamespace(capture=capture, settings=settings)))
    assert report["available"] is True
