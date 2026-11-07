"""Study section 5 held as data: every cell of its 16 rows, in the four columns kept, has a field of ``LexRules``.

``mssql`` and ``oracle`` have no column: the design maps them to ``UNSUPPORTED``. Line cites are the study's own
(``study.md`` section 1) and name the server source: ``pg`` is scan.l, ``my`` is sql_lex.cc, ``mdb`` is MariaDB's
sql_lex.cc, ``sl`` is tokenize.c.
"""

from __future__ import annotations

import ast
from dataclasses import fields, replace
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.sqltext import rules as rules_module
from sharpit.engine.sqltext.rules import (
    GENERIC,
    MARIADB,
    MYSQL_84,
    POSTGRESQL,
    SQLITE,
    Backslash,
    BacktickRun,
    Bracket,
    DigitDollar,
    DollarCloser,
    DollarOpen,
    DoubleQuote,
    HashRule,
    LexRules,
    Reading,
    VariableSuffix,
)

RADIX_ALL = frozenset({"0x", "0X", "0o", "0O", "0b", "0B", "_"})


COLUMNS: dict[str, LexRules] = {"postgresql": POSTGRESQL, "mysql": MYSQL_84, "sqlite": SQLITE, "generic": GENERIC}


def column(name: str) -> LexRules:
    """The rules a column of the study reads under, by the named constant: ``READINGS`` is staged by Task 12 on."""
    return COLUMNS[name]


# Row id -> column -> {field: expected value}.
ROWS: dict[str, dict[str, dict[str, Any]]] = {
    # `\` in `'`: pg scan.l:545-552 (E only; plain string under standard_conforming_strings), my:1043-1054 (escape),
    # sl:396-420 (none). A backslash cut stays on pg and my: session state (D7), none on sl.
    "backslash_in_single": {
        "postgresql": {"backslash_in_single": Backslash.E_ONLY, "cut_backslash": True},
        "mysql": {"backslash_in_single": Backslash.ALWAYS, "cut_backslash": True},
        "sqlite": {"backslash_in_single": Backslash.NONE, "cut_backslash": False},
        "generic": {"backslash_in_single": Backslash.ALWAYS, "cut_backslash": True},
    },
    # `\` in `"`: pg 294-298 (none), my 1043-1054 (escape; ANSI_QUOTES is session state), sl 396-420 (none). generic is
    # Generic text has no double-quote escape, but the backslash run remains ambiguous.
    "backslash_in_double": {
        "postgresql": {"backslash_in_double": Backslash.NONE},
        "mysql": {"backslash_in_double": Backslash.ALWAYS},
        "sqlite": {"backslash_in_double": Backslash.NONE},
        "generic": {"backslash_in_double": Backslash.NONE},
    },
    # `"`: pg 294-298 name, my literal, sl 413-415 name (DQS); generic keeps its value-position rule.
    # On SQLite, whether a name shows is a separate field: `hide_double_quoted=True`, read by the renderer.
    "double_quote": {
        "postgresql": {"double_quote": DoubleQuote.NAME, "hide_double_quoted": False},
        "mysql": {"double_quote": DoubleQuote.STRING, "hide_double_quoted": False},
        "sqlite": {"double_quote": DoubleQuote.NAME, "hide_double_quoted": True},
        "generic": {"double_quote": DoubleQuote.VALUE_POSITION, "hide_double_quoted": False},
    },
    # Backtick: pg 367 an operator, my 1765-1804 and sl 396-420 a name; generic cuts a run with a quote or left open.
    "backtick": {
        "postgresql": {"backtick_run": BacktickRun.NONE},
        "mysql": {"backtick_run": BacktickRun.NAME},
        "sqlite": {"backtick_run": BacktickRun.NAME},
        "generic": {"backtick_run": BacktickRun.NAME_OR_CUT},
    },
    # `[`: pg 366 and my sql_chars.cc:98 a character, sl 499-503 to the first `]`. The family keeps a bracket cut
    # (MariaDB sql_mode=MSSQL, mdb 2105-2106, is session state).
    "bracket": {
        "postgresql": {"bracket": Bracket.CHARACTER, "cut_bracket": False},
        "mysql": {"bracket": Bracket.CHARACTER, "cut_bracket": True},
        "sqlite": {"bracket": Bracket.TO_FIRST_CLOSE, "cut_bracket": False},
        "generic": {"bracket": Bracket.TWO_WAY, "cut_bracket": True},
    },
    # Dollar quote opens: pg 285-287 tag, my 2160-2193 tag, sl 509-538 never (`$` opens a variable), generic as today.
    "dollar_opens": {
        "postgresql": {"dollar": DollarOpen.POSTGRESQL_TAG},
        "mysql": {"dollar": DollarOpen.MYSQL_TAG},
        "sqlite": {"dollar": DollarOpen.NONE},
        "generic": {"dollar": DollarOpen.POSTGRESQL_TAG},
    },
    # Dollar closer: pg 757-776 first identical, my 1159-1188 no step back, generic PostgreSQL's.
    "dollar_closer": {
        "postgresql": {"dollar_closer": DollarCloser.FIRST_IDENTICAL},
        "mysql": {"dollar_closer": DollarCloser.NO_STEP_BACK},
        "sqlite": {"dollar_closer": DollarCloser.NONE},
        "generic": {"dollar_closer": DollarCloser.FIRST_IDENTICAL},
    },
    # Nested `/*`: pg 447-485 counts depth; the family keeps the safety cut from spec §14 D7.
    "nested_comment": {
        "postgresql": {"nested_comments": Reading.YES},
        "mysql": {"nested_comments": Reading.CUT},
        "sqlite": {"nested_comments": Reading.NO},
        "generic": {"nested_comments": Reading.CUT},
    },
    # `/*!` belongs to MySQL; MariaDB adds `/*M!` (sql_lex.cc:2440-2525).
    "executable_comment": {
        "postgresql": {"executable_prefixes": frozenset()},
        "mysql": {"executable_prefixes": frozenset({"/*!"})},
        "sqlite": {"executable_prefixes": frozenset()},
        "generic": {"executable_prefixes": frozenset({"/*!", "/*M!"})},
    },
    # `--`: pg 210-213 always, ends at `\n` or `\r`; my 1504-1506 needs a space, ends at `\n`; sl 289-293 always,
    # ends at `\n`; generic: a tight one or a lone CR cuts.
    "dash": {
        "postgresql": {"dash_needs_space": Reading.NO, "cr_ends_dash": Reading.YES},
        "mysql": {"dash_needs_space": Reading.YES, "cr_ends_dash": Reading.NO},
        "sqlite": {"dash_needs_space": Reading.NO, "cr_ends_dash": Reading.NO},
        "generic": {"dash_needs_space": Reading.CUT, "cr_ends_dash": Reading.CUT},
    },
    # `#`: pg 367 operator, my 1916 comment, sl 509-538 variable prefix, generic a trigger.
    "hash": {
        "postgresql": {"hash": HashRule.OPERATOR},
        "mysql": {"hash": HashRule.COMMENT},
        "sqlite": {"hash": HashRule.VARIABLE},
        "generic": {"hash": HashRule.CUT},
    },
    # `q'`: nothing on pg, my (`q` is an identifier) and sl; a trigger in generic.
    "q_quote": {
        "postgresql": {"q_quote_cuts": False},
        "mysql": {"q_quote_cuts": False},
        "sqlite": {"q_quote_cuts": False},
        "generic": {"q_quote_cuts": True},
    },
    # `.digits` after a word: pg 395 and sl 421-433 literal, my 1611-1612 a name (keep it).
    "dot_digits": {
        "postgresql": {"dot_digits_is_name": False},
        "mysql": {"dot_digits_is_name": True},
        "sqlite": {"dot_digits_is_name": False},
        "generic": {"dot_digits_is_name": False},
    },
    # Digits then `$`: pg 421 the number ends and `$` opens, my 1682-1728 a name (integers only), sl 493-496 illegal,
    # generic opens nothing.
    "digit_dollar": {
        "postgresql": {"digit_dollar": DigitDollar.OPENS},
        "mysql": {"digit_dollar": DigitDollar.NAME},
        "sqlite": {"digit_dollar": DigitDollar.ILLEGAL},
        "generic": {"digit_dollar": DigitDollar.NO_OPEN},
    },
    # Radix: pg 386-393 `0x 0o 0b _`, my 1677-1726 lowercase `0x 0b`, sl 438-492 `0x _`, generic keeps all.
    "radix": {
        "postgresql": {"radix": RADIX_ALL},
        "mysql": {"radix": frozenset({"0x", "0b"})},
        "sqlite": {"radix": frozenset({"0x", "0X", "_"})},
        "generic": {"radix": RADIX_ALL},
    },
    # Variable with a suffix: pg none, my 2100-2122 `@` runs to `[alnum._$]*`, sl 519-531 `$a(..)` to `)` or space,
    # generic does not read it (a limit).
    "variable_suffix": {
        "postgresql": {"at_token": False, "variable_suffix": VariableSuffix.NONE},
        "mysql": {"at_token": True, "variable_suffix": VariableSuffix.NONE},
        "sqlite": {"at_token": False, "variable_suffix": VariableSuffix.TCL_PAREN},
        "generic": {"at_token": False, "variable_suffix": VariableSuffix.NOT_READ},
    },
}

CELLS = [(row, col) for row, cols in ROWS.items() for col in cols]


@pytest.mark.parametrize(("row", "col"), CELLS, ids=[f"{r}-{c}" for r, c in CELLS])
def test_every_cell_of_the_study_has_a_field(row: str, col: str) -> None:
    rules = column(col)
    for name, expected in ROWS[row][col].items():
        assert getattr(rules, name) == expected, name


def is_data(value: object) -> bool:
    return isinstance(value, bool | Enum | frozenset)


def non_data_fields(rules: LexRules) -> list[str]:
    return [f.name for f in fields(rules) if not is_data(getattr(rules, f.name))]


def all_rules() -> list[LexRules]:
    return [GENERIC, MYSQL_84, MARIADB, POSTGRESQL, SQLITE]


def test_rules_are_data() -> None:
    assert [(i, non_data_fields(rules)) for i, rules in enumerate(all_rules()) if non_data_fields(rules)] == []


def test_a_function_field_is_not_data() -> None:
    # planted: a real LexRules whose closer is held as a callable field must fail the same check
    planted = replace(GENERIC, dollar_closer=lambda text: text)  # type: ignore[arg-type]
    assert non_data_fields(planted) == ["dollar_closer"]


def test_the_frozenset_fields_hold_strings() -> None:
    for rules in all_rules():
        assert all(isinstance(item, str) for item in rules.radix | rules.executable_prefixes)


def test_mariadb_is_mysql_with_dollar_executable_comment_and_backslash_readings_changed() -> None:
    # study section 5 and MariaDB sql_lex.cc:2091-2096, 2440-2525: /*M! executes and `\` is a token on MariaDB alone.
    differs = {f.name for f in fields(MARIADB) if getattr(MARIADB, f.name) != getattr(MYSQL_84, f.name)}
    assert differs == {"dollar", "dollar_closer", "executable_prefixes", "backslash_token"}


def test_mariadb_opens_no_dollar_quote() -> None:
    assert MARIADB.dollar is DollarOpen.NONE


def test_mariadb_runs_m_bang() -> None:
    assert "/*M!" in MARIADB.executable_prefixes


def test_mysql_m_bang_is_not_its_executable_comment() -> None:
    assert "/*M!" not in MYSQL_84.executable_prefixes


def test_the_family_keeps_the_bracket_cut_on_both_readings() -> None:
    assert [r.cut_bracket for r in (MYSQL_84, MARIADB)] == [True, True]


def test_generic_is_todays_non_mysql_reading() -> None:
    # Task 12 reads POSTGRESQL, SQLITE and UNSUPPORTED through GENERIC: it keeps the PostgreSQL tag and no `"` escape
    assert (GENERIC.dollar, GENERIC.backslash_in_double) == (DollarOpen.POSTGRESQL_TAG, Backslash.NONE)


def dialect_uses(source: str) -> list[int]:
    """Lines that name ``Dialect`` outside ``READINGS``: a name, an attribute, or an alias of either."""
    tree = ast.parse(source)
    names = {"Dialect"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names |= {a.asname for a in node.names if a.name in names and a.asname}
        elif isinstance(node, ast.Assign) and _names_dialect(node.value, names):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    readings = next(
        (n for n in tree.body if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "READINGS"), None
    )
    inside = {id(n) for n in ast.walk(readings)} if readings else set()
    return [n.lineno for n in ast.walk(tree) if id(n) not in inside and _names_dialect(n, names)]


def _names_dialect(node: ast.AST, names: set[str]) -> bool:
    return (isinstance(node, ast.Name) and node.id in names) or (isinstance(node, ast.Attribute) and node.attr in names)


def test_rules_never_branch_on_a_dialect() -> None:
    # `Dialect` is named in READINGS, the one place a dialect meets rules, and nowhere else.
    assert dialect_uses(Path(rules_module.__file__).read_text(encoding="utf-8")) == []


PLANTED_DIALECT_USES = {
    "name": "from d import Dialect\nx = Dialect.SQLITE\n",
    "attribute": "import m\nx = m.Dialect.SQLITE\n",
    "import_alias": "from d import Dialect as D\nx = D.SQLITE\n",
    "assigned_alias": "from d import Dialect\nD = Dialect\nx = D.SQLITE\n",
}


@pytest.mark.parametrize("source", PLANTED_DIALECT_USES.values(), ids=PLANTED_DIALECT_USES.keys())
def test_a_planted_dialect_use_is_found(source: str) -> None:
    assert dialect_uses(source) != []


def test_a_dialect_in_readings_alone_is_allowed() -> None:
    assert dialect_uses("READINGS: dict = {Dialect.SQLITE: (S,)}\n") == []
