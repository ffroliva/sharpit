"""# derived: a miss on the recorder renders a statement once: with nothing hidden the shape is its render.

``test_shown_with_nothing_hidden_equals_normalize`` covers ASCII text; non-ASCII input uses the full render.
"""

from __future__ import annotations

import pytest

from sharpit.engine.capture import statement
from sharpit.engine.capture.sqlscan import read_statement
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect

MASKED = Masker(Exposure.MASKED, True)


def test_a_statement_with_nothing_hidden_is_not_rendered_twice(monkeypatch: pytest.MonkeyPatch):
    sql = "select a from t where b is null"
    calls: list[str] = []
    real = statement.shown

    def counted(*args: object) -> str:
        calls.append("rendered")
        return real(*args)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(statement, "shown", counted)

    assert statement.statement_text(MASKED, sql, Dialect.SQLITE, read_statement(sql, Dialect.SQLITE)) == sql
    assert calls == []


def test_a_statement_with_a_hit_is_rendered_with_it():
    sql = "select password_token from t where a = 'x' and token=abc"
    shown = statement.statement_text(MASKED, sql, Dialect.POSTGRESQL, read_statement(sql, Dialect.POSTGRESQL))

    assert shown is not None
    assert "abc" not in shown


def test_a_statement_with_no_reading_is_rendered():
    assert statement.statement_text(MASKED, "select 1", Dialect.SQLITE) == "select ?"


def test_a_non_ascii_statement_uses_the_full_render():
    sql = "SELECT \ufeff`x`"
    reading = read_statement(sql, Dialect.SQLITE)

    assert statement.statement_text(MASKED, sql, Dialect.SQLITE, reading) == statement.shown(
        sql, [], Dialect.SQLITE, reading
    )
