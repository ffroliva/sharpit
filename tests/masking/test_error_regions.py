"""Error text by region (spec §3): each region has one owner, and every job reads raw text.

Real driver text comes from ``tests/fixtures/sql_errors``, captured from live servers. A string here is a shape a
scenario names, or a live SQLite error.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

import psycopg.errors
import pymysql
import pytest

pytest.importorskip("sqlalchemy")
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, StatementError
from sqlalchemy.types import String, TypeDecorator
from tests.engine.collectors.mysql.fakes import FakeMySqlConnection

from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.engine.capture.logtail import SharpitLogHandler
from sharpit.engine.capture.sqltrace import SqlTraceRecorder, mask_error
from sharpit.engine.collectors.mysql.sections import DataSourceData, RowLimits, collect_replication
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.sqltext import Dialect, error_text, statement_text

pytestmark = pytest.mark.needs_sqlalchemy
ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sql_errors"
MANIFEST: list[dict[str, Any]] = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
MASKER = Masker(Exposure.MASKED, True)
CAPTURING = Masker(Exposure.MASKED, True, capture_parameters=True)
SECRET = "hunter2plain"
LINK = "https://sqlalche.me/e/21/gkpj"
LINK_LINE = f"(Background on this error at: {LINK})"
DRIVER = "(sqlite3.IntegrityError) UNIQUE constraint failed: u.name"
# owner ruling 2026-11-08: a stated limit (CHANGELOG, MVP spec section 14); strict: a fix that closes one fails
TEXT_ONLY_LIMIT = pytest.mark.xfail(
    strict=True, reason="owner ruling 2026-11-08: text-only surface, unquoted driver value; stated limit"
)
MARKERS = re.compile(r"mk[0-9a-f]{10}")
SECTION = re.compile(r"^##### (.+?) #####\n", re.MULTILINE)
SEPARATORS = {"cr": "\r", "nel": "\x85", "ls": " ", "ps": " ", "vt": "\x0b", "ff": "\x0c", "fs": "\x1c"}
# the statement a case must keep, as the capture script wrote it, with no lexer involved
KEPT = {
    "unique_params": "VALUES (",
    "hide_parameters": "VALUES (",
    "syntax_inline_literal": "SELECT name FROM u WHERE name = ? AND",
    "syntax_mid_literal": "SELECT name FROM u WHERE AND name = ?",
    "bracket_block": "VALUES (",
    "closer_in_param": "VALUES (",
    "closer_in_literal": "VALUES (",
    "sql_marker_in_param": "VALUES (",
    "sql_marker_in_literal": "VALUES (",
    "multiline_literal": "VALUES (",
    "crlf": "VALUES (",
    "long_params": "VALUES (",
    "many_params": "VALUES (",
    "engine_log": "VALUES (",
    "engine_log_long": "VALUES (",
    "pg_line_hint": "SELECT name + ? FROM u WHERE name = ?",
    "pg_context": "DO ?",
    "mysql_no_backslash_param": "VALUES (",
    "bracket_syntax": "FROM u WHERE name = ? AND",
}
# past the scan's limit a block has no closer, and a statement that reads two ways stops at its first quote
NO_CLOSER = {"long_statement", "mysql_no_backslash_literal"}


def sections(entry: dict[str, Any]) -> dict[str, str]:
    """A fixture's sections by name, raw: CRLF and all."""
    text = (ROOT / str(entry["file"])).read_bytes().decode("utf-8")
    parts = SECTION.split(text)
    return {parts[i]: parts[i + 1][:-1] for i in range(1, len(parts), 2)}


def shown(text: str, dialect: Dialect = Dialect.POSTGRESQL) -> str:
    masked = mask_error(MASKER, text, dialect)
    assert masked is not None
    return masked


def recorded(text: str, sql: str = "SELECT 2", masker: Masker = MASKER) -> str | None:
    recorder = SqlTraceRecorder(masker, max_sql_length=10**6)
    recorder.record(
        sql, duration_ns=1, thread="t", connection_id=None, error=Exception(text), dialect=Dialect.POSTGRESQL
    )
    return recorder.rows()[-1]["errorMessage"]


def logged(name: str, message: str, masker: Masker = MASKER, family: Dialect | None = None) -> str | None:
    handler = SharpitLogHandler.__new__(SharpitLogHandler)
    handler.masker = masker
    handler.application = lambda: family
    # as SQLAlchemy logs a statement: the text is the message, with no args (a record with args carries values)
    record = logging.LogRecord(name, logging.INFO, __file__, 1, message, None, None)
    line = handler.line(record)
    assert line is not None
    return line["message"]


def error(statement: str, parameters: str = "(1, 'bound-value-7')", driver: str = DRIVER) -> str:
    return f"{driver}\n[SQL: {statement}]\n[parameters: {parameters}]\n{LINK_LINE}"


COMPLETE = [e for e in MANIFEST if not e["case"].startswith("raw_")]
# the proof a surface holding the exception gets from its chain (Task 27): since Task 28 the text no longer gives it
PROOF = dict.fromkeys(("pymysql", "mysqlclient", "aiomysql"), Dialect.MYSQL_FAMILY)


@pytest.mark.parametrize("entry", COMPLETE, ids=lambda e: e["file"])
def test_real_error_keeps_statement_and_link(entry: dict[str, Any]) -> None:
    raw = sections(entry)["str(exc)"]
    masked = shown(raw, PROOF.get(entry["driver"], Dialect.POSTGRESQL))
    assert MARKERS.search(masked) is None
    assert re.search(r"\(Background on this error at: https://sqlalche\.me/e/\d+/\w+\)$", masked) is not None
    if entry["case"] not in NO_CLOSER:
        assert KEPT[entry["case"]] in masked


@pytest.mark.parametrize("entry", MANIFEST, ids=lambda e: e["file"])
def test_a_real_traceback_shows_no_value(entry: dict[str, Any]) -> None:
    assert MARKERS.search(shown(sections(entry)["traceback"])) is None


@pytest.mark.parametrize("entry", COMPLETE, ids=lambda e: e["file"])
def test_a_real_traceback_keeps_its_frames_and_statement(entry: dict[str, Any]) -> None:
    masked = shown(sections(entry)["traceback"], PROOF.get(entry["driver"], Dialect.POSTGRESQL))
    assert '  File "<repo>' in masked
    if entry["case"] not in NO_CLOSER:
        assert KEPT[entry["case"]] in masked


@pytest.mark.parametrize("entry", MANIFEST, ids=lambda e: e["file"])
def test_a_bare_cause_shows_no_value(entry: dict[str, Any]) -> None:
    """``exc.orig`` and ``causes[]``: a driver's own message, with no class before it."""
    found = sections(entry)
    raw = found["str(exc)"] if entry["case"].startswith("raw_") else found["str(exc.orig)"]
    assert MARKERS.search(shown(raw)) is None


def test_a_closer_past_the_scan_limit_is_not_a_closer() -> None:
    masked = shown(f"{DRIVER}\n[SQL: SELECT {'1, ' * 8000}'{SECRET}']\n[parameters: ('{SECRET}',)]\n{LINK_LINE}")
    assert SECRET not in masked
    # owner ruling 2026-11-08 (E): a run-on that stops at the parameters line ends there, and they show as the constant
    assert masked.endswith(f"[parameters: {MASK}]\n{LINK_LINE}")


def test_a_bracket_in_the_statement_is_not_the_closer() -> None:
    masked = shown(error("SELECT arr[1] FROM t WHERE a = 'x'"))
    assert "[SQL: SELECT arr[?] FROM t WHERE a = ?]\n[parameters: ******]\n" in masked


def test_block_starts_at_a_line_start() -> None:
    text = (
        f'(psycopg2.errors.UniqueViolation) duplicate key "u"\nDETAIL:  Key (a)=({SECRET} [SQL: x) already exists.\n'
        f"\n[SQL: INSERT INTO u VALUES (1)]\n{LINK_LINE}"
    )
    masked = shown(text)
    assert SECRET not in masked
    assert "[SQL: INSERT INTO u VALUES (?)]" in masked


def test_second_block_fails_closed() -> None:
    masked = shown(f"{DRIVER}\n[SQL: SELECT 1]\n[SQL: SELECT {SECRET} FROM t]\n{LINK_LINE}")
    assert masked == f"{DRIVER}\n[SQL: SELECT ?]\n[SQL: {MASK}]\n{LINK_LINE}"


def test_frame_code_lines_hide_quotes() -> None:
    text = (
        'Traceback (most recent call last):\n  File "/srv/app/db.py", line 12, in run\n'
        f"    conn.exec_driver_sql(\"SELECT '{SECRET}'\")\nsqlalchemy.exc.IntegrityError: {DRIVER}\n[SQL: SELECT 1]"
    )
    masked = shown(text)
    assert SECRET not in masked
    assert '  File "/srv/app/db.py", line 12, in run\n    conn.exec_driver_sql(?)\n' in masked


def test_driver_value_holding_a_quote() -> None:
    masked = shown(f"(psycopg2.errors.Error) invalid value 'it's {SECRET}' for column 'a'\n[SQL: SELECT 1]")
    assert masked.startswith("(psycopg2.errors.Error) invalid value ?\n[SQL: ")
    assert SECRET not in masked


def test_recorder_keeps_no_frames() -> None:
    text = (
        'Traceback (most recent call last):\n  File "/srv/app/db.py", line 12, in run\n    conn.run()\n'
        f"sqlalchemy.exc.IntegrityError: {DRIVER}\n[SQL: SELECT 1]\n{LINK_LINE}"
    )
    masked = recorded(text)
    assert masked is not None
    assert "db.py" not in masked
    assert "[SQL: SELECT ?]" in masked


def test_a_driver_error_with_no_block_takes_the_driver_region() -> None:
    assert shown(f"(sqlite3.OperationalError) near '{SECRET}': syntax error") == (
        "(sqlite3.OperationalError) near ?: syntax error"
    )


@pytest.mark.parametrize("separator", SEPARATORS.values(), ids=SEPARATORS)
def test_a_detail_line_never_survives(separator: str) -> None:
    masked = shown(f'(psycopg2.errors.UniqueViolation) duplicate key "u"{separator}DETAIL:  Key (a)=({SECRET}) exists')
    assert SECRET not in masked


def test_a_literal_cannot_switch_mysql_mode() -> None:
    """A ``"`` run is a name in generic text and a string on MySQL: a literal with ``pymysql.`` must not switch it."""
    masked = shown(f"{DRIVER}\n[SQL: SELECT 'pymysql.x', \"c\" FROM t]\n{LINK_LINE}")
    assert '"c"' in masked


def test_a_driver_value_cannot_switch_mysql_mode() -> None:
    masked = shown(f"(sqlite3.Error) bad 'pymysql.x'\n[SQL: SELECT \"c\" FROM t]\n{LINK_LINE}")
    assert '"c"' in masked


# derived: replaces test_a_driver_line_does_switch_mysql_mode, whose behaviour Task 28 removes. Architecture spec §6,
# "Text never names a dialect": a database can return a driver-shaped string as a value, so a driver line marks a
# region and never picks the reading: a MySQL driver line on a surface whose proof is not MySQL's is a conflict, which
# hides the block.
def test_a_driver_line_chooses_no_reading() -> None:
    masked = shown(f"(pymysql.err.Error) (1064, 'bad')\n[SQL: SELECT \"c\" FROM t]\n{LINK_LINE}")
    assert f"[SQL: {MASK}]" in masked


DRIVER_LINES = {
    "pymysql": "(pymysql.err.Error) (1064, 'bad')",
    "mysqldb": "(MySQLdb.OperationalError) (1064, 'bad')",
    "mysql_connector": "(mysql.connector.errors.ProgrammingError) 1064 (42000): bad",
    "mariadb": "(mariadb.ProgrammingError) bad",
    "asyncmy": "(asyncmy.errors.ProgrammingError) (1064, 'bad')",
    "psycopg": "(psycopg.errors.SyntaxError) bad",
    "sqlite3": "(sqlite3.OperationalError) bad",
}
HIDDEN_BLOCK = f"[SQL: {MASK}]"


# derived: architecture spec §6, "Driver text marks regions and can reveal a conflict, which hides. It cannot authorise
# a reading": whatever driver a line names, the block is the given dialect's reading of it, or hidden.
@pytest.mark.parametrize("dialect", list(Dialect), ids=[dialect.name.lower() for dialect in Dialect])
@pytest.mark.parametrize("line", DRIVER_LINES.values(), ids=DRIVER_LINES)
def test_a_driver_name_in_text_can_only_hide(line: str, dialect: Dialect) -> None:
    sql = "SELECT \"c\", 'v' FROM t"
    masked = shown(f"{line}\n[SQL: {sql}]\n{LINK_LINE}", dialect)
    # hiding too much is caught elsewhere: test_real_error_keeps_statement_and_link (with PROOF) and
    # test_a_sensitive_column_keeps_where on the surfaces that carry a proof
    assert f"[SQL: {statement_text(MASKER, sql, dialect)}]" in masked or HIDDEN_BLOCK in masked


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (f"SELECT name FROM u WHERE name = '{SECRET}' -- note", "SELECT name FROM u WHERE name = ?"),
        ("UPDATE t SET note='x', b=1", "UPDATE t SET note=?, b=?"),
        ("BEGIN (implicit)", "BEGIN (implicit)"),
        ("ROLLBACK", "ROLLBACK"),
    ],
    ids=["literal-and-note", "update", "begin", "rollback"],
)
def test_an_engine_log_record_is_a_statement(record: str, expected: str) -> None:
    # derived: Task 29, an application on SQLite; with no family the record is UNSUPPORTED's and hidden
    assert logged("sqlalchemy.engine.Engine", record, family=Dialect.SQLITE) == expected


def test_an_engine_log_record_with_no_family_is_hidden() -> None:
    assert (
        logged("sqlalchemy.engine.Engine", "UPDATE t SET note='x', b=1") == "[statement hidden: unsupported database]"
    )


def test_an_engine_log_record_with_capture_on_keeps_its_literal() -> None:
    # derived: Task 32, owner's item 7: capture on lifts no hide with no family, so the literal is a known dialect's
    assert logged("sqlalchemy.engine.Engine", "SELECT 'x'", CAPTURING, family=Dialect.SQLITE) == "SELECT 'x'"


def test_an_engine_log_record_with_capture_on_and_no_family_is_hidden() -> None:
    assert logged("sqlalchemy.engine.Engine", "SELECT 'x'", CAPTURING) == "[statement hidden: unsupported database]"


class _Broken(Masker):
    def mask_spans(self, text: str, strict: bool = True, view: Any = None) -> list[tuple[int, int]] | None:
        raise RuntimeError(text)


def test_a_render_exception_fails_closed() -> None:
    assert (
        mask_error(_Broken(Exposure.MASKED, True), f"(sqlite3.Error) x {SECRET}\n[SQL: SELECT 1]", Dialect.UNSUPPORTED)
        == MASK
    )


@pytest.mark.parametrize(
    "line",
    [
        "(pymysql.err.IntegrityError) (1062, \"Duplicate entry '{}' for key 'u.name'\")",
        "(1062, \"Duplicate entry '{}' for key 'u.name'\")",
    ],
    ids=["class", "bare"],
)
def test_pymysql_tuple_keeps_its_message(line: str) -> None:
    assert shown(line.format(SECRET)).endswith('(1062, "Duplicate entry ?")')


def _last_error(message: str, masker: Masker = MASKER) -> str | None:
    conn = FakeMySqlConnection().with_rows("REPLICATION", {"channel_name": "", "last_error_message": message})
    found = DataSourceData("primary")
    collect_replication(conn, RowLimits(), found, masker)
    return found.replication_channels[0]["lastErrorMessage"]


def test_last_error_message_hides_the_value() -> None:
    masked = _last_error(f"Duplicate entry '{SECRET}' for key 'u.name'")
    assert masked == "Duplicate entry ?"


CHAINED = (
    'Traceback (most recent call last):\n  File "a.py", line 1, in f\n'
    f"    cursor.execute(\"SELECT '{SECRET}'\")\n"
    'psycopg2.errors.UniqueViolation: duplicate key "u"\n'
    f"DETAIL:  Key (a)=({SECRET}) exists\n\n"
    "The above exception was the direct cause of the following exception:\n\n"
    'Traceback (most recent call last):\n  File "b.py", line 2, in g\n'
    f"    conn.execute(text('SELECT {SECRET}'))\n"
)


def test_a_chained_traceback_hides_quoted_text() -> None:
    masked = shown(
        f'{CHAINED}sqlalchemy.exc.IntegrityError: (psycopg2.errors.UniqueViolation) key "u"\n[SQL: SELECT 1]'
    )
    assert SECRET not in masked
    assert '  File "b.py", line 2, in g' in masked


def test_a_chained_trailer_hides_quoted_text() -> None:
    text = (
        f"{DRIVER}\n[SQL: SELECT 1]\n[SQL parameters hidden due to hide_parameters=True]\n{LINK_LINE}\n\n"
        "During handling of the above exception, another exception occurred:\n\n"
        f"Traceback (most recent call last):\n  File \"c.py\", line 3, in h\n    raise E('{SECRET}')\nE: '{SECRET}'"
    )
    masked = shown(text)
    assert SECRET not in masked
    assert '  File "c.py", line 3, in h' in masked


def test_a_raw_driver_traceback_takes_the_regions() -> None:
    text = (
        'Traceback (most recent call last):\n  File "a.py", line 1, in f\n'
        f"    cursor.execute('SELECT {SECRET}')\n"
        'psycopg2.errors.UniqueViolation: duplicate key "u"\n'
        f"DETAIL:  Key (a)=({SECRET}) exists\n"
    )
    assert shown(text) == (
        'Traceback (most recent call last):\n  File "a.py", line 1, in f\n    cursor.execute(?)\n'
        "psycopg2.errors.UniqueViolation: duplicate key ?"
    )


# --- the scenario pass ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        f"IntegrityError: (sqlite3.IntegrityError) failed for '{SECRET}'",
        f"Could not read a mapper (RuntimeError: (sqlite3.IntegrityError) failed for '{SECRET}')",
        f'duplicate key "u"\nDETAIL:  Key (a)=({SECRET}) exists',
    ],
    ids=["prefixed", "wrapped", "bare_cause"],
)
def test_an_unanchored_driver_message_takes_the_driver_region(text: str) -> None:
    assert SECRET not in shown(text)


def test_a_mid_line_block_is_still_hidden() -> None:
    masked = shown(json.dumps({"detail": f"{DRIVER}\n[SQL: SELECT {SECRET} FROM t]"}))
    assert SECRET not in masked
    assert "[SQL: " in masked


def test_a_truncated_engine_log_statement_hides_its_tail() -> None:
    """A cut that takes one quote flips every quote after it: past the marker the scan reads values as code."""
    record = f"SELECT 'a' ... 1200 characters truncated ... {SECRET}', 'b'"
    masked = logged("sqlalchemy.engine.Engine", record)
    assert masked is not None
    assert SECRET not in masked


def test_driver_line_with_odd_quotes_hides_the_tail() -> None:
    assert shown(f"(sqlite3.Error) This Session's {SECRET} is rolled back") == "(sqlite3.Error) This Session?"


def test_a_mysql_tight_double_dash_keeps_the_value_hidden() -> None:
    # derived: Task 29 re-reads the generic row on MySQL, where a tight ``--`` is two minus signs
    masked = shown(f"{DRIVER}\n[SQL: SELECT 5--'a\n{SECRET}']\n[parameters: ('b',)]\n{LINK_LINE}", Dialect.MYSQL_FAMILY)
    assert SECRET not in masked


@pytest.mark.parametrize("label", ["LINE 1", "HINT", "CONTEXT", "QUERY", "WHERE"])
def test_every_driver_line_after_the_first_is_hidden(label: str) -> None:
    masked = shown(f"(psycopg.errors.Error) boom\n{label}:  value {SECRET}\n[SQL: SELECT 1]")
    assert masked == "(psycopg.errors.Error) boom\n[SQL: SELECT ?]"


# --- the plan's Review Focus ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        f"{DRIVER}\n[SQL: SELECT 'hidden-{SECRET}",
        f"{DRIVER}\n[SQL: SELECT 'hidden-{SECRET}]",
        f"{DRIVER}\n[SQL: SELECT 1]\n[parameters: ('{SECRET}', 'b",
        f"{DRIVER}\n[SQL: SELECT 1]\n[parameters: ('{SECRET}',\n  'second {SECRET}",
    ],
    ids=["literal", "literal-ending-in-a-bracket", "parameters", "parameters-across-a-line"],
)
def test_a_cut_error_shows_nothing_past_the_cut(text: str) -> None:
    masked = shown(text)
    assert SECRET not in masked
    assert masked.startswith(DRIVER)


def test_a_cut_literal_does_not_close_its_block() -> None:
    assert shown(f"{DRIVER}\n[SQL: SELECT 'hidden-{SECRET}]") == f"{DRIVER}\n[SQL: SELECT ?"


@pytest.mark.needs_sqlalchemy
def test_a_live_error_with_hidden_parameters_keeps_the_line() -> None:
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine("sqlite://", hide_parameters=True)
    with engine.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE u (id INTEGER, name TEXT UNIQUE)")
        conn.exec_driver_sql("INSERT INTO u VALUES (?, ?)", (1, SECRET))
        with pytest.raises(sa.exc.IntegrityError) as caught:
            conn.exec_driver_sql("INSERT INTO u VALUES (?, ?)", (2, SECRET))
    masked = shown(str(caught.value))
    assert "\n[SQL: INSERT INTO u VALUES (?, ?)]\n" in masked
    assert "]\n[SQL parameters hidden due to hide_parameters=True]\n" in masked


def test_crlf_text_finds_its_regions() -> None:
    block = f"[SQL: SELECT 'a'\r\nFROM t]\r\n[parameters: ('{SECRET}',)]"
    text = f"{DRIVER}\r\nDETAIL:  x {SECRET}\r\n{block}\r\n{LINK_LINE}\r\n"
    assert shown(text) == f"{DRIVER}\n[SQL: SELECT ? FROM t]\n[parameters: {MASK}]\n{LINK_LINE}"


def test_a_crlf_traceback_finds_its_regions() -> None:
    text = (
        'Traceback (most recent call last):\r\n  File "a.py", line 1, in f\r\n'
        f"    run('{SECRET}')\r\nsqlalchemy.exc.Error: {DRIVER}\r\n[SQL: SELECT 1]\r\n{LINK_LINE}\r\n"
    )
    assert shown(text) == (
        'Traceback (most recent call last):\n  File "a.py", line 1, in f\n    run(?)\n'
        f"sqlalchemy.exc.Error: {DRIVER}\n[SQL: SELECT ?]\n{LINK_LINE}"
    )


@pytest.mark.parametrize(
    ("driver", "statement", "expected"),
    [
        ("(pyodbc.IntegrityError) ('23000', 'x')", "SELECT [name], [a b] FROM [dbo].[u] WHERE a = 'x'", None),
        ("(aiosqlite.Error) x", "SELECT [name] FROM [u] WHERE a = 'x'", "SELECT [name] FROM [u] WHERE a = ?"),
        ("(sqlalchemy.dialects.postgresql.asyncpg.Error) x", "SELECT a[1] FROM t", "SELECT a[?] FROM t"),
    ],
    ids=["sql-server", "aiosqlite", "asyncpg"],
)
def test_bracket_identifiers_stay_in_the_block(driver: str, statement: str, expected: str | None) -> None:
    masked = shown(error(statement, driver=driver))
    assert f"\n[parameters: {MASK}]\n" in masked
    assert (expected or "FROM [dbo].[u] WHERE a = ?") in masked


def test_a_driver_message_with_no_block_keeps_its_first_line() -> None:
    text = f"(sqlalchemy.dialects.postgresql.asyncpg.Error) relation 'x' missing\nDETAIL: {SECRET}"
    assert shown(text) == "(sqlalchemy.dialects.postgresql.asyncpg.Error) relation ? missing"


def test_a_literal_holding_the_closer_is_not_the_closer() -> None:
    masked = shown(error(f"SELECT '{SECRET}]\n(Background on x' FROM t"))
    assert masked == f"{DRIVER}\n[SQL: SELECT ? FROM t]\n[parameters: {MASK}]\n{LINK_LINE}"


# derived: the A2 differential, seed 11, shortest hits on trace and err_off: a tuple whose quote comes back inside it is
# no repr, and a value tight before a literal is no name
def test_a_tuple_holding_its_own_quote_is_no_message() -> None:
    masked = shown(f'(pymysql.err.OperationalError) (1045, "v":"{SECRET}")\n[SQL: SELECT 1]')
    assert masked.startswith("(pymysql.err.OperationalError) (1045, ?)\n")


def test_a_value_tight_before_a_literal_stays_hidden() -> None:
    statement = f"""UPDATE t SET AccountKey=abc.'set-cookie':Bearer b?Server=x;Password={SECRET}="https": "v\""""
    masked = shown(f"{DRIVER}\n[SQL: {statement}]")
    assert SECRET not in masked


# derived: Task 7's closer read the parameters too: a trigger there cut the statement, and an ambiguous statement's
# render read the parameters, where the masker's own pass hit, so ``?`` became ``******``
def test_a_trigger_in_the_parameters_does_not_cut_the_statement() -> None:
    masked = shown(error("SELECT 1, 'x', a FROM t", "(\"it's # \\'\", 'y')"))
    assert "[SQL: SELECT ?, ?, a FROM t]\n[parameters: ******]\n" in masked


def test_an_ambiguous_statement_shows_its_cut_not_a_mask() -> None:
    masked = shown(error("/* /* nested */ it's */ SELECT 'x'"), Dialect.MYSQL_FAMILY)  # D7's nested cut
    # owner ruling 2026-11-08 (E): the run-on ends at the parameters line, shown as the constant
    assert masked == f"{DRIVER}\n[SQL: it ?]\n[parameters: {MASK}]\n{LINK_LINE}"


def test_a_parameters_repr_holding_the_closer_stays_hidden() -> None:
    parameters = f"('{SECRET}]\n(Background on x', '{SECRET}]\n{LINK_LINE}\n{SECRET}',)"
    masked = shown(error("SELECT 1", parameters))
    assert masked == f"{DRIVER}\n[SQL: SELECT ?]\n[parameters: {MASK}]\n{LINK_LINE}"


# Task 7's two open leaks (report, "Known limits"): red until Task 27 closes them
def test_a_bare_cause_with_an_object_shows_no_value() -> None:
    """A PostgreSQL cause with no ``DETAIL:`` or ``LINE n:`` has nothing to route on: the object is read, not its text.

    Owner ruling 2026-11-07 (alternative B): the real psycopg class, raised as the ``__cause__`` of a wrapper. Its
    driver message is never shown. Owner ruling 2026-11-07, structured driver codes: its SQLSTATE is.
    """
    cause = psycopg.errors.InvalidTextRepresentation(f'invalid input syntax for type integer: "{SECRET}"')
    store = ExceptionStore(10, 5, 20, MASKER, application=lambda: None)
    try:
        try:
            raise cause
        except psycopg.errors.InvalidTextRepresentation as inner:
            raise RuntimeError("wrapper") from inner
    except RuntimeError as outer:
        store.record(outer, "t", None, None)
    recorded_cause = next(iter(store._groups.values())).causes[0]  # pyright: ignore[reportPrivateUsage]
    assert recorded_cause["message"] == "(psycopg.errors.InvalidTextRepresentation) 22P02"
    assert recorded_cause["exceptionClassName"] == "psycopg.errors.InvalidTextRepresentation"
    assert len(recorded_cause["frames"]) >= 1
    assert isinstance(recorded_cause["commonFrames"], int)
    assert error_text(MASKER, cause, Dialect.POSTGRESQL) == "(psycopg.errors.InvalidTextRepresentation) 22P02"


def test_a_planted_block_line_shows_no_value() -> None:
    """A newline planted in a ``DETAIL`` value starts a block that is not the real one."""
    masked = shown(f"{DRIVER}\nDETAIL:  Key (a)=(x\n[SQL: {SECRET}) exists\n[SQL: SELECT 1]")
    assert SECRET not in masked
    assert masked == f"{DRIVER}\n[SQL: {MASK}]"


def test_unclosed_block_before_real_block_keeps_driver_and_hides_block() -> None:
    masked = shown(f"{DRIVER}\nDETAIL:  Key (a)=(x\n[SQL: {SECRET}) exists\n[SQL: SELECT 1]\n{LINK_LINE}")
    assert masked == f"{DRIVER}\n[SQL: {MASK}]\n{LINK_LINE}"
    assert SECRET not in masked


# Task 8 review of 11-04/T7 (r8b): each finding as a row, red until the owning task closes it. Real SQLite errors,
# real exception objects and real pymysql classes.
# the message is a literal: older SQLite accepts only a string literal in RAISE, not an expression
TRIGGER = f"CREATE TRIGGER tg BEFORE INSERT ON u BEGIN SELECT RAISE(ABORT, 'bad value {SECRET}'); END"
CHAIN = "The above exception was the direct cause of the following exception:"
CHAINS = (CHAIN, "During handling of the above exception, another exception occurred:")


def raised(sql: str, parameters: tuple[str, ...] | None = None, setup: tuple[str, ...] = ()) -> Exception:
    """The SQLAlchemy error SQLite really raises for ``sql``; its ``__cause__`` is the real driver error."""
    with sa.create_engine("sqlite://").connect() as connection:
        for statement in setup:
            connection.exec_driver_sql(statement)
        try:
            connection.exec_driver_sql(sql, parameters) if parameters is not None else connection.exec_driver_sql(sql)
        except Exception as exc:  # noqa: BLE001
            return exc
    raise AssertionError(f"no error: {sql}")


class _Boom(TypeDecorator[str]):
    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        raise ValueError("cannot bind")


# T27, review H1: a PyMySQL ``(code, 'message')`` tuple is the message, and the base hid its values
def test_a_pymysql_tuple_message_shows_no_value() -> None:
    cause = pymysql.err.OperationalError(1644, f"bad password {SECRET}")
    exc = DBAPIError.instance("SELECT 1", (), cause, pymysql.err.Error)
    assert SECRET not in shown(str(exc))


# T27, review H2: a driver line with no quote has nothing to route on, and the attach path and a RAISE message are one
@TEXT_ONLY_LIMIT
@pytest.mark.parametrize("case", ["attach", "raise"])
def test_a_driver_line_with_no_quote_shows_no_value(case: str) -> None:
    if case == "attach":
        exc = raised(f"ATTACH DATABASE '/nonexistent/dir/{SECRET}' AS x")
    else:
        exc = raised("INSERT INTO u VALUES (?)", (SECRET,), ("CREATE TABLE u(a TEXT)", TRIGGER))
    assert SECRET not in shown(str(exc))


def _store_message(exc: BaseException) -> str | None:
    store = ExceptionStore(10, 5, 20, MASKER, application=lambda: None)
    store.record(exc, "t", None, None)
    return next(iter(store._groups.values())).message  # pyright: ignore[reportPrivateUsage]


# T27 v5 review D1: H2's rows on the object path. A classified driver exception shows its class, a numeric code and
# the masked statement; never the driver's own text (owner ruling 2026-11-07, 2). Bound values add the constant masked
# parameters line, as SQLAlchemy prints it (owner ruling 2026-11-07, params region kept)
OBJECT_ROWS = {  # owner ruling 2026-11-07: structured driver codes (sqlite3's sqlite_errorname)
    "attach": "(sqlite3.OperationalError) SQLITE_CANTOPEN\n[SQL: ATTACH DATABASE ? AS x]",
    "raise": (
        "(sqlite3.IntegrityError) SQLITE_CONSTRAINT_TRIGGER\n[SQL: INSERT INTO u VALUES (?)]\n[parameters: ******]"
    ),
}


@pytest.mark.parametrize("surface", ["error_text", "exception_store"])
@pytest.mark.parametrize("case", ["attach", "raise"])
def test_a_driver_object_with_no_quote_shows_no_value(case: str, surface: str) -> None:
    if case == "attach":
        exc = raised(f"ATTACH DATABASE '/nonexistent/dir/{SECRET}' AS x")
    else:
        exc = raised("INSERT INTO u VALUES (?)", (SECRET,), ("CREATE TABLE u(a TEXT)", TRIGGER))
    masked = error_text(MASKER, exc, Dialect.SQLITE) if surface == "error_text" else _store_message(exc)
    assert masked == OBJECT_ROWS[case]


# derived: owner ruling 2026-11-07, structured driver codes. A driver's structured code is shown after its class: the
# int ``args[0]``, else psycopg's ``sqlstate`` or psycopg2's ``pgcode``, else sqlite3's ``sqlite_errorname``
PG_CODES = {
    "invalid_text": (psycopg.errors.InvalidTextRepresentation, "22P02"),
    "undefined_table": (psycopg.errors.UndefinedTable, "42P01"),
}


@pytest.mark.parametrize("case", sorted(PG_CODES))
def test_a_psycopg_error_shows_its_sqlstate(case: str) -> None:
    kind, code = PG_CODES[case]
    exc = DBAPIError.instance("SELECT a FROM t", None, kind(f"bad value {SECRET}"), psycopg.Error)
    assert (
        error_text(MASKER, exc, Dialect.POSTGRESQL)
        == f"({kind.__module__}.{kind.__qualname__}) {code}\n[SQL: SELECT a FROM t]"
    )


@pytest.mark.parametrize("storage", ["instance", "member"])  # a member descriptor, as psycopg2's C type keeps it
def test_a_psycopg2_error_shows_its_pgcode(storage: str) -> None:
    slots = {"__slots__": ("pgcode",)} if storage == "member" else {}
    kind = type("UndefinedTable", (Exception,), {"__module__": "psycopg2.errors", **slots})
    cause = kind(f"relation {SECRET} does not exist")
    cause.pgcode = "42P01"  # pyright: ignore[reportAttributeAccessIssue]
    exc = DBAPIError.instance("SELECT a FROM t", None, cause, Exception)
    assert (
        error_text(MASKER, exc, Dialect.POSTGRESQL) == "(psycopg2.errors.UndefinedTable) 42P01\n[SQL: SELECT a FROM t]"
    )


def test_a_sqlite_error_shows_its_error_name_and_no_message() -> None:
    masked = error_text(MASKER, raised("select * from missing_table"), Dialect.SQLITE) or ""
    assert masked.startswith("(sqlite3.OperationalError) SQLITE_ERROR\n")
    assert "no such table" not in masked


class _OddStr(str):
    __slots__ = ()


def _code_spy(ran: list[str]) -> property:
    def read(_self: object) -> str:
        ran.append("code")
        return "42P01"

    return property(read)


# derived: owner ruling 2026-11-07, structured driver codes: a code that is not an exact str of the code's shape is
# not shown, and a property standing for one never runs
@pytest.mark.parametrize("value", ["subclass", "wrong_shape", "property"])
@pytest.mark.parametrize("field", ["sqlstate", "sqlite_errorname"])
def test_a_code_of_the_wrong_kind_is_not_shown(field: str, value: str) -> None:
    ran: list[str] = []
    module = "sqlite3" if field == "sqlite_errorname" else "psycopg.errors"
    good = "SQLITE_ERROR" if field == "sqlite_errorname" else "42P01"
    planted = {"subclass": _OddStr(good), "wrong_shape": f"{good} {SECRET}", "property": _code_spy(ran)}[value]
    kind = type("OperationalError", (Exception,), {"__module__": module, field: planted})
    exc = DBAPIError.instance("SELECT a FROM t", None, kind("failed"), Exception)
    masked = error_text(MASKER, exc, Dialect.POSTGRESQL)
    assert masked == f"({module}.OperationalError)\n[SQL: SELECT a FROM t]"
    assert ran == []


# derived: Task 27 Opus review r2 #4: a str subclass is no code wherever the driver keeps it
@pytest.mark.parametrize("storage", ["instance", "member"])
def test_a_str_subclass_code_on_the_driver_is_not_shown(storage: str) -> None:
    slots = {"__slots__": ("pgcode",)} if storage == "member" else {}
    kind = type("UndefinedTable", (Exception,), {"__module__": "psycopg2.errors", **slots})
    cause = kind("failed")
    cause.pgcode = _OddStr("42P01")  # pyright: ignore[reportAttributeAccessIssue]
    exc = DBAPIError.instance("SELECT a FROM t", None, cause, Exception)
    assert error_text(MASKER, exc, Dialect.POSTGRESQL) == "(psycopg2.errors.UndefinedTable)\n[SQL: SELECT a FROM t]"


# derived: Task 27 Opus review r2 #4: a bool ``args[0]`` is no numeric code
def test_a_bool_first_argument_is_not_a_code() -> None:
    exc = DBAPIError.instance("SELECT a FROM t", None, pymysql.err.OperationalError(True, "failed"), pymysql.err.Error)
    assert error_text(MASKER, exc, Dialect.MYSQL_FAMILY) == "(pymysql.err.OperationalError)\n[SQL: SELECT a FROM t]"


# T27 v5 review D3: no data descriptor a subclass defines may run while its exception is read
@pytest.mark.parametrize("surface", ["error_text", "exception_store"])
@pytest.mark.parametrize("module", ["app.errors", "sqlite3"], ids=["plain", "driver"])
@pytest.mark.parametrize("field", ["args", "__dict__"])
def test_an_exception_property_never_runs(field: str, module: str, surface: str) -> None:
    ran: list[str] = []

    def spy(_self: BaseException) -> object:
        ran.append(field)
        return (SECRET,) if field == "args" else {"statement": SECRET}

    shadow = type("Shadow", (Exception,), {"__module__": module, field: property(spy)})("plain")
    if surface == "error_text":
        error_text(MASKER, shadow, Dialect.UNSUPPORTED)
    else:
        try:
            raise RuntimeError("wrapper") from shadow
        except RuntimeError as outer:
            _store_message(outer)
    assert ran == []


# T27, review H3: ``causes[]`` is the real ``__cause__`` of a SQLAlchemy error, and shows what it holds as it came
@pytest.mark.parametrize("case", ["near_literal", "attach"])
def test_a_cause_in_the_exception_store_shows_no_value(case: str) -> None:
    sql = f"SELECT 'a' 'b' '{SECRET}' FROM" if case == "near_literal" else f"ATTACH DATABASE '/no/dir/{SECRET}' AS x"
    exc = raised(sql)
    store = ExceptionStore(10, 5, 20, MASKER, application=lambda: None)
    store.record(exc, "t", None, None)
    group = next(iter(store._groups.values()))  # pyright: ignore[reportPrivateUsage]
    assert exc.__cause__ is not None
    assert SECRET not in str(group.causes[0]["message"])


# T27, review M4: a driver line that holds the chain line a value planted starts a link that is not the real one
def test_a_planted_chain_line_shows_no_value() -> None:
    exc = raised(f"SELECT 'a' 'b' 'x\n{CHAIN}\n{SECRET}' FROM")
    assert SECRET not in shown(str(exc))


# T27, review M5: with no docs link of its own (a ``StatementError``), a link line a value planted is taken for the end
def test_a_planted_link_line_shows_no_value() -> None:
    statement = sa.text(f"SELECT 'x\n{LINK_LINE}\n{SECRET}' AS q, :a").bindparams(sa.bindparam("a", "v", type_=_Boom()))
    with sa.create_engine("sqlite://").connect() as connection, pytest.raises(StatementError) as caught:
        connection.execute(statement)
    assert SECRET not in shown(str(caught.value))


# T27, review M6: a ``[SQL: `` a value planted, never closed: the DETAIL-less shape and the one that starts with a verb
@pytest.mark.parametrize("planted", ["[SQL: {}", "[SQL: select {}"], ids=["detail_less", "verb"])
def test_an_unterminated_block_line_shows_no_value(planted: str) -> None:
    exc = raised(f"SELECT 'x\n{planted.format(SECRET)}")
    assert SECRET not in shown(str(exc))


# T28, review M7: a release name with a colon or ``:=`` before the value
@pytest.mark.parametrize("name", ["Password:", "pwd:="])
def test_a_colon_name_before_a_value_shows_no_value(name: str) -> None:
    exc = raised(f'UPDATE t SET x = {name}{SECRET}="https"')
    assert SECRET not in shown(str(exc))


# T21, review L8: a comment holding ``]`` and the words of the docs link is no closer
def test_a_comment_is_not_a_closer() -> None:
    exc = raised("SELECT pin FROM t /* ] (Background on */ WHERE pin = 1234567")
    assert "1234567" not in shown(str(exc))


# derived: Task 27 review 4 (subclass __class__ descriptor is never invoked by read_chain or error_text)
def test_a_class_property_on_exception_never_runs() -> None:
    import sqlite3

    from sharpit.engine.sqltext.dialect import read_chain

    ran: list[str] = []

    class HostileClassError(sqlite3.OperationalError):
        __module__ = "sqlite3"

        @property
        def __class__(self) -> type:  # type: ignore[override]
            ran.append("__class__")
            return sqlite3.OperationalError

    exc = HostileClassError("near 'secret': syntax error")
    assert read_chain(exc).families == frozenset({Dialect.SQLITE})
    assert error_text(MASKER, exc, Dialect.SQLITE) is None
    assert ran == []


# derived: Task 27 review 10 (single exported is_database_exception predicate in sharpit.engine.sqltext)
def test_sqltext_exports_single_is_database_exception_predicate() -> None:
    import sqlite3

    from sharpit.engine import sqltext
    from sharpit.engine.capture import logtail
    from sharpit.engine.sqltext import errors

    predicate = getattr(sqltext, "is_database_exception", None)
    assert callable(predicate)
    assert predicate(sqlite3.OperationalError("near 'secret': syntax error")) is True
    assert predicate(RuntimeError("plain failure")) is False
    assert not hasattr(errors, "_is_database_exception")
    assert not hasattr(logtail, "_is_classified")


# Task 35 council H1: a docs-link line inside the statement (a comment, a dollar quote) is not the error's end. A link
# is accepted only after the block ends, so the statement after it is never read as trailer free text
ACCOUNT = "99887766"
PLANTED_LINK = {
    "comment": f"SELECT a FROM t /*\n{LINK_LINE}\n*/ WHERE acct = {ACCOUNT}",
    "dollar": f"SELECT $x$\n{LINK_LINE}\n$x$, {ACCOUNT} AS acct",
}
LINK_DRIVERS = {
    Dialect.POSTGRESQL: (psycopg.errors.SyntaxError, ("syntax error",)),
    Dialect.MYSQL_FAMILY: (pymysql.err.ProgrammingError, (1064, "syntax error")),
}
LINK_DIALECTS = [Dialect.POSTGRESQL, Dialect.MYSQL_FAMILY]


@pytest.mark.parametrize("bound", [None, {"p": 1}], ids=["no_parameters", "parameters"])
@pytest.mark.parametrize("dialect", LINK_DIALECTS, ids=["postgresql", "mysql_family"])
@pytest.mark.parametrize("case", sorted(PLANTED_LINK))
def test_a_link_line_in_a_classified_statement_is_not_the_end(case: str, dialect: Dialect, bound: object) -> None:
    kind, args = LINK_DRIVERS[dialect]
    exc = DBAPIError.instance(PLANTED_LINK[case], bound, kind(*args), Exception)
    masked = error_text(MASKER, exc, dialect)
    assert masked is not None
    assert ACCOUNT not in masked


@pytest.mark.parametrize("dialect", LINK_DIALECTS, ids=["postgresql", "mysql_family"])
@pytest.mark.parametrize("case", sorted(PLANTED_LINK))
def test_a_link_line_in_a_statement_with_no_link_of_its_own_is_not_the_end(case: str, dialect: Dialect) -> None:
    """The text as a log line cut before SQLAlchemy's own link: the planted line is the last one."""
    masked = shown(f"{DRIVER}\n[SQL: {PLANTED_LINK[case]}]\n[parameters: (1,)]", dialect)
    assert ACCOUNT not in masked


# Task 35 council H1, the object path (second reviewer, probe_link.py): a link line inside a literal, no parameters,
# on every family; and a line comment whose ``]`` is followed by a planted link line, on the object and the text path
LITERAL_LINK = f"SELECT 'a\n{LINK_LINE}\n{SECRET}'"
LINE_COMMENT_LINK = f"SELECT a FROM t -- x]\n{LINK_LINE}\n, {ACCOUNT} AS acct"
FAMILY_DRIVERS = {
    Dialect.POSTGRESQL: (psycopg.errors.UniqueViolation, ("dup",)),
    Dialect.MYSQL_FAMILY: (pymysql.err.IntegrityError, (1062, "dup")),
    Dialect.SQLITE: (sqlite3.IntegrityError, ("UNIQUE constraint failed",)),
}
FAMILY_IDS = ["postgresql", "mysql_family", "sqlite"]


@pytest.mark.parametrize("dialect", list(FAMILY_DRIVERS), ids=FAMILY_IDS)
def test_a_link_line_in_a_classified_literal_shows_no_value(dialect: Dialect) -> None:
    kind, args = FAMILY_DRIVERS[dialect]
    masked = error_text(MASKER, DBAPIError.instance(LITERAL_LINK, None, kind(*args), Exception), dialect)
    assert masked is not None
    assert SECRET not in masked


def test_a_link_line_in_a_literal_through_the_exception_store_shows_no_value() -> None:
    exc = raised(
        f"insert into u values ('a' || substr('x\n{LINK_LINE}\n{SECRET}', 1, 0))",
        setup=("create table u (name text unique)", "insert into u values ('a')"),
    )
    store = ExceptionStore(10, 5, 20, MASKER, application=lambda: Dialect.SQLITE)
    store.record(exc, "t", None, None)
    group = next(iter(store._groups.values()))  # pyright: ignore[reportPrivateUsage]
    assert "IntegrityError" in str(group.message)
    assert SECRET not in str(group.message)


@pytest.mark.parametrize("bound", [None, {"p": 1}], ids=["no_parameters", "parameters"])
@pytest.mark.parametrize("dialect", list(FAMILY_DRIVERS), ids=FAMILY_IDS)
def test_a_line_comment_closer_before_a_link_line_shows_no_value_classified(dialect: Dialect, bound: object) -> None:
    kind, args = FAMILY_DRIVERS[dialect]
    masked = error_text(MASKER, DBAPIError.instance(LINE_COMMENT_LINK, bound, kind(*args), Exception), dialect)
    assert masked is not None
    assert ACCOUNT not in masked


@pytest.mark.parametrize("cut", [False, True], ids=["own_link", "cut_before_own_link"])
@pytest.mark.parametrize("dialect", list(FAMILY_DRIVERS), ids=FAMILY_IDS)
def test_a_line_comment_closer_before_a_link_line_shows_no_value(dialect: Dialect, cut: bool) -> None:
    kind, args = FAMILY_DRIVERS[dialect]
    text = str(DBAPIError.instance(LINE_COMMENT_LINK, {"p": 1}, kind(*args), Exception))
    masked = shown(text[: text.rfind("(Background")] if cut else text, dialect)
    assert ACCOUNT not in masked


# the M4 and M5 rows of the text-only limit above, on the object path: the exception, not its string
def test_a_planted_chain_line_on_the_object_path_shows_no_value() -> None:
    masked = error_text(MASKER, raised(f"SELECT 'a' 'b' 'x\n{CHAIN}\n{SECRET}' FROM"), Dialect.SQLITE)
    assert masked is not None
    assert SECRET not in masked


def test_a_planted_link_line_on_the_object_path_shows_no_value() -> None:
    masked = error_text(MASKER, raised(f"SELECT 'x\n{LINK_LINE}\n{SECRET}' AS q FROM"), Dialect.SQLITE)
    assert masked is not None
    assert SECRET not in masked


# Task 35 council M2: a chain sentence on its own line inside a quoted driver value is the value's, not a chain: the
# walk stays where it was, so the rest of the value never shows as trailer text
@pytest.mark.parametrize("chain", sorted(CHAINS), ids=["direct_cause", "during_handling"])
@pytest.mark.parametrize("quote", ["'", '"'], ids=["single", "double"])
def test_a_chain_line_inside_a_quoted_driver_value_shows_no_value(quote: str, chain: str) -> None:
    text = f"(psycopg2.errors.X) bad {quote}a\n{chain}\n{SECRET}{quote}\n[SQL: SELECT 1]\n{LINK_LINE}"
    assert SECRET not in shown(text)


# Task 35 H1 guard: the common chained shape (``raise HTTPException`` in an ``except``) has text after its link and no
# parameters line. The link is SQLAlchemy's own: a chain sentence and a traceback follow it, as Python writes them
def test_a_chained_traceback_after_the_link_keeps_its_frames() -> None:
    text = (
        f"{DRIVER}\n[SQL: SELECT 1]\n{LINK_LINE}\n\n"
        "During handling of the above exception, another exception occurred:\n\n"
        f"Traceback (most recent call last):\n  File \"c.py\", line 3, in h\n    raise E('{SECRET}')\nE: '{SECRET}'"
    )
    masked = shown(text)
    assert SECRET not in masked
    assert '  File "c.py", line 3, in h' in masked
    assert "[SQL: SELECT ?]" in masked


# Task 35 council M4 (inherited from 523eb1e5 and v0.4.0): a ``[SQL: `` at a line start inside a quoted driver value is
# not the block. Text that cannot be read is not shown: with the driver line's quote open and two block lines after it,
# which is SQLAlchemy's cannot be read, so the block and what follows it to the link hide
VALUE_BREAKS = {"lf": "\n", "crlf": "\r\n", "ls": " ", "nel": "\x85"}


@pytest.mark.parametrize("quote", ["'", '"'], ids=["single", "double"])
@pytest.mark.parametrize("separator", VALUE_BREAKS.values(), ids=VALUE_BREAKS)
def test_a_block_line_inside_a_quoted_driver_value_shows_no_value(separator: str, quote: str) -> None:
    text = f"(psycopg2.errors.X) bad value: {quote}abc{separator}[SQL: {SECRET} x]{quote}\n[SQL: SELECT 1]\n{LINK_LINE}"
    assert SECRET not in shown(text)
