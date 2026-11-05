"""The renderer decides a double-quoted run: the lexer only names it (plan Task 11, predict C1)."""

from __future__ import annotations

from sharpit.engine import sqltext
from sharpit.engine.sqltext import Dialect

MASK = "******"
SQL = 'SELECT "x" FROM t'


def _shown(sql: str, hidden: list[tuple[int, int]], double_quoted: object) -> str:
    scan = sqltext.LEXER.scan(sql, Dialect.UNSUPPORTED)
    return sqltext.shown(sql, scan, hidden, MASK, double_quoted)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


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
