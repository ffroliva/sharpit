"""The SQL Trace recorder stores a compact, already-masked row and builds the readable row only on read (perf lane B).

The listener's budget is per statement, so recording must not build the 22-key row dict; masking still happens at
record time, so the compact row holds nothing raw; and a read over a full ring must not hold the writers' lock while
it builds the readable rows.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any, cast

import pytest

from sharpit.engine.capture import sqltrace
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect

CANARY = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiJkZWZlciJ9" + "." + "c2lnbmF0dXJl" + "LWRlZmVy"
PASSWORD = "plain" + "-pass-" + "deferral"


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
    assert not isinstance(stored, dict), "the ring holds the 22-key row dict built at record time"


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
    real = getattr(sqltrace, "materialize", None)
    building = threading.Event()
    recorded = threading.Event()

    def slow(*args: Any) -> dict[str, Any]:
        if not building.is_set():
            building.set()
            assert recorded.wait(5), "a host statement waited for a read that was building rows"
        assert real is not None
        return real(*args)

    monkeypatch.setattr(sqltrace, "materialize", slow, raising=False)
    writer = threading.Thread(
        target=lambda: (building.wait(5), _record(recorder, "select 2"), recorded.set()), daemon=True
    )
    writer.start()
    report = recorder.report([])
    writer.join(5)
    assert building.is_set(), "report() did not build the readable rows through ``materialize``"
    assert recorded.is_set(), "the concurrent statement did not complete"
    assert len(report["entries"]) == 50, "the read is the ring as copied, before the concurrent statement"
