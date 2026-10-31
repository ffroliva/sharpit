"""SQL Trace recorder, normaliser and category (F3, spec §7.3). Pure: no SQLAlchemy needed.

Ported from BootUI ``SqlStatementNormalizerTests`` (every case, cited per test), ``SqlTraceRecorderTests`` (cited per
test) and ``SqlTracingProxies.categoryOf``. Dropped, with reason: ``recordsNothingWhenDisabled`` (a disabled panel or
``SQL_TRACE_ENABLED=false`` builds no recorder at all), ``recordsNothingWhenCaptureGuardSuppressed`` (the ``INTERNAL``
marker is checked by the listener, see ``test_internal_statements_not_traced``), the idle-suspension cases (no idle
reclaim in sharpit), ``tracksWrappedDataSourceNames`` (data sources are the engine registry,
``tests/engine/test_sqla.py``), the trace-id provider and span-enricher cases (the trace id is the sharpit request
id) and the ``selectCallSite`` StackWalker cases (replaced by the frame-walk cases below).
"""

from __future__ import annotations

import functools
import re
import sys
import threading
from typing import Any

import pytest

from sharpit.engine.capture import sqltrace
from sharpit.engine.capture.sqltrace import (
    ENTRY_KEYS,
    GROUP_KEYS,
    REPORT_KEYS,
    STATS_KEYS,
    SqlTraceRecorder,
    category_of,
    normalize,
    normalize_sql,
    unavailable_report,
)
from sharpit.engine.masking import MASK, Exposure, Masker

MASKED = Masker(Exposure.MASKED, True)
WITH_PARAMETERS = Masker(Exposure.MASKED, True, capture_parameters=True)
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJyZXNldCJ9.c2lnbmF0dXJlLWJ5dGVz"


def _recorder(masker: Masker = MASKED, **kw: Any) -> SqlTraceRecorder:
    return SqlTraceRecorder(masker, **kw)


def _record(recorder: SqlTraceRecorder, sql: str = "select 1", **kw: Any) -> None:
    fields: dict[str, Any] = {"duration_ns": 1_000_000, "thread": "main", "connection_id": "c1", **kw}
    recorder.record(sql, **fields)


def _entries(recorder: SqlTraceRecorder) -> list[dict[str, Any]]:
    return recorder.report([])["entries"]


# --- SqlStatementNormalizer ------------------------------------------------------------------------------------------


def _fingerprint(sql: str) -> str:
    return normalize(sql).fingerprint


def test_replaces_string_and_numeric_literals():
    # ported: SqlStatementNormalizerTests.replacesStringAndNumericLiteralsSoEquivalentExecutionsAggregate
    first = _fingerprint("select * from users where id = 41 and name = 'ada'")
    second = _fingerprint("select * from users where id = 42 and name = 'grace'")
    assert first == second == "select * from users where id = ? and name = ?"


def test_never_leaves_a_literal_value():
    # ported: SqlStatementNormalizerTests.neverLeavesALiteralValueInTheNormalizedText
    result = normalize("insert into audit (actor, token) values ('ada@example.com', 'sk-live-9f3b')")
    assert "ada@example.com" not in result.sql
    assert "sk-live-9f3b" not in result.sql
    assert result.literal_count == 2


def test_folds_in_lists():
    # ported: SqlStatementNormalizerTests.foldsInListsSoListLengthDoesNotSplitOneStatementIntoMany
    three = _fingerprint("select * from t where id in (1, 2, 3)")
    thirty = _fingerprint("select * from t where id in (1,2,3,4,5,6,7,8,9,10)")
    assert three == thirty == "select * from t where id in (?)"


def test_case_insensitive_fingerprint_keeps_text_as_written():
    # ported: SqlStatementNormalizerTests.isCaseInsensitiveForGroupingButKeepsTheStatementAsWritten
    upper, lower = normalize("SELECT ID FROM USERS"), normalize("select id from users")
    assert upper.fingerprint == lower.fingerprint
    assert upper.sql == "SELECT ID FROM USERS"


def test_keeps_quoted_identifiers():
    # ported: SqlStatementNormalizerTests.keepsQuotedIdentifiersSoDifferentColumnsNeverCollapse
    assert _fingerprint('select "firstName" from "user"') != _fingerprint('select "lastName" from "user"')
    assert '"firstName"' in normalize_sql('select "firstName" from "user"')


def test_digits_inside_identifiers_are_not_literals():
    # ported: SqlStatementNormalizerTests.doesNotTreatDigitsInsideIdentifiersAsLiterals
    result = normalize("select t2.column1 from order_2024 t2 where t2.column1 = 7")
    assert result.sql == "select t2.column1 from order_2024 t2 where t2.column1 = ?"
    assert result.literal_count == 1


def test_collapses_whitespace_and_strips_comments():
    # ported: SqlStatementNormalizerTests.collapsesWhitespaceAndStripsComments
    result = normalize("select id\n  from users -- the comment\n  where id = 1 /* inline */ and active = true")
    assert result.sql == "select id from users where id = ? and active = ?"


@pytest.mark.parametrize(
    ("sql", "count"),
    [
        ("select * from t where id = 42", 1),
        ("select * from t where id in (1, 2)", 2),
        ("select * from t where name like 'a%'", 1),
        ("select * from t where age >= 18", 1),
        ("select 1, 'literal' from dual", 0),
        ("select * from t limit 50 offset 100", 0),
        ("select cast(x as decimal(10, 2)) from t", 0),
    ],
)
def test_predicate_literal_count(sql: str, count: int):
    # ported: SqlStatementNormalizerTests.countsLiteralsInPredicatePositionsSeparately,
    # doesNotCountProjectedOrPagingLiteralsAsPredicateLiterals
    assert normalize(sql).predicate_literal_count == count


def test_survives_unterminated_quotes():
    # ported: SqlStatementNormalizerTests.survivesUnterminatedQuotesFromTruncatedCapture
    assert normalize_sql("select * from t where name = 'ad") == "select * from t where name = ?"


def test_doubled_quote_escape():
    # ported: SqlStatementNormalizerTests.handlesDoubledQuoteEscapesWithoutSplittingTheLiteral
    result = normalize("select * from t where name = 'it''s' and id = 1")
    assert result.sql == "select * from t where name = ? and id = ?"
    assert result.literal_count == 2


def test_bounds_the_scan():
    # ported: SqlStatementNormalizerTests.boundsTheScanSoAPathologicalStatementCannotDominate
    assert len(normalize_sql("select * from t where x in (" + "1," * 30_000 + "1)")) < 1000


def test_masks_dollar_quoted_strings():
    # ported: SqlStatementNormalizerTests.masksPostgresDollarQuotedStrings
    result = normalize("select * from t where note = $$top secret$$ and tag = $x$vip$x$")
    assert result.sql == "select * from t where note = ? and tag = ?"
    assert result.predicate_literal_count == 2


def test_unterminated_dollar_run_left_alone():
    # ported: SqlStatementNormalizerTests.leavesAnUnterminatedDollarRunAloneRatherThanSwallowingTheStatement
    assert normalize_sql("select a$b$c from t where id = 5") == "select a$b$c from t where id = ?"


def test_double_quoted_run_that_cannot_be_an_identifier():
    # ported: SqlStatementNormalizerTests.masksADoubleQuotedRunThatCannotBeAnIdentifier
    assert normalize_sql('select * from t where name = "Ada Lovelace"') == "select * from t where name = ?"
    assert normalize_sql('select "firstName" from t where id = 1') == 'select "firstName" from t where id = ?'


def test_boolean_literals_aggregate():
    # ported: SqlStatementNormalizerTests.normalizesBooleanLiteralsSoEquivalentPredicatesAggregate
    assert _fingerprint("select * from t where active = true") == _fingerprint("select * from t where active = FALSE")


def test_collapses_in_lists_but_not_projections():
    # ported: SqlStatementNormalizerTests.collapsesInListsButNotProjectionsOrArguments
    assert normalize_sql("select * from t where id in (1, 2, 3)") == "select * from t where id in (?)"
    assert _fingerprint("select 1, 2 from dual") != _fingerprint("select 1 from dual")
    assert normalize_sql("insert into t (a, b) values (1, 2)") == "insert into t (a, b) values (?, ?)"


def test_empty_result_for_blank_sql():
    # ported: SqlStatementNormalizerTests.returnsAnEmptyResultForNullOrBlankSql
    assert normalize("   ").fingerprint == ""
    assert normalize("").sql == ""


def test_escape_string_literal():
    # derived: spec §7.3 names PostgreSQL E'...' strings; the backslash escape keeps the quote inside the literal
    assert "hunter2" not in normalize_sql(r"select * from u where p = E'hunter2\'s'")


# --- SqlTracingProxies.categoryOf ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sql", "category"),
    [
        *((f"{k} x", "SELECT") for k in ("SELECT", "WITH", "SHOW", "VALUES", "TABLE")),
        ("insert into t values (1)", "INSERT"),
        *((f"{k} x", "UPDATE") for k in ("UPDATE", "MERGE", "UPSERT")),
        ("delete from account", "DELETE"),
        *((f"{k} x", "DDL") for k in ("CREATE", "ALTER", "DROP", "TRUNCATE", "COMMENT", "RENAME", "GRANT", "REVOKE")),
        ("/* hint */ SELECT 1", "SELECT"),
        ("-- note\n  ((select 1))", "SELECT"),
        ("PRAGMA foreign_keys", "OTHER"),
        ("", "OTHER"),
    ],
)
def test_category_of_table(sql: str, category: str):
    # ported: SqlTracingProxies.categoryOf / firstKeyword (verbatim), SqlTracingProxiesTests category assertions
    assert category_of(sql) == category


# --- SqlTraceRecorder ------------------------------------------------------------------------------------------------


def test_evicts_oldest_and_counts_evictions():
    # ported: SqlTraceRecorderTests.evictsOldestBeyondCapacityAndCountsEvictions
    recorder = _recorder(max_entries=2)
    for sql in ("select first", "select second", "select third"):
        _record(recorder, sql)
    report = recorder.report([])
    assert [e["sql"] for e in report["entries"]] == ["select third", "select second"]
    assert (report["totalCaptured"], report["stats"]["evicted"]) == (3, 1)
    assert "Older queries were dropped; the buffer keeps the most recent 2." in report["warnings"]


def test_drops_parameters_when_capture_disabled():
    # ported: SqlTraceRecorderTests.dropsParametersWhenCaptureDisabled
    recorder = _recorder()
    _record(recorder, "select ?", parameters=("x",))
    entry = _entries(recorder)[0]
    assert entry["parameters"] == []
    assert entry["statementType"] == "PREPARED"


def test_keeps_parameters_and_thread_when_capture_enabled():
    # ported: SqlTraceRecorderTests.keepsParametersAndThreadWhenCaptureEnabled
    recorder = _recorder(WITH_PARAMETERS)
    _record(recorder, "select ?", parameters=("x",), thread="worker-1")
    entry = _entries(recorder)[0]
    assert (entry["parameters"], entry["thread"]) == (["'x'"], "worker-1")


def test_flags_slow_queries_by_threshold():
    # ported: SqlTraceRecorderTests.flagsSlowQueriesByThreshold, slowFlaggingDisabledWhenThresholdZero
    recorder = _recorder(slow_query_threshold_millis=100)
    _record(recorder, duration_ns=150_000_000)
    _record(recorder, duration_ns=50_000_000)
    assert [e["slow"] for e in _entries(recorder)] == [False, True]
    off = _recorder(slow_query_threshold_millis=0)
    _record(off, duration_ns=5_000_000_000)
    assert _entries(off)[0]["slow"] is False


def test_computes_aggregate_stats():
    # ported: SqlTraceRecorderTests.computesAggregateStats
    recorder = _recorder()
    _record(recorder, "select", duration_ns=10_000_000)
    _record(recorder, "update", parameters=(1,), duration_ns=200_000_000, rowcount=3)
    _record(recorder, "insert", parameters=[(1,)] * 5, executemany=True, duration_ns=50_000_000, success=False,
            error=RuntimeError("boom"))  # fmt: skip
    stats = recorder.report([])["stats"]
    assert stats == {
        "totalQueries": 3,
        "totalDurationMillis": 260,
        "maxDurationMillis": 200,
        "avgDurationMillis": 260 / 3,
        "slowQueries": 1,
        "failedQueries": 1,
        "batchExecutions": 1,
        "selectCount": 1,
        "insertCount": 1,
        "updateCount": 1,
        "deleteCount": 0,
        "otherCount": 0,
        "evicted": 0,
    }


def test_groups_repeated_selects_and_flags_n_plus_one():
    # ported: SqlTraceRecorderTests.groupsRepeatedSelectsAndFlagsNPlusOne (grouped on the normalised statement)
    recorder = _recorder(n_plus_one_threshold=5)
    for parent in range(6):
        _record(recorder, f"select * from child where parent_id = {parent}")
    _record(recorder, "select * from parent")
    _record(recorder, "update parent set x = ?", parameters=(1,))
    groups = recorder.report([])["topStatements"]
    assert len(groups) == 3
    top = groups[0]
    assert (top["sql"], top["executions"], top["potentialNPlusOne"], top["callSites"]) == (
        "select * from child where parent_id = ?", 6, True, []
    )  # fmt: skip
    assert [g["potentialNPlusOne"] for g in groups].count(True) == 1


def test_n_plus_one_needs_a_select_at_threshold():
    # derived: spec §7.3, potentialNPlusOne is a SELECT group with >= N_PLUS_ONE_THRESHOLD executions
    recorder = _recorder(n_plus_one_threshold=3)
    for _ in range(2):
        _record(recorder, "select * from a where id = 1")
    for _ in range(3):
        _record(recorder, "delete from b where id = 1")
    assert not any(g["potentialNPlusOne"] for g in recorder.report([])["topStatements"])
    _record(recorder, "select * from a where id = 2")
    groups = recorder.report([])["topStatements"]  # tie on 3 executions: ordered by sql
    assert [(g["category"], g["potentialNPlusOne"]) for g in groups] == [("DELETE", False), ("SELECT", True)]


def test_clear_empties_buffer_but_keeps_total():
    # ported: SqlTraceRecorderTests.clearEmptiesBufferButKeepsTotalCaptured
    recorder = _recorder()
    _record(recorder)
    recorder.clear()
    report = recorder.report([])
    assert (report["entries"], report["topStatements"], report["totalCaptured"]) == ([], [], 1)


def test_signals_on_record_clear_and_recording_change(monkeypatch: pytest.MonkeyPatch):
    # ported: SqlTraceRecorderTests.notifiesSubscribersOnRecordClearAndRecordingChange
    recorder = _recorder()
    ticks: list[int] = []
    monkeypatch.setattr(recorder.changes, "signal", lambda: ticks.append(1))
    _record(recorder)
    recorder.clear()
    recorder.set_recording(False)
    recorder.set_recording(False)  # no change, no tick
    assert len(ticks) == 3


def test_paused_records_nothing():
    # ported: SqlTraceRecorderTests.recordsNothingWhenPaused
    recorder = _recorder(recording=False)
    _record(recorder)
    report = recorder.report([])
    assert (report["entries"], report["capturing"]) == ([], False)
    assert "Recording is paused. Resume it to capture new queries." in report["warnings"]
    recorder.set_recording(True)
    _record(recorder)
    assert len(_entries(recorder)) == 1


def test_aggregates_capped_500_lru():
    # derived: spec §7.3, top-statement aggregates are capped at 500 keys, least recently seen evicted first
    recorder = _recorder(max_entries=10, n_plus_one_threshold=2)
    _record(recorder, "select * from kept")
    for table in range(500):
        _record(recorder, f"select * from t{table}")
        if table == 250:
            _record(recorder, "select * from kept")  # seen again: now newer than t0..t250
    assert recorder.aggregate_count == 500
    groups = {g["sql"]: g for g in recorder.report([])["topStatements"]}
    assert groups["select * from kept"]["executions"] == 2  # survived: t0 was evicted, not "kept"
    recorder2 = _recorder(max_entries=10)
    for table in range(501):
        _record(recorder2, f"select * from t{table}")
    _record(recorder2, "select * from t0")  # t0 was evicted, so it starts again at one execution
    assert recorder2.aggregate_count == 500
    assert next(g for g in recorder2.report([])["topStatements"] if g["sql"] == "select * from t0")["executions"] == 1


def test_top_statements_limit_and_order():
    # ported: SqlTraceRecorder.topStatements (executions desc, then sql, at most 20)
    recorder = _recorder(max_entries=500)
    for n in range(25):
        for _ in range(n % 3 + 1):
            _record(recorder, f"select * from t{n:02d}")
    groups = recorder.report([])["topStatements"]
    assert len(groups) == 20
    assert [(g["executions"], g["sql"]) for g in groups] == sorted(
        ((g["executions"], g["sql"]) for g in groups), key=lambda x: (-x[0], x[1])
    )


def test_concurrent_record_and_report():
    # derived: spec §7.3, sync endpoints record from several threads while a report is built
    recorder = _recorder(max_entries=50)
    stop = threading.Event()
    errors: list[BaseException] = []

    def reader() -> None:
        while not stop.is_set():
            try:
                recorder.report([])
            except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
                errors.append(exc)

    def writer(n: int) -> None:
        for i in range(500):
            _record(recorder, f"select * from w{n} where i = {i}")

    reading = threading.Thread(target=reader)
    reading.start()
    writers = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for w in writers:
        w.start()
    for w in writers:
        w.join()
    stop.set()
    reading.join()
    report = recorder.report([])
    assert errors == []
    assert report["totalCaptured"] == 4000
    assert report["stats"]["totalQueries"] + report["stats"]["evicted"] == 4000
    assert sum(g["executions"] for g in report["topStatements"]) == 4000  # 8 groups, all within the top 20


def test_literals_normalised_when_params_off():
    # derived: spec §7.3 masking, inline literals never reach the buffer while parameter capture is off
    statements = [
        "insert into users (name, password) values ('bob', 'hunter2')",
        "select * from notes where body = $$hunter2$$",
        r"select * from users where p = E'hunter2'",
    ]
    for masker in (MASKED, Masker(Exposure.FULL, True), Masker(Exposure.METADATA_ONLY, True, capture_parameters=True)):
        recorder = _recorder(masker)
        for sql in statements:
            _record(recorder, sql)
        assert "hunter2" not in str(recorder.report([]))
    assert _entries(recorder)[-1]["sql"] == "insert into users (name, password) values (?, ?)"


def test_raw_text_masked_when_params_on():
    # derived: spec §7.3, with parameter capture on the raw SQL goes through mask_text
    recorder = _recorder(WITH_PARAMETERS)
    _record(recorder, "update users set password = 'hunter2' where id = 4")
    entry = _entries(recorder)[0]
    assert entry["sql"] == f"update users set password = '{MASK}' where id = 4"
    assert recorder.report([])["topStatements"][0]["sql"] == "update users set password = ? where id = ?"


def test_parameter_caps_and_masking():
    # derived: spec §7.3 bind values, at most 5 sets x 5 values, 200 chars, dict by key and value, positional by value
    recorder = _recorder(WITH_PARAMETERS, max_parameter_length=20)
    _record(recorder, "insert", parameters=[tuple(range(7))] * 8, executemany=True)
    _record(recorder, "select", parameters={"password": "hunter2", "name": "bob", "tok": JWT, "long": "x" * 50})
    _record(recorder, "select", parameters=(JWT, "plain"))
    positional, named, batch = _entries(recorder)
    assert batch["batchSize"] == 8
    assert batch["parameters"] == ["0", "1", "2", "3", "4"] * 5
    assert named["parameters"] == [f"password={MASK}", "name='bob'", f"tok={MASK}", "long='" + "x" * 19 + "…"]
    assert positional["parameters"] == [MASK, "'plain'"]
    assert positional["batchSize"] == 0


def test_metadata_only_no_parameters_even_when_capture_on():
    # derived: spec §7.3, METADATA_ONLY suppresses parameters and SQL error text even when capture is on
    recorder = _recorder(Masker(Exposure.METADATA_ONLY, True, capture_parameters=True))
    _record(recorder, "select ?", parameters=("hunter2",), success=False, error=RuntimeError("password=hunter2"))
    report = recorder.report([])
    entry = report["entries"][0]
    assert (entry["parameters"], entry["errorMessage"], report["captureParameters"]) == ([], None, False)
    assert "hunter2" not in str(report)


def test_error_message_masked_and_inline_sql_normalised():
    # derived: spec §7.3, §11: [parameters: ...] dropped, and the [SQL: ...] copy of the statement normalised
    recorder = _recorder()
    sql = "insert into u (id, p) values (1, 'hunter2')"
    error = RuntimeError(f"(sqlite3.IntegrityError) UNIQUE\n[SQL: {sql}]\n[parameters: ('{JWT}',)]")
    _record(recorder, sql, success=False, error=error)
    message = _entries(recorder)[0]["errorMessage"]
    assert (
        message == f"(sqlite3.IntegrityError) UNIQUE\n[SQL: insert into u (id, p) values (?, ?)]\n[parameters: {MASK}]"
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            '(psycopg.errors.UniqueViolation) duplicate key value violates unique constraint "u_secret_key"\n'
            "DETAIL:  Key (secret)=(hunter2-xyz) already exists.",
            "(psycopg.errors.UniqueViolation) duplicate key value violates unique constraint ?",
        ),
        (
            '(psycopg.errors.InvalidTextRepresentation) invalid input syntax for type integer: "hunter2-xyz"',
            "(psycopg.errors.InvalidTextRepresentation) invalid input syntax for type integer: ?",
        ),
        (
            "(pymysql.err.IntegrityError) (1062, \"Duplicate entry 'hunter2-xyz' for key 'secret'\")",
            "(pymysql.err.IntegrityError) (1062, ?)",
        ),
    ],
)
def test_driver_message_values_dropped_with_parameters_off(message: str, expected: str):
    # derived: spec §11 every captured value masked; PostgreSQL and MySQL echo row values in their messages
    recorder = _recorder()
    sql = "insert into u (secret) values (%(secret)s)"
    error = RuntimeError(f"{message}\n[SQL: {sql}]\n[parameters: {{'secret': 'hunter2-xyz'}}]")
    _record(recorder, sql, success=False, error=error)
    stored = _entries(recorder)[0]["errorMessage"]
    assert "hunter2" not in stored
    assert stored == f"{expected}\n[SQL: {sql}]\n[parameters: {MASK}]"


def test_sql_cut_at_max_length():
    # ported: SqlTraceRecorder.truncate (strip, cut, ellipsis)
    recorder = _recorder(max_sql_length=20)
    _record(recorder, "  select abcdefghijklmnopqrstuvwxyz from t  ")
    assert _entries(recorder)[0]["sql"] == "select abcdefghijklm…"


def test_unavailable_report_and_keys():
    # ported: SqlTraceReport.unavailable, SqlTraceStatsDto.empty
    report = unavailable_report("why")
    assert tuple(report) == REPORT_KEYS
    assert (report["available"], report["unavailableReason"], report["entries"]) == (False, "why", [])
    assert tuple(report["stats"]) == STATS_KEYS
    assert set(report["stats"].values()) == {0}


def test_entry_and_group_keys():
    # ported: SqlTraceEntryDto, SqlTraceGroupDto record components
    recorder = _recorder()
    _record(recorder, request_id="r1", call_site="app:f:3")
    report = recorder.report(["sqlite+pysqlite:///"])
    assert tuple(report["entries"][0]) == ENTRY_KEYS
    assert tuple(report["topStatements"][0]) == GROUP_KEYS
    entry = report["entries"][0]
    assert (entry["traceId"], entry["callSite"], entry["connectionId"]) == ("r1", "app:f:3", "c1")
    assert report["dataSources"] == ["sqlite+pysqlite:///"]


def test_call_site_off_ignores_given_call_site():
    # ported: SqlTraceRecorderTests.omitsCallSiteWhenCaptureDisabled
    recorder = _recorder(capture_call_site=False)
    _record(recorder, call_site="app:f:3")
    assert _entries(recorder)[0]["callSite"] is None


# --- call site (frame walk) ------------------------------------------------------------------------------------------


def _app_function() -> str | None:
    return sqltrace.call_site(sys._getframe())  # noqa: SLF001


def test_call_site_is_first_application_frame():
    # derived: spec §7.3, the first application frame as module:function:line
    site = _app_function()
    assert site is not None, site
    assert re.fullmatch(r"test_sqltrace:_app_function:\d+", site), site


@pytest.mark.needs_sqlalchemy
def test_call_site_follows_greenlet_parent():
    # derived: spec §7.3, an AsyncSession listener runs in a greenlet with only SQLAlchemy frames
    greenlet = pytest.importorskip("greenlet")
    site = greenlet.greenlet(functools.partial(sqltrace.call_site, None)).switch()
    assert site is not None
    assert re.fullmatch(r"test_sqltrace:test_call_site_follows_greenlet_parent:\d+", site)


@pytest.mark.needs_sqlalchemy
def test_call_site_without_greenlet(monkeypatch: pytest.MonkeyPatch):
    # derived: spec §7.3, greenlet absent from sys.modules: only the plain stack is walked
    greenlet = pytest.importorskip("greenlet")
    child = greenlet.greenlet(functools.partial(sqltrace.call_site, None))
    monkeypatch.delitem(sys.modules, "greenlet")
    assert child.switch() is None


def test_call_site_walk_is_bounded():
    # derived: spec §7.3, at most 64 frames are walked
    here = sys._getframe()  # noqa: SLF001
    assert sqltrace.call_site(_library_frames(63, here)) is not None  # the app frame is the 64th
    assert sqltrace.call_site(_library_frames(64, here)) is None


def _library_frames(count: int, tail: object) -> Any:
    frame = tail
    for _ in range(count):
        frame = _Library(frame)
    return frame


class _Library:
    """A fake frame from an installed package (SQLAlchemy's own frames sit above the app's)."""

    f_code = type("Code", (), {"co_filename": "/venv/lib/site-packages/sqlalchemy/engine/base.py", "co_name": "x"})()
    f_globals = {"__name__": "sqlalchemy.engine.base"}
    f_lineno = 1

    def __init__(self, back: object) -> None:
        self.f_back = back
