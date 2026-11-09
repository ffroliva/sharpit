"""SQLite's rules: study section 5 and tokenize.c (plan Task 18, spec sections 9 and 10)."""

from __future__ import annotations

import sqlite3

import pytest

from sharpit.engine.capture.sqlscan import normalize, reads_two_ways
from sharpit.engine.capture.statement import statement_text
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import LEXER, Dialect
from sharpit.engine.sqltext.lexer import readings
from sharpit.engine.sqltext.rules import (
    Backslash,
    BacktickRun,
    Bracket,
    DoubleQuote,
    HashRule,
    Reading,
    VariableSuffix,
)

MASKER = Masker(Exposure.MASKED, True)


def test_sqlite_rules_match_tokenize_c() -> None:
    rules = readings(Dialect.SQLITE)[0]
    # tokenize.c:396-420: no backslash escape in '...'
    assert rules.backslash_in_single is Backslash.NONE
    # tokenize.c:499-503: [ to the first ]
    assert rules.bracket is Bracket.TO_FIRST_CLOSE
    # tokenize.c:396-420: backtick as a name
    assert rules.backtick_run is BacktickRun.NAME
    # tokenize.c:509-538: # a variable prefix
    assert rules.hash is HashRule.VARIABLE
    # tokenize.c:289-293: -- always
    assert rules.dash_needs_space is Reading.NO
    assert rules.cr_ends_dash is Reading.NO
    # tokenize.c:413-415: double quote is a name to the lexer, hidden by the renderer
    assert rules.double_quote is DoubleQuote.NAME
    assert rules.hide_double_quoted is True
    # tokenize.c:519-531: TCL paren variable suffix
    assert rules.variable_suffix is VariableSuffix.TCL_PAREN


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ('SELECT "x"', "SELECT ?"),
        ('"users"."id"', "?.?"),
        ('SELECT "users"."id" FROM "users"', "SELECT ?.? FROM ?"),
        ('SELECT "x", "y" FROM "t"', "SELECT ?, ? FROM ?"),
        ('WHERE "name" = "val"', "WHERE ? = ?"),
    ],
    ids=["select_x", "users_id", "select_users_id", "select_x_y", "where_name"],
)
def test_sqlite_hides_every_double_quoted_run(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.SQLITE).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT :a(x), 'SECRET'", "SELECT :a(x), ?"),
        ("SELECT $a(x), 'SECRET'", "SELECT $a(x), ?"),
        ("SELECT @a(x), 'SECRET'", "SELECT @a(x), ?"),
        ("SELECT #a(x), 'SECRET'", "SELECT #a(x), ?"),
        ("SELECT :ns::a(x), 'SECRET'", "SELECT :ns::a(x), ?"),
        ("SELECT $ns::var(x), 'SECRET'", "SELECT $ns::var(x), ?"),
        ("SELECT :a(foo x), 'SECRET'", "SELECT :a(foo x), ?"),
    ],
    ids=[
        "colon_suffix",
        "dollar_suffix",
        "at_suffix",
        "hash_suffix",
        "colon_namespace",
        "dollar_namespace",
        "nbsp_suffix",
    ],
)
def test_sqlite_variable_suffix_is_one_token(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.SQLITE).sql == expected


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT :a('), 'SECRET'",
        "SELECT $a(it's), 'SECRET'",
        "SELECT @a(\"), 'SECRET'",
        "SELECT #a('), 'SECRET'",
        "SELECT :a(' SECRET",
        "SELECT :a('it's, 'SECRET'",
        "SELECT $a(')x','SECRET'",
    ],
    ids=["colon", "dollar", "at_double", "hash", "open_at_space", "open_at_comma", "not_tight_against_a_quote"],
)
def test_a_quote_in_a_suffix_or_an_open_suffix_hides_from_the_opener(sql: str) -> None:
    assert normalize(sql, Dialect.SQLITE).sql == "SELECT ?"


def test_a_refused_statement_with_a_quote_in_its_suffix_keeps_its_value_hidden() -> None:
    sql = "SELECT ?1,$a(')','ZQMARK'"
    connection = sqlite3.connect(":memory:")
    with pytest.raises(sqlite3.Error):
        connection.execute(sql)
    connection.close()
    assert normalize(sql, Dialect.SQLITE).sql == "SELECT ??, ?"
    assert "ZQMARK" not in (statement_text(MASKER, sql, Dialect.SQLITE) or "")


def test_a_suffix_holding_a_value_reads_the_same_on_both_outputs() -> None:
    sql = "SELECT $a('ZQMARK')"
    assert normalize(sql, Dialect.SQLITE).sql == "SELECT ?"
    assert statement_text(MASKER, sql, Dialect.SQLITE) == "SELECT ?"


@pytest.mark.parametrize(
    "between",
    ["", "﻿", "﻿﻿", " ", "\xa0", "\U0001f600", "_", "é", "1"],
    ids=["none", "bom", "doubled_bom", "em_space", "nbsp", "emoji", "underscore", "e_acute", "digit"],
)
def test_a_dollar_after_a_name_character_hides_from_there(between: str) -> None:
    name = f"x{between}$a"
    sql = f"WITH {name}(')x,') AS (SELECT 'ZQKK') SELECT * FROM {name}"
    returned = sqlite3.connect(":memory:").execute(sql).fetchall()
    assert returned == [("ZQKK",)]
    assert normalize(sql, Dialect.SQLITE).sql == f"WITH x{between.replace(chr(0xFEFF) * 2, chr(0xFEFF))} ?"
    assert "ZQKK" not in (statement_text(MASKER, sql, Dialect.SQLITE) or "")


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT x$a, 'SECRET'", "SELECT x ?"),
        ("SELECT x:a, 'SECRET'", "SELECT x ?"),
        ("SELECT x@a, 'SECRET'", "SELECT x ?"),
        ("SELECT x#a, 'SECRET'", "SELECT x ?"),
        ("SELECT _:a, 'SECRET'", "SELECT _ ?"),
        ("SELECT é@a, 'SECRET'", "SELECT é ?"),
        ("SELECT ?1$a(x), 'SECRET'", "SELECT ?? ?"),
        ("SELECT 1$a, 'SECRET'", "SELECT ? ?"),
        ("SELECT ﻿$a(foo), 'SECRET'", "SELECT ?"),
        ("﻿$a(foo), 'SECRET'", "?"),
    ],
    ids=["dollar", "colon", "at", "hash", "underscore", "e_acute", "numeric_variable", "number", "bom", "leading_bom"],
)
def test_every_opener_cuts_when_its_source_character_is_not_a_boundary(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.SQLITE).sql == expected


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT :a, @b, $c",
        "SELECT * FROM t WHERE x=:a AND y=@b OR z=$c",
        "INSERT INTO t VALUES(:a,$b,@c)",
        "SELECT * FROM t LIMIT :n OFFSET :m",
        "SELECT (:a)+(@b)-($c)",
        "SELECT #a",
        ":a",
        "$a(x)",
        "SELECT a$",
        "SELECT a$ FROM t",
        "SELECT a: FROM t",
    ],
    ids=[
        "list",
        "where",
        "values",
        "limit",
        "parens",
        "hash",
        "start",
        "start_suffix",
        "name_end",
        "name_mid",
        "colon",
    ],
)
def test_ordinary_sqlite_variables_stay_readable(sql: str) -> None:
    scan = LEXER.scan(sql, Dialect.SQLITE)
    assert scan.cut == -1
    assert scan.text == sql


def test_a_block_closer_past_a_variable_cut_is_a_guess() -> None:
    assert reads_two_ways("SELECT x$a, 'b'", Dialect.SQLITE)


@pytest.mark.parametrize(
    ("sql", "marker", "expected"),
    [
        ("WITH x$a(')') AS (SELECT 'ZQMARKA') SELECT * FROM x$a", "ZQMARKA", "WITH x ?"),
        ("SELECT 1 AS [:a(],'ZQMARKB'", "ZQMARKB", "SELECT ? AS [:a(],?"),
        ('SELECT 1 AS [@b(],"ZQMARKD"', "ZQMARKD", "SELECT ? AS [@b(],?"),
    ],
    ids=["dollar_in_name", "colon_in_bracket", "at_in_bracket"],
)
def test_sqlite_never_shows_a_returned_tcl_name_value(sql: str, marker: str, expected: str) -> None:
    returned = sqlite3.connect(":memory:").execute(sql).fetchall()
    assert marker in repr(returned)
    shown = normalize(sql, Dialect.SQLITE).sql
    assert marker not in shown
    assert shown == expected


def test_sqlite_backslash_does_not_join_adjacent_literals() -> None:
    sql = "SELECT 'a\\', 'ZQBACKSLASH'"
    assert normalize(sql, Dialect.SQLITE).sql == "SELECT ?, ?"


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT $( 'ZQNO_NAME' ), 'ZQTAIL'", "SELECT $( ? ), ?"),
        ("SELECT $a(foo\tx), 'ZQSPACE'", "SELECT ?"),
        ("SELECT $\u0080(foo'bar)", "SELECT ?"),
        ("SELECT :ns::(foo'bar)", "SELECT ?"),
        ("SELECT $::#a('ZQZERO'), 'ZQTAIL'", "SELECT $:: ?"),
        ("SELECT a$ , 'ZQTAIL'", "SELECT a$ , ?"),
    ],
    ids=["suffix_needs_name", "ascii_space", "nonascii_name", "namespace", "empty_name", "no_name_no_cut"],
)
def test_sqlite_tcl_suffix_boundaries(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.SQLITE).sql == expected


def test_sqlite_bom_is_space_at_a_token_start() -> None:
    sql = "SELECT ﻿1, 'ZQTAIL'"
    returned = sqlite3.connect(":memory:").execute(sql).fetchall()
    assert returned == [(1, "ZQTAIL")]
    assert normalize(sql, Dialect.SQLITE).sql == "SELECT ?, ?"


def test_sqlite_bom_continues_an_identifier_before_dollar_variable() -> None:
    sql = "WITH x﻿$a(')') AS (SELECT 'SECRET') SELECT * FROM x﻿$a"
    returned = sqlite3.connect(":memory:").execute(sql, {"a(')')": "ZQBOUND"}).fetchall()
    assert returned == [("SECRET",)]
    assert "SECRET" not in normalize(sql, Dialect.SQLITE).sql
