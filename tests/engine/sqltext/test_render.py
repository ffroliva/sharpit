"""The renderer decides a double-quoted run: the lexer only names it (plan Task 11, predict C1)."""

from __future__ import annotations

from collections.abc import Callable

from sharpit.engine import sqltext
from sharpit.engine.sqltext import Dialect

MASK = "******"
SQL = 'SELECT "x" FROM t'


def _shown(sql: str, hidden: list[tuple[int, int]], double_quoted: Callable[[str], bool]) -> str:
    scan = sqltext.LEXER.scan(sql, Dialect.POSTGRESQL)
    return sqltext.shown(sql, scan, hidden, MASK, sqltext.secrets(scan, double_quoted), ())


def test_render_decides_a_double_quoted_run() -> None:
    assert _shown(SQL, [], lambda _body: True) == "SELECT ? FROM t"


def test_render_keeps_a_double_quoted_run_it_does_not_call_a_secret() -> None:
    assert _shown(SQL, [], lambda _body: False) == SQL


def test_render_asks_with_the_body_of_the_run() -> None:
    asked: list[str] = []

    def record(body: str) -> bool:
        asked.append(body)
        return False

    _shown('SELECT "abc" FROM t', [], record)

    assert asked == ["abc"]


def test_render_masks_a_hidden_double_quoted_name_it_keeps() -> None:
    assert _shown(SQL, [(7, 10)], lambda _body: False) == f'SELECT "{MASK}" FROM t'


def test_render_does_not_ask_about_a_run_the_lexer_made_a_literal() -> None:
    asked: list[str] = []

    def record(body: str) -> bool:
        asked.append(body)
        return False

    _shown('SELECT a = "x"', [], record)

    assert asked == []


def test_render_asks_about_each_run_once_for_the_shape_and_the_text() -> None:
    asked: list[str] = []

    def record(body: str) -> bool:
        asked.append(body)
        return True

    sql = 'SELECT "abc", "def" FROM t'
    scan = sqltext.LEXER.scan(sql, Dialect.POSTGRESQL)
    secret = sqltext.secrets(scan, record)
    sqltext.shape(scan, secret)
    sqltext.shown(sql, scan, [], MASK, secret, ())

    assert asked == ["abc", "def"]


def test_a_secret_run_in_a_predicate_is_a_predicate_literal() -> None:
    # ported: the candidate remembers whether a literal there sits in a predicate
    scan = sqltext.LEXER.scan('SELECT 1 WHERE a = "secret".x', Dialect.POSTGRESQL)

    _, _, predicates = sqltext.shape(scan, sqltext.secrets(scan, lambda _body: True))

    assert predicates == 1


def test_a_double_quoted_name_outside_a_predicate_is_no_predicate_literal() -> None:
    scan = sqltext.LEXER.scan('SELECT "secret".x FROM t', Dialect.POSTGRESQL)

    _, literals, predicates = sqltext.shape(scan, sqltext.secrets(scan, lambda _body: True))

    assert (literals, predicates) == (1, 0)
