"""The lexer reports what it read and decides nothing about secrets (study section 5; plan Task 11, predict C1, C4)."""

from __future__ import annotations

import pytest

from sharpit.engine import sqltext
from sharpit.engine.sqltext import Dialect, Kind, Range

GENERIC = Dialect.UNSUPPORTED


def _kinds(sql: str, dialect: Dialect = GENERIC) -> list[tuple[str, Kind]]:
    return [(sql[found.start : found.end], found.kind) for found in sqltext.LEXER.scan(sql, dialect).runs]


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

    assert [found.kind for found in scan.uncut_runs] == [Kind.LITERAL, Kind.LITERAL]


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
    sqlscan.normalize.__wrapped__("select 1", True)  # type: ignore[attr-defined]  # pyright: ignore[reportFunctionMemberAccess]

    assert seen == [Dialect.MYSQL_FAMILY]
