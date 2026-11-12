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

from sharpit.engine.capture import sqltrace
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.sqltext import Dialect

CANARY = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiJkZWZlciJ9" + "." + "c2lnbmF0dXJl" + "LWRlZmVy"
PASSWORD = "plain" + "-pass-" + "deferral"
COMPACT_WIDTH = 18
ROWCOUNT, PARAMETERS = 8, 12  # positions in the compact row (``sqltrace._ROWCOUNT``, ``_PARAMETERS``)


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
    assert len(stored) == COMPACT_WIDTH, "the compact row has lost or gained a position"


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


def test_a_password_named_parameter_is_stored_as_the_mask_under_parameter_capture():
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, capture_parameters=True))
    _record(recorder, "update users set password = %(password)s", parameters={"password": PASSWORD, "id": 7})
    (stored,) = _stored(recorder)
    parameters = cast(tuple[Any, ...], stored)[PARAMETERS]
    assert f"password={MASK}" in parameters, "the compact row does not hold the mask for the password parameter"
    assert PASSWORD not in " ".join(_strings(stored)), "the planted password is in the compact row"


@pytest.mark.parametrize("bad", [None, "3", 2.5, True])
def test_a_rowcount_a_driver_cannot_make_an_int_is_stored_as_unknown_and_every_read_works(bad: Any):
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True))
    _record(recorder, "update pets set name = 'x'", rowcount=bad)
    (stored,) = _stored(recorder)
    assert cast(tuple[Any, ...], stored)[ROWCOUNT] == -1, f"rowcount {bad!r} reached the stored row"
    assert recorder.rows()[0]["affectedRows"] is None
    assert recorder.report([])["entries"][0]["affectedRows"] is None


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


def test_slow_is_the_verdict_at_record_time_not_the_threshold_at_read_time():
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True), slow_query_threshold_millis=100)
    _record(recorder, "select 1", duration_ns=150_000_000)
    _record(recorder, "select 2", duration_ns=50_000_000)
    recorder.slow_query_threshold_millis = 1_000
    report = recorder.report([])
    assert [e["slow"] for e in reversed(report["entries"])] == [True, False], "a read re-decided slow"
    assert [r["slow"] for r in recorder.rows()] == [True, False], "rows() re-decided slow"
    assert report["stats"]["slowQueries"] == 1, "stats.slowQueries disagrees with the recorded verdicts"


def test_every_entry_key_carries_its_own_recorded_value():
    """Distinct values in every field: a swapped position in the compact row shows as the wrong value under a key."""
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, capture_parameters=True), slow_query_threshold_millis=3)
    recorder.lifespan_phase = "STARTUP"
    _record(
        recorder,
        "insert into pets (name) values (%s)",
        duration_ns=7_654_321,
        thread="thread-x",
        connection_id="conn-y",
        parameters=[("rex",), ("fido",)],
        executemany=True,
        rowcount=5,
        batch_size=9,
        call_site="app.mod:fn:42",
    )
    other = SqlTraceRecorder(Masker(Exposure.MASKED, True), slow_query_threshold_millis=3)
    _record(other, "select 1", request_id="req-7", duration_ns=1_000_000)
    (entry,) = recorder.report([])["entries"]
    (row,) = recorder.rows()
    expected = {
        "id": 1,
        "sql": "insert into pets (name) values (%s)",
        "statementType": "PREPARED",
        "category": "INSERT",
        "durationMicros": 7_654,
        "durationMillis": 7,
        "success": True,
        "errorMessage": None,
        "affectedRows": 5,
        "batchSize": 9,
        "connectionId": "conn-y",
        "thread": "thread-x",
        "slow": True,
        "parameters": ["'rex'", "'fido'"],
        "traceId": None,
        "callSite": "app.mod:fn:42",
        "requestId": None,
        "requestPhase": "STARTUP",
    }
    assert {k: entry[k] for k in expected} == expected
    assert entry["timestamp"] == row["timestamp"] // 1_000_000
    assert row["phase"] == "STARTUP"
    (request_entry,) = other.report([])["entries"]
    assert request_entry["requestId"] == "req-7"
    assert request_entry["traceId"] == "req-7"
    assert request_entry["requestPhase"] is None
