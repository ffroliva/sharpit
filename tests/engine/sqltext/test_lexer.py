"""The lexer reports what it read and decides nothing about secrets (study section 5; plan Task 11, predict C1, C4)."""

from __future__ import annotations

import pytest

from sharpit.engine import sqltext
from sharpit.engine.sqltext import Dialect, Kind, Range

GENERIC = Dialect.UNSUPPORTED


def _kinds(sql: str, dialect: Dialect = GENERIC) -> list[tuple[str, Kind]]:
    return [(sql[start:end], kind) for start, end, kind in sqltext.LEXER.scan(sql, dialect).runs]


def test_a_double_quoted_run_is_its_own_kind() -> None:
    scan = sqltext.LEXER.scan('SELECT "x" FROM t', GENERIC)

    assert scan.runs == (Range(7, 10, Kind.DOUBLE_QUOTED),)


def test_a_double_quoted_run_in_a_value_position_is_a_literal() -> None:
    assert _kinds('SELECT a = "x"') == [('"x"', Kind.LITERAL)]


def test_a_double_quoted_run_on_mysql_is_a_literal() -> None:
    assert _kinds('SELECT "x"', Dialect.MYSQL_FAMILY) == [('"x"', Kind.LITERAL)]


def test_a_double_quoted_run_that_is_no_identifier_is_a_literal() -> None:
    assert _kinds('SELECT "a b"') == [('"a b"', Kind.LITERAL)]


def test_each_double_quoted_run_has_a_candidate_in_order() -> None:
    scan = sqltext.LEXER.scan('SELECT "t"."id" FROM t', GENERIC)

    assert [found.at for found in scan.candidates] == [7, 11]


def test_a_candidate_remembers_whether_a_literal_there_would_sit_in_a_predicate() -> None:
    scan = sqltext.LEXER.scan('SELECT "x", a = "t".y', GENERIC)

    assert [found.predicate for found in scan.candidates] == [False, True]


def test_the_scan_holds_the_text_the_runs_replay() -> None:
    scan = sqltext.LEXER.scan("SELECT 'a', /* c */ 1 -- d\n", GENERIC)

    assert scan.text == "SELECT ?, ? "


def test_a_scan_that_reads_one_way_has_no_cut() -> None:
    scan = sqltext.LEXER.scan("select 1", GENERIC)

    assert scan.cut == -1


def test_a_scan_that_reads_one_way_has_the_runs_it_would_have_uncut() -> None:
    scan = sqltext.LEXER.scan("select 1", GENERIC)

    assert scan.uncut_runs == scan.runs


def test_a_statement_that_reads_two_ways_cuts_at_its_first_opener() -> None:
    scan = sqltext.LEXER.scan("select 1 # 'x'", GENERIC)

    assert scan.cut == 11


def test_a_cut_keeps_the_runs_the_scan_read_before_it() -> None:
    scan = sqltext.LEXER.scan("select 1 # 'x'", GENERIC)

    assert [kind for _, _, kind in scan.uncut_runs] == [Kind.LITERAL, Kind.LITERAL]


def test_a_cut_ends_the_runs_with_a_literal_to_the_end() -> None:
    scan = sqltext.LEXER.scan("select 1 # 'x'", GENERIC)

    assert scan.runs[-1] == Range(11, 14, Kind.LITERAL)


def test_the_scan_is_frozen() -> None:
    scan = sqltext.LEXER.scan("select 1", GENERIC)

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
    assert sqltext.LEXER.block_closer(text, GENERIC) == -1


def test_reads_two_ways_reads_the_dialect_it_is_given() -> None:
    sql = 'select 1 where a = "x\y"'  # MySQL escapes in ``"..."``, the generic read does not: two readings there

    assert not sqltext.LEXER.reads_two_ways(sql, MYSQL)
    assert sqltext.LEXER.reads_two_ways(sql, GENERIC)


def test_a_lone_cr_in_a_comment_cuts_only_generic_text() -> None:
    sql = "select 1 -- a\rb\n, 'x'"

    assert not sqltext.LEXER.reads_two_ways(sql, MYSQL)
    assert sqltext.LEXER.reads_two_ways(sql, GENERIC)


def test_an_opener_in_a_tight_comment_cuts_only_generic_text() -> None:
    assert not sqltext.LEXER.reads_two_ways("select 1 #a'b\n, 2", MYSQL)
    assert sqltext.LEXER.reads_two_ways("select 1 --a'b\n, 2", GENERIC)


def test_a_swapped_lexer_reaches_the_closer_the_two_way_check_and_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from sharpit.engine.capture import sqlscan  # noqa: PLC0415

    sqlscan.normalize("select 1", Dialect.UNSUPPORTED)  # warm: a cache that outlives the swap would answer from this

    class Swapped:
        def scan(self, sql: str, dialect: Dialect) -> sqltext.Scan:
            return sqltext.HandLexer().scan("delete from t", dialect)

        def block_closer(self, text: str, dialect: Dialect) -> int:
            return 99

        def reads_two_ways(self, sql: str, dialect: Dialect) -> bool:
            return True

    monkeypatch.setattr(sqltext, "LEXER", Swapped())

    assert sqlscan.block_closer("a]", Dialect.UNSUPPORTED) == 99
    assert sqlscan.reads_two_ways("a", Dialect.UNSUPPORTED)
    assert sqlscan.normalize("select 1", Dialect.UNSUPPORTED).sql == "delete from t"
