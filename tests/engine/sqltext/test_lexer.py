"""The lexer reports what it read and decides nothing about secrets (study section 5; plan Task 11, predict C1, C4)."""

from __future__ import annotations

import pytest

from sharpit.engine import sqltext
from sharpit.engine.sqltext import Dialect, Kind, Range
from sharpit.engine.sqltext.lexer import _dollar_quote_end, _read, _two_way_bracket_end
from sharpit.engine.sqltext.rules import MYSQL_84
from sharpit.engine.sqltext.rules import MYSQL_84 as MYSQL_RULES
from sharpit.engine.sqltext.rules import POSTGRESQL as POSTGRESQL_RULES


def _kinds(sql: str, dialect: Dialect = Dialect.POSTGRESQL) -> list[tuple[str, Kind]]:
    return [(sql[start:end], kind) for start, end, kind in sqltext.LEXER.scan(sql, dialect).runs]


def test_a_double_quoted_run_is_its_own_kind() -> None:
    scan = sqltext.LEXER.scan('SELECT "x" FROM t', Dialect.POSTGRESQL)

    assert scan.runs == (Range(7, 10, Kind.DOUBLE_QUOTED),)


def test_a_double_quoted_run_in_a_value_position_is_a_literal() -> None:
    assert _kinds('SELECT a = "x"') == [('"x"', Kind.LITERAL)]


def test_a_double_quoted_run_on_mysql_is_a_literal() -> None:
    assert _kinds('SELECT "x"', Dialect.MYSQL_FAMILY) == [('"x"', Kind.LITERAL)]


def test_a_double_quoted_run_that_is_no_identifier_is_a_literal() -> None:
    assert _kinds('SELECT "a b"') == [('"a b"', Kind.LITERAL)]


def test_each_double_quoted_run_has_a_candidate_in_order() -> None:
    scan = sqltext.LEXER.scan('SELECT "t"."id" FROM t', Dialect.POSTGRESQL)

    assert [found.at for found in scan.candidates] == [7, 11]


def test_a_candidate_remembers_whether_a_literal_there_would_sit_in_a_predicate() -> None:
    scan = sqltext.LEXER.scan('SELECT "x", a = "t".y', Dialect.POSTGRESQL)

    assert [found.predicate for found in scan.candidates] == [False, True]


def test_the_scan_holds_the_text_the_runs_replay() -> None:
    scan = sqltext.LEXER.scan("SELECT 'a', /* c */ 1 -- d\n", Dialect.POSTGRESQL)

    assert scan.text == "SELECT ?, ? "


def test_array_subscript_is_not_a_bracket_identifier() -> None:
    assert _read("SELECT ARRAY [secret]", MYSQL_RULES).out.runs == [(13, 14, Kind.CODE)]


def test_a_digit_led_bracket_body_is_not_an_identifier() -> None:
    assert _read("SELECT [123]", MYSQL_RULES).out.runs == [(7, 8, Kind.CODE), (8, 11, Kind.LITERAL)]


def test_a_closed_quote_inside_brackets_does_not_open_a_two_way_read() -> None:
    sql = "SELECT [" + chr(39) + "x" + chr(39) + " tail]"
    assert _two_way_bracket_end(sql, sql.index("["), POSTGRESQL_RULES) == -1


def test_an_open_quote_at_bracket_close_opens_a_two_way_read() -> None:
    sql = "SELECT [" + chr(39) + "x]"
    assert _two_way_bracket_end(sql, sql.index("["), POSTGRESQL_RULES) == sql.index("]") + 1


def test_mssql_doubled_bracket_opener_cuts_the_raw_mysql_pass() -> None:
    sql = "SELECT [a]]`[it" + chr(39) + "s], " + chr(39) + "secret" + chr(39)
    assert _read(sql, MYSQL_84).cut == sql.index("[")


def test_a_scan_that_reads_one_way_has_no_cut() -> None:
    scan = sqltext.LEXER.scan("select 1", Dialect.POSTGRESQL)

    assert scan.cut == -1


def test_mysql_shows_nothing_past_a_hash_comment_after_a_hidden_render() -> None:
    sql = "SELECT 1 # password hunter2"

    assert (
        sqltext.shown(sql, sqltext.LEXER.scan(sql, Dialect.MYSQL_FAMILY), (), "***", frozenset(), []).strip()
        == "SELECT ?"
    )


def test_a_hash_in_a_literal_stays_in_the_literal() -> None:
    assert sqltext.LEXER.scan("SELECT 'a#b', c FROM t", Dialect.POSTGRESQL).text == "SELECT ?, c FROM t"


def test_a_scan_that_reads_one_way_has_the_runs_it_would_have_uncut() -> None:
    scan = sqltext.LEXER.scan("select 1", Dialect.POSTGRESQL)

    assert scan.uncut_runs == scan.runs


def test_a_statement_that_reads_two_ways_cuts_at_its_first_opener() -> None:
    scan = sqltext.LEXER.scan("select 1 /* /* */ 'x'", Dialect.MYSQL_FAMILY)

    assert scan.cut == 18


def test_a_cut_keeps_the_runs_the_scan_read_before_it() -> None:
    scan = sqltext.LEXER.scan("select 1 /* /* */ 'x'", Dialect.MYSQL_FAMILY)

    assert [kind for _, _, kind in scan.uncut_runs] == [Kind.LITERAL, Kind.COMMENT, Kind.LITERAL]


def test_a_cut_ends_the_runs_with_a_literal_to_the_end() -> None:
    scan = sqltext.LEXER.scan("select 1 /* /* */ 'x'", Dialect.MYSQL_FAMILY)

    assert scan.runs[-1] == Range(18, 21, Kind.LITERAL)


def test_the_scan_is_frozen() -> None:
    scan = sqltext.LEXER.scan("select 1", Dialect.POSTGRESQL)

    with pytest.raises(AttributeError):
        scan.cut = 3  # type: ignore[misc]  # pyright: ignore[reportAttributeAccessIssue]


def test_the_facade_reads_the_lexer_the_package_names(monkeypatch: pytest.MonkeyPatch) -> None:
    from sharpit.engine.capture import sqlscan  # noqa: PLC0415

    real, seen = sqltext.LEXER, []

    class Spy:
        def scan(self, sql: str, dialect: Dialect) -> sqltext.Scan:
            seen.append(dialect)
            return real.scan(sql, dialect)

    monkeypatch.setattr(sqltext, "LEXER", Spy())
    sqlscan.normalize("select 1", Dialect.MYSQL_FAMILY)

    assert seen == [Dialect.MYSQL_FAMILY]


MYSQL = Dialect.MYSQL_FAMILY


def test_block_closer_reads_the_dialect_it_is_given() -> None:
    text = 'x = "a\\"]" ]'  # a backslash escapes the quote on MySQL, so the first ``]`` is inside a string there

    assert sqltext.LEXER.block_closer(text, MYSQL) == 11
    assert sqltext.LEXER.block_closer(text, Dialect.POSTGRESQL) == -1


# derived: Task 29 re-reads this row on known dialects: SQLite reads ``\`` as a character and keeps no backslash cut,
# the MySQL family escapes with it and cuts where the text without it reads apart
def test_reads_two_ways_reads_the_dialect_it_is_given() -> None:
    sql = r"select 'a\'b', 'c'"

    assert not sqltext.LEXER.reads_two_ways(sql, Dialect.SQLITE)
    assert sqltext.LEXER.reads_two_ways(sql, MYSQL)


def test_mysql_dollar_closer_does_not_step_back_after_a_partial_match() -> None:
    sql = "$a$body$$a$tail$a$ after"
    assert _dollar_quote_end(sql, 0, MYSQL_84) == sql.rindex("$a$") + 3


def test_a_swapped_lexer_reaches_the_facade_and_error_renderer(monkeypatch: pytest.MonkeyPatch) -> None:

    class Swapped:
        def scan(self, sql: str, dialect: Dialect) -> sqltext.Scan:
            self.scans += 1
            return sqltext.HandLexer().scan("delete from t", dialect)

        def block_closer(self, text: str, dialect: Dialect) -> int:
            self.closers += 1
            return 99

        def reads_two_ways(self, sql: str, dialect: Dialect) -> bool:
            self.two_ways += 1
            return True

        def __init__(self) -> None:
            self.closers = 0
            self.scans = 0
            self.two_ways = 0

    swapped = Swapped()
    monkeypatch.setattr(sqltext, "LEXER", swapped)

    from sharpit.engine.masking import Exposure, Masker

    sqltext.error_text(
        Masker(Exposure.MASKED, True), "(psycopg.errors.Error) failed\n[SQL: select 1]", Dialect.POSTGRESQL
    )
    assert swapped.closers == 1
    assert swapped.two_ways >= 1
    assert swapped.scans >= 1
