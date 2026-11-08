"""``LexRules``: study section 5 as data. A dialect meets rules in ``READINGS`` and nowhere else.

Every field is a ``bool``, an enum member or a ``frozenset``: a closer that needs code is a scanner chosen by an enum
member, never a callable field. Source lines cited are from ``study.md`` section 1. ``UNSUPPORTED`` has no entry: its
text is hidden, never read (architecture spec section 7). ``mssql`` and ``oracle`` are ``UNSUPPORTED``: no server
source was read.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum

from sharpit.engine.sqltext.dialect import Dialect


class Backslash(Enum):
    NONE = "none"
    E_ONLY = "e_only"
    ALWAYS = "always"


class DoubleQuote(Enum):
    NAME = "name"
    STRING = "string"


class BacktickRun(Enum):
    NONE = "none"
    NAME = "name"


class Bracket(Enum):
    CHARACTER = "character"
    TO_FIRST_CLOSE = "to_first_close"


class DollarOpen(Enum):
    NONE = "none"
    POSTGRESQL_TAG = "postgresql_tag"
    MYSQL_TAG = "mysql_tag"
    CUT_ON_OPEN = "cut_on_open"


class DollarCloser(Enum):
    NONE = "none"
    FIRST_IDENTICAL = "first_identical"
    NO_STEP_BACK = "no_step_back"


class Reading(Enum):
    NO = "no"
    YES = "yes"
    CUT = "cut"


class HashRule(Enum):
    OPERATOR = "operator"
    COMMENT = "comment"
    VARIABLE = "variable"
    NAME = "name"


class DigitDollar(Enum):
    OPENS = "opens"
    NAME = "name"
    ILLEGAL = "illegal"


class VariableSuffix(Enum):
    NONE = "none"
    TCL_PAREN = "tcl_paren"


@dataclass(frozen=True, slots=True)
class LexRules:
    backslash_in_single: Backslash
    backslash_in_double: Backslash
    double_quote: DoubleQuote
    backtick_run: BacktickRun
    bracket: Bracket
    dollar: DollarOpen
    dollar_name_boundary: bool
    dollar_closer: DollarCloser
    nested_comments: Reading
    dash_needs_space: Reading
    cr_ends_dash: Reading
    hash: HashRule
    dot_digits_is_name: bool
    digit_dollar: DigitDollar
    radix: frozenset[str]
    at_token: bool
    variable_suffix: VariableSuffix
    cut_backslash: bool
    cut_bracket: bool
    executable_prefixes: frozenset[str]
    hide_double_quoted: bool = False
    cut_prefixes: frozenset[str] = frozenset()  # text this reading stops at wherever it stands
    backslash_token: bool = False  # outside a string `\` and the next byte are one token


_RADIX_ALL = frozenset({"0x", "0X", "0o", "0O", "0b", "0B", "_"})

POSTGRESQL = LexRules(
    backslash_in_single=Backslash.E_ONLY,  # scan.l:545-552; `standard_conforming_strings` is session state
    backslash_in_double=Backslash.NONE,  # scan.l:294-298
    double_quote=DoubleQuote.NAME,
    backtick_run=BacktickRun.NONE,  # scan.l:367, an operator
    bracket=Bracket.CHARACTER,  # scan.l:366
    dollar=DollarOpen.POSTGRESQL_TAG,  # scan.l:285-287
    dollar_name_boundary=True,
    dollar_closer=DollarCloser.FIRST_IDENTICAL,  # scan.l:757-776
    nested_comments=Reading.YES,  # scan.l:447-485
    dash_needs_space=Reading.NO,  # scan.l:210-213
    cr_ends_dash=Reading.YES,  # scan.l:210-213
    hash=HashRule.OPERATOR,  # scan.l:367
    dot_digits_is_name=False,  # scan.l:395
    digit_dollar=DigitDollar.OPENS,  # scan.l:421
    radix=_RADIX_ALL,  # scan.l:386-393
    at_token=False,
    variable_suffix=VariableSuffix.NONE,
    cut_backslash=True,  # a plain string reads `\` under another setting: session state
    cut_bracket=False,
    executable_prefixes=frozenset(),  # scan.l:328, plain comments
)

MYSQL_84 = LexRules(
    backslash_in_single=Backslash.ALWAYS,  # sql_lex.cc:1043-1054; NO_BACKSLASH_ESCAPES is session state
    backslash_in_double=Backslash.ALWAYS,  # :1043-1054; ANSI_QUOTES is session state
    double_quote=DoubleQuote.STRING,
    backtick_run=BacktickRun.NAME,  # :1765-1804
    bracket=Bracket.CHARACTER,  # sql_chars.cc:98
    dollar=DollarOpen.MYSQL_TAG,  # :2160-2193
    dollar_name_boundary=False,
    dollar_closer=DollarCloser.NO_STEP_BACK,  # :1159-1188
    nested_comments=Reading.CUT,  # spec §14 D7 keeps the nested-comment safety cut on the MySQL family
    dash_needs_space=Reading.YES,  # :1504-1506
    cr_ends_dash=Reading.NO,  # :1916
    hash=HashRule.COMMENT,  # :1916
    dot_digits_is_name=True,  # :1611-1612
    digit_dollar=DigitDollar.NAME,  # :1682-1728, integers only
    radix=frozenset({"0x", "0b"}),  # :1677-1726
    at_token=True,  # :2100-2122
    variable_suffix=VariableSuffix.NONE,
    cut_backslash=True,
    cut_bracket=True,  # MariaDB `sql_mode=MSSQL` is session state no text reveals
    executable_prefixes=frozenset({"/*!"}),
    # TiDB reports as MySQL and runs this; no lexer of its was read (spec §14, the owner's word item 4)
    cut_prefixes=frozenset({"/*T!"}),
)

# MariaDB has no dollar quote (charset.c:85), executes `/*M!` (sql_lex.cc:2450-2453) and reads `\` outside a string as
# a token with the next byte (charset.c:95, sql_lex.cc:2091-2096).
MARIADB = replace(
    MYSQL_84,
    dollar=DollarOpen.NONE,
    dollar_name_boundary=False,
    dollar_closer=DollarCloser.NONE,
    executable_prefixes=frozenset({"/*!", "/*M!"}),
    backslash_token=True,
)

SQLITE = LexRules(
    backslash_in_single=Backslash.NONE,  # tokenize.c:396-420
    backslash_in_double=Backslash.NONE,
    double_quote=DoubleQuote.NAME,  # tokenize.c:413-415, DQS; hidden by the renderer
    backtick_run=BacktickRun.NAME,
    bracket=Bracket.TO_FIRST_CLOSE,  # tokenize.c:499-503
    dollar=DollarOpen.NONE,  # tokenize.c:509-538, `$` opens a variable
    dollar_name_boundary=False,
    dollar_closer=DollarCloser.NONE,
    nested_comments=Reading.NO,  # tokenize.c:321-330
    dash_needs_space=Reading.NO,  # tokenize.c:289-293
    cr_ends_dash=Reading.NO,
    hash=HashRule.VARIABLE,  # tokenize.c:509-538
    dot_digits_is_name=False,  # tokenize.c:421-433
    digit_dollar=DigitDollar.ILLEGAL,  # tokenize.c:493-496
    radix=frozenset({"0x", "0X", "_"}),  # tokenize.c:438-492
    at_token=False,
    variable_suffix=VariableSuffix.TCL_PAREN,  # tokenize.c:519-531
    cut_backslash=False,
    cut_bracket=False,
    executable_prefixes=frozenset(),
    hide_double_quoted=True,
)

# Each dialect is read with its own rule table.
READINGS: Mapping[Dialect, tuple[LexRules, ...]] = {
    Dialect.POSTGRESQL: (POSTGRESQL,),
    Dialect.MYSQL_FAMILY: (MYSQL_84, MARIADB),
    Dialect.SQLITE: (SQLITE,),
}
