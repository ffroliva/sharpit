"""Lifetime statement totals on the SQL recorder (lane A-sqlalchemy-statistics, Task 2)."""

from __future__ import annotations

from typing import Any

from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect

MASKED = Masker(Exposure.MASKED, True)


def _record(recorder: SqlTraceRecorder, sql: str = "select 1", millis: int = 1, **kw: Any) -> None:
    recorder.record(
        sql, duration_ns=millis * 1_000_000, thread="main", connection_id="c1", dialect=Dialect.POSTGRESQL, **kw
    )


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


DOUBLE_QUOTED_SECRET = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"


def test_max_sql_masks_a_double_quoted_secret_with_parameter_capture():
    # review A-sqlalchemy-statistics #1: normalize() keeps double-quoted text, so max_sql needs mask_text like the ring
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, capture_parameters=True))
    _record(recorder, f'select * from pay where key = "{DOUBLE_QUOTED_SECRET}"', millis=3)
    assert DOUBLE_QUOTED_SECRET not in (recorder.totals().max_sql or "")


def test_ring_row_masks_a_double_quoted_secret_without_parameter_capture():
    # 0.3.0 leak: normalize() kept an identifier-shaped double-quoted value (MySQL string literal) verbatim
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, f'select * from pay where key = "{DOUBLE_QUOTED_SECRET}"')
    assert DOUBLE_QUOTED_SECRET not in recorder.report([])["entries"][0]["sql"]


def test_top_statement_masks_a_double_quoted_secret_without_parameter_capture():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, f'select * from pay where key = "{DOUBLE_QUOTED_SECRET}"')
    assert DOUBLE_QUOTED_SECRET not in recorder.report([])["topStatements"][0]["sql"]


def test_double_quoted_value_is_a_placeholder_without_parameter_capture():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, 'select * from pay where name = "bob"')
    assert recorder.report([])["entries"][0]["sql"] == "select * from pay where name = ?"


def test_double_quoted_value_kept_with_parameter_capture():
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, capture_parameters=True))
    _record(recorder, 'select * from pay where name = "bob"')
    assert recorder.report([])["entries"][0]["sql"] == 'select * from pay where name = "bob"'


def test_max_time_counts_selects_only():
    # Hibernate's queryExecutionMaxTime covers queries only, not DML
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, "select a from t where id = 1", millis=5)
    _record(recorder, "update t set a = 2", millis=50)
    assert recorder.totals().max_millis == 5


def test_max_sql_is_a_select():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, "select a from t where id = 1", millis=5)
    _record(recorder, "update t set a = 2", millis=50)
    assert recorder.totals().max_sql == "select a from t where id = ?"


def test_clear_resets_max_time():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, "select 1", millis=9)
    recorder.clear()
    assert recorder.totals().max_millis == 0


def test_clear_resets_max_sql():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, "select 1", millis=9)
    recorder.clear()
    assert recorder.totals().max_sql is None


def test_counts_survive_clear():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, "select 1", millis=9)
    recorder.clear()
    assert recorder.totals().statements == 1


def test_max_after_clear_is_the_next_select():
    recorder = SqlTraceRecorder(MASKED)
    _record(recorder, "select 1", millis=9)
    recorder.clear()
    _record(recorder, "select 2", millis=3)
    assert recorder.totals().max_millis == 3
