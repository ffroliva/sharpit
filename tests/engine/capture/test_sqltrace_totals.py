"""Lifetime statement totals on the SQL recorder (lane A-sqlalchemy-statistics, Task 2)."""

from __future__ import annotations

from typing import Any

from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker

MASKED = Masker(Exposure.MASKED, True)


def _record(recorder: SqlTraceRecorder, sql: str = "select 1", millis: int = 1, **kw: Any) -> None:
    recorder.record(sql, duration_ns=millis * 1_000_000, thread="main", connection_id="c1", **kw)


def test_totals_count_every_statement():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, "select 1")
    _record(recorder, "insert into t values (1)")
    _record(recorder, "update t set a = 1")
    assert recorder.totals().statements == 3


def test_totals_selects_only_select_category():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, "select 1")
    _record(recorder, "select 2 from t")
    _record(recorder, "delete from t")
    assert recorder.totals().selects == 2


def test_totals_max_keeps_slowest():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, "select a from slow where id = 7", millis=40)
    _record(recorder, "select 1", millis=5)
    totals = recorder.totals()
    assert totals.max_millis == 40
    assert totals.max_sql == "select a from slow where id = ?"


def test_totals_max_sql_is_none_before_any_statement():
    assert SqlTraceRecorder(MASKED).totals().max_sql is None


def test_totals_survive_clear():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, "select 1", millis=9)
    recorder.clear()
    totals = recorder.totals()
    assert totals.statements == 1
    assert totals.max_millis == 9


def test_totals_survive_eviction():
    recorder = SqlTraceRecorder(MASKED, max_entries=5)
    for _ in range(12):
        _record(recorder)
    assert len(recorder.rows()) == 5
    assert recorder.totals().statements == 12


def test_paused_recorder_adds_nothing():
    recorder = SqlTraceRecorder(MASKED, recording=False)
    _record(recorder)
    assert recorder.totals().statements == 0


def test_totals_max_sql_never_holds_a_literal_with_parameter_capture():
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, capture_parameters=True))
    _record(recorder, "select * from t where token = 'sk-live-9f3b'", millis=3)
    assert "sk-live-9f3b" not in (recorder.totals().max_sql or "")
