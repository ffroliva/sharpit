"""MySQL-family readings follow MySQL 8.4 sql_lex.cc and MariaDB sql_lex.cc."""

from __future__ import annotations

from dataclasses import fields

import pytest

from sharpit.engine.capture.statement import statement_text
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import LEXER, Dialect, lexer
from sharpit.engine.sqltext.lexer import _MAX_SCAN_LENGTH, _dollar_quote_end
from sharpit.engine.sqltext.rules import (
    MARIADB,
    MYSQL_84,
    READINGS,
    Backslash,
    Bracket,
    DollarOpen,
    DoubleQuote,
    HashRule,
    Reading,
)

MARKER, NUMBER = "ZQXJKV", "7654329"


def scan(sql: str) -> lexer.Scan:
    return LEXER.scan(sql, Dialect.MYSQL_FAMILY)


def test_mysql_rules_match_server_source() -> None:
    # mysql/sql/sql_lex.cc:1043-1054,1504-1508,1611-1612,1676-1735,1758-1804,1916,2100-2122,2160-2193;
    # mysql/strings/sql_chars.cc:97-131
    assert MYSQL_84.backslash_in_single is Backslash.ALWAYS
    assert MYSQL_84.double_quote is DoubleQuote.STRING
    assert MYSQL_84.backtick_run.value == "name"
    assert MYSQL_84.bracket is Bracket.CHARACTER
    assert MYSQL_84.hash is HashRule.COMMENT
    assert MYSQL_84.dash_needs_space is Reading.YES
    assert MYSQL_84.dot_digits_is_name
    assert MYSQL_84.digit_dollar.value == "name"
    assert MYSQL_84.at_token
    assert MYSQL_84.executable_prefixes == frozenset({"/*!"})


def test_mariadb_rules_match_server_source() -> None:
    # mariadb/sql/sql_lex.cc:2091-2096,2114-2130,2231-2285,2440-2525,2692-2713; mysys/charset.c:78-100
    assert MARIADB.dollar is DollarOpen.NONE
    assert "/*!" in MARIADB.executable_prefixes
    assert "/*M!" in MARIADB.executable_prefixes
    assert MARIADB.backslash_token


def test_family_rule_sets_differ_only_where_the_sources_do() -> None:
    """This is what lets text with no ``$``, ``\\`` or ``/*M!`` skip the second read: a new difference fails here."""
    differs = {f.name for f in fields(MARIADB) if getattr(MARIADB, f.name) != getattr(MYSQL_84, f.name)}
    assert differs == {"dollar", "dollar_closer", "executable_prefixes", "backslash_token"}


def test_family_reads_both_rule_sets() -> None:
    assert READINGS[Dialect.MYSQL_FAMILY] == (MYSQL_84, MARIADB)


def _reads(monkeypatch: pytest.MonkeyPatch, sql: str) -> int:
    calls = 0
    read = lexer._read

    def count(*args: object, **kwargs: object) -> lexer._Pass:
        nonlocal calls
        calls += 1
        return read(*args, **kwargs)  # type: ignore[arg-type]

    with monkeypatch.context() as patch:
        patch.setattr(lexer, "_read", count)
        scan(sql)
    return calls


def test_an_orm_statement_pays_one_read(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _reads(monkeypatch, "SELECT `column` FROM `table` WHERE `id` = 1") == 1


@pytest.mark.parametrize("sql", ["SELECT $$ value $$", "SELECT `a$b`", "SELECT 'a\\_b'"])
def test_a_statement_holding_what_the_rule_sets_read_apart_pays_a_second_read(
    monkeypatch: pytest.MonkeyPatch, sql: str
) -> None:
    assert _reads(monkeypatch, sql) > 1


def test_mariadb_does_not_open_a_dollar_quote() -> None:
    assert _dollar_quote_end("$$value$$", 0, MARIADB) == -1


def test_digits_after_a_dot_that_run_into_a_name_stay_in_the_name() -> None:
    sql = "SELECT t.1col FROM t"
    assert scan(sql).text == sql


def test_family_cuts_at_a_dollar_quote_disagreement() -> None:
    sql = "SELECT $$ ' $$, 'SECRET'"
    assert scan(sql).cut == sql.index("$$")
    assert "SECRET" not in scan(sql).text


def test_a_real_read_of_the_second_rules_cuts_a_bracket_earlier_than_a_dollar_blind_read() -> None:
    # the rule sets read the bracket's body apart, so the stop moves to it: it shows less, never more (Task 12's note)
    sql = "select [$$ ' $$], 'x'"
    assert scan(sql).cut == sql.index("[")
    assert scan(sql).text == "select ?"


WITNESSES = {
    "dollar": "SELECT $$ ' $$, '{}'",
    "m_bang": "SELECT 1 /*M! , '{}' */",
    "tidb": "SELECT 1 /*T! , '{}' */",
    "bracket": "SELECT 1 AS [it's{}], 'SECRET'",
    "real_dollar": "SELECT .5$$ ' $$, '{}'",
    "bad_exponent": "SELECT 1.5e+''{}'",
    "signed_exponent": "SELECT t.1.5e+0x{}",
    "escape": "SELECT \\N{}",
    "session": "SELECT '\\'\\', '{}'",
    "head": "SELECT [\\N0x{}@`",
    "key": 'SELECT "password":{}="v"',
    "system_variable": "SELECT @@x..5$${}''{}'",
}
SEEDS = (7, 8, 9)


@pytest.mark.parametrize("witness", WITNESSES)
@pytest.mark.parametrize("seed", SEEDS)
def test_family_cut_witness(witness: str, seed: int) -> None:
    value = f"ZQ{seed}17" if witness not in ("signed_exponent", "escape", "head") else f"765{seed}17"
    sql = WITNESSES[witness].format(value, value)
    read = scan(sql)
    assert read.cut >= 0
    assert value not in read.text


def test_reads_two_ways_sees_where_the_readings_part() -> None:
    """Task 12 kept this in ``_ambiguous_cut``. A closer found past such a point is a guess (errortext ``_block``)."""
    assert LEXER.reads_two_ways("SELECT $$ ] $$", Dialect.MYSQL_FAMILY)


def test_the_backslash_cut_needs_no_tag() -> None:
    assert scan("SELECT 'a\\', 'SECRET' AS col").cut >= 0
    assert "SECRET" not in scan("SELECT 'a\\', 'SECRET' AS col").text


def test_family_keeps_the_executable_comment_cut() -> None:
    sql = "SELECT 1 /*! -- */ don't\n, 'ZQXJKV' */"
    assert scan(sql).cut >= 0
    assert "ZQXJKV" not in scan(sql).text


@pytest.mark.parametrize("sql", ["SELECT 1 AS [it's], 'SECRET'", "SELECT [a'b], 'SECRET', [c'd]"])
def test_family_keeps_the_bracket_cut(sql: str) -> None:
    assert scan(sql).cut >= 0
    assert "SECRET" not in scan(sql).text


@pytest.mark.parametrize("sql", ["/*T![f] , 'a */ b', 'SECRET' */", "/*T!"])
def test_a_tidb_comment_cuts(sql: str) -> None:
    assert scan(sql).cut >= 0
    assert "SECRET" not in scan(sql).text


def test_a_family_read_past_the_scan_limit_shows_nothing_past_it() -> None:
    sql = "SELECT " + "$tag$" + "x" * (_MAX_SCAN_LENGTH - 20) + "'SECRET'" + "$tag$"
    assert len(scan(sql).source) == _MAX_SCAN_LENGTH
    assert scan(sql).cut == sql.index("$tag$")
    assert "SECRET" not in scan(sql).text


# each row is a shrunk case of the fuzz on the port of the servers' lexers (arch\t17): a value token some real reading
# holds, shown by the build before this task. The name says which reading holds it.
SHRUNK = {
    "mysql84-a_real_ends_its_token_so_dollars_open": ("SELECT .5$$" + MARKER, MARKER),
    "mysql84-after_an_exponent_too": ("SELECT 1e5$$" + MARKER, MARKER),
    "mysql84-a_double_dot_owns_no_word": ("SELECT x..5$$0x" + NUMBER, NUMBER),
    "mysql84-a_bad_exponent_eats_a_dollar": ("SELECT 1.5e$" + NUMBER, NUMBER),
    "mysql84-a_bad_exponent_eats_a_quote": (f"SELECT 1.5e+''{MARKER}'", MARKER),
    "mysql84-no_exponent_in_a_name_chain": ("SELECT t.1.5e+0x" + NUMBER, NUMBER),
    "mysql84-no_exponent_after_a_digit_led_word": ("SELECT 0b121.5e+1e5$$" + NUMBER, NUMBER),
    "mysql84-a_non_ascii_lead_starts_a_name": ("SELECT \xa01.5e+0x" + NUMBER, NUMBER),
    "mysql84-a_non_ascii_digit_starts_a_name": ("SELECT \u06631E+1e5" + NUMBER + ".", NUMBER),
    "mysql84-a_unicode_digit_after_exponent_does_not_split_a_hex_value": ("SELECT 1.5e٣0x" + NUMBER, NUMBER),
    "mysql84-a_system_variable_has_no_host": (f"SELECT @@x..5$${MARKER}''{MARKER}'", MARKER),
    "mysql84-a_signed_exponent_then_a_point": ("SELECT ﻿1E+1.$$a$" + MARKER + "$a$", MARKER),
    "mysql84-a_host_is_ascii": (f"SELECT @$é$...5$$`a'`{MARKER}'", MARKER),
    "mariadb_mssql-a_doubled_closer_goes_on": (f"SELECT [a]]`[it's], '{MARKER}'", MARKER),
    "mariadb_mssql-bracket_after_name_chain_starts_a_value": ("SELECT t.$[&]]:.7654001` AS [it's]$1- 'ZQ02X'", "ZQ02X"),
    "mariadb-backslash_n_ends_a_token": ("SELECT \\N" + NUMBER, NUMBER),
    "mariadb-backslash_eats_any_byte": ("SELECT \\x" + NUMBER, NUMBER),
    "mariadb-a_swallowing_bracket_hides_the_parting": ("SELECT [\\N0x" + NUMBER + "@`", NUMBER),
    "mariadb_nbe-the_stripped_text_reads_alike": (f"SELECT '\\'\\', '{MARKER}'", MARKER),
}


@pytest.mark.parametrize(("sql", "value"), SHRUNK.values(), ids=SHRUNK)
def test_a_value_some_real_reading_holds_never_shows(sql: str, value: str) -> None:
    assert value not in scan(sql).text


MASKER = Masker(Exposure.MASKED, True)


@pytest.mark.parametrize(
    "sql",
    ['select "password":hunter2xyz="v"', 'select "password" : hunter2xyz="v"'],
    ids=["tight", "spaced"],
)
def test_a_key_the_scan_hides_takes_its_value_with_it(sql: str) -> None:
    """The masker's last pass reads the render, and on MySQL the render has no ``"password"``."""
    assert "hunter2xyz" not in (statement_text(MASKER, sql, Dialect.MYSQL_FAMILY) or "")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT `a`.`id`, `a`.`name` FROM `users` `a` WHERE `a`.`id` = 1",
        "SELECT t.1col, db.2020_sales, x.y FROM t",
        "SELECT 'a$b', '$.items[0]', 'C:\\\\dir'",
        "SELECT `j`->'$.a', j->>'$.b' FROM t",
        "SELECT /*+ MAX_EXECUTION_TIME(100) */ `id` FROM `t`",
        "SELECT @a := 1, @@session.sql_mode, @@global.max_connections",
        "SELECT 1.5, .5, 1e5, 1.5e3, 0x1F, x'1F'",
    ],
)
def test_ordinary_mysql_reads_one_way(sql: str) -> None:
    """The other side of a cut: what the readings agree on must not stop."""
    assert scan(sql).cut == -1


def test_a_bracket_inside_a_string_does_not_start_a_family_cut() -> None:
    assert scan("SELECT '$.items[0]]'").cut == -1


def test_a_second_bracket_shape_is_hidden_in_the_rendered_mysql_statement() -> None:
    sql = "SELECT x[1][2]], ' ] 'ZSECRET'"

    assert "ZSECRET" not in (statement_text(Masker(Exposure.MASKED, True), sql, Dialect.MYSQL_FAMILY) or "")


@pytest.mark.parametrize(
    ("sql", "opener"),
    [
        ("SELECT [p], x[a]], ' ] 'ZSECRET'", "[a]"),
        ("SELECT [a[b]], ' ] 'ZSECRET'", "["),
        ("SELECT x[1][2]], ' ] 'ZSECRET'", "[2]"),
        ("SELECT [p] FROM t WHERE y[a]], ' ] = 'ZSECRET'", "[a]"),
    ],
    ids=["subscript", "nested", "second-subscript", "predicate"],
)
def test_a_mssql_doubled_bracket_cuts_at_the_earliest_matching_opener(sql: str, opener: str) -> None:
    assert scan(sql).cut == sql.index(opener)


@pytest.mark.parametrize(
    "sql",
    ["SELECT @a.1e①e-0x7654001", "SELECT 1E٣٣..0x7654001"],
    ids=["mysql-number-ident", "mariadb-real-or-point"],
)
def test_a_non_ascii_character_after_a_mysql_exponent_cuts_the_read(sql: str) -> None:
    assert "7654001" not in (statement_text(Masker(Exposure.MASKED, True), sql, Dialect.MYSQL_FAMILY) or "")


@pytest.mark.parametrize(
    ("sql", "marker"),
    [
        ("SELECT ٣..0x7654001", "7654001"),
        ("SELECT ,7654001.5..0x7654002", "7654002"),
        ("SELECT 0b12..0x7654001", "7654001"),
    ],
    ids=["unicode-digit", "decimal-number", "malformed-binary"],
)
def test_mariadb_double_dot_before_hex_literal_fails_closed(sql: str, marker: str) -> None:
    shown = statement_text(Masker(Exposure.MASKED, True), sql, Dialect.MYSQL_FAMILY) or ""
    assert marker not in shown


def test_mariadb_dot_radix_cut_ignores_strings() -> None:
    sql = "SELECT '1..0x7654001', 1"
    assert statement_text(Masker(Exposure.MASKED, True), sql, Dialect.MYSQL_FAMILY) == "SELECT ?, ?"


@pytest.mark.parametrize(
    ("sql", "marker"),
    [
        ("SELECT 1e7654001_0é", "7654001"),
        ("SELECT ①e-0x7654001", "7654001"),
        ("SELECT 1....0x7654001", "7654001"),
        ("SELECT 1e7654001_٣", "7654001"),
        ("SELECT .1e7654001_0\xa0", "7654001"),
        ("SELECT ①..0x7654001", "7654001"),
        ("SELECT ٣....0b101100100001", "101100100001"),
        ("SELECT 0x7654001０..0x7654002", "7654002"),
        ("SELECT 1.5..0b101100100001 ٣.٣ ..0x_7654002", "101100100001"),
        ("SELECT ..5.e7654001", "7654001"),
    ],
    ids=[
        "underscore-exponent",
        "unicode-digit-name",
        "even-dot-run",
        "unicode-exponent-digit",
        "nbsp-after-exponent",
        "unicode-radix-lead",
        "binary-after-even-dots",
        "fullwidth-digit-and-dots",
        "earliest-cut-wins",
        "dots-before-number",
    ],
)
def test_uncertain_mysql_number_read_cuts_at_number(sql: str, marker: str) -> None:
    shown = statement_text(Masker(Exposure.MASKED, True), sql, Dialect.MYSQL_FAMILY) or ""
    assert marker not in shown


@pytest.mark.parametrize(
    ("sql", "marker"),
    [
        ("SELECT ①_0e-0x7654001", "7654001"),
        ("SELECT ²_0e+0x7654001", "7654001"),
        ("SELECT ③_0.5e-0x7654001", "7654001"),
        ("SELECT ⑴_0_0e-0b1011001000", "1011001000"),
        ("SELECT a-①_0e-0x7654001", "7654001"),
    ],
    ids=[
        "circled-digit-exponent",
        "superscript-digit-exponent",
        "circled-digit-decimal-exponent",
        "parenthesized-digit-binary-exponent",
        "circled-digit-after-name",
    ],
)
def test_non_ascii_first_number_character_cuts_the_mysql_read(sql: str, marker: str) -> None:
    shown = statement_text(Masker(Exposure.MASKED, True), sql, Dialect.MYSQL_FAMILY) or ""
    assert marker not in shown


@pytest.mark.parametrize(
    ("dialect", "sql", "expected"),
    [
        (Dialect.POSTGRESQL, "SELECT @a.1e①e-0x7654001", "SELECT @a.?e-?"),
        (Dialect.POSTGRESQL, "SELECT 1E٣٣..0x7654001", "SELECT ?..?"),
        (Dialect.SQLITE, "SELECT @a.1e①e-0x7654001", "SELECT @a.?e-?"),
        (Dialect.SQLITE, "SELECT 1E٣٣..0x7654001", "SELECT ?..?"),
        (Dialect.UNSUPPORTED, "SELECT @a.1e①e-0x7654001", "SELECT @a.?e-?"),
        (Dialect.UNSUPPORTED, "SELECT 1E٣٣..0x7654001", "SELECT ?..?"),
    ],
    ids=[
        "postgresql-number-ident",
        "postgresql-real",
        "sqlite-number-ident",
        "sqlite-real",
        "generic-number-ident",
        "generic-real",
    ],
)
def test_mysql_exponent_fail_closed_rule_does_not_change_other_dialect_output(
    dialect: Dialect, sql: str, expected: str
) -> None:
    assert statement_text(Masker(Exposure.MASKED, True), sql, dialect) == expected
