"""``LexRules``: study section 5 as data. A dialect meets rules in ``READINGS`` and nowhere else.

Every field is a ``bool``, an enum member or a ``frozenset``: a closer that needs code is a scanner chosen by an enum
member, never a callable field. Source lines cited are from ``study.md`` section 1. ``generic`` claims nothing about
the server, so wherever two readings differ it cuts. ``mssql`` and ``oracle`` have no entry: no server source was read.
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
    VALUE_POSITION = "value_position"


class BacktickRun(Enum):
    NONE = "none"
    NAME = "name"
    NAME_OR_CUT = "name_or_cut"


class Bracket(Enum):
    CHARACTER = "character"
    TO_FIRST_CLOSE = "to_first_close"
    TWO_WAY = "two_way"


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
    CUT = "cut"


class DigitDollar(Enum):
    OPENS = "opens"
    NAME = "name"
    ILLEGAL = "illegal"
    NO_OPEN = "no_open"


class VariableSuffix(Enum):
    NONE = "none"
    TCL_PAREN = "tcl_paren"
    NOT_READ = "not_read"


@dataclass(frozen=True, slots=True)
class LexRules:
    backslash_in_single: Backslash
    backslash_in_double: Backslash
    double_quote: DoubleQuote
    backtick_run: BacktickRun
    bracket: Bracket
    dollar: DollarOpen
    dollar_closer: DollarCloser
    nested_comments: Reading
    dash_needs_space: Reading
    cr_ends_dash: Reading
    hash: HashRule
    q_quote_cuts: bool
    dot_digits_is_name: bool
    digit_dollar: DigitDollar
    radix: frozenset[str]
    at_token: bool
    variable_suffix: VariableSuffix
    cut_backslash: bool
    cut_bracket: bool
    executable_prefixes: frozenset[str]


_RADIX_ALL = frozenset({"0x", "0X", "0o", "0O", "0b", "0B", "_"})

POSTGRESQL = LexRules(
    backslash_in_single=Backslash.E_ONLY,  # scan.l:545-552; `standard_conforming_strings` is session state
    backslash_in_double=Backslash.NONE,  # scan.l:294-298
    double_quote=DoubleQuote.NAME,
    backtick_run=BacktickRun.NONE,  # scan.l:367, an operator
    bracket=Bracket.CHARACTER,  # scan.l:366
    dollar=DollarOpen.POSTGRESQL_TAG,  # scan.l:285-287
    dollar_closer=DollarCloser.FIRST_IDENTICAL,  # scan.l:757-776
    nested_comments=Reading.YES,  # scan.l:447-485
    dash_needs_space=Reading.NO,  # scan.l:210-213
    cr_ends_dash=Reading.YES,  # scan.l:210-213
    hash=HashRule.OPERATOR,  # scan.l:367
    q_quote_cuts=False,
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
    dollar_closer=DollarCloser.NO_STEP_BACK,  # :1159-1188
    nested_comments=Reading.NO,  # :1315-1351
    dash_needs_space=Reading.YES,  # :1504-1506
    cr_ends_dash=Reading.NO,  # :1916
    hash=HashRule.COMMENT,  # :1916
    q_quote_cuts=False,
    dot_digits_is_name=True,  # :1611-1612
    digit_dollar=DigitDollar.NAME,  # :1682-1728, integers only
    radix=frozenset({"0x", "0b"}),  # :1677-1726
    at_token=True,  # :2100-2122
    variable_suffix=VariableSuffix.NONE,
    cut_backslash=True,
    cut_bracket=True,  # MariaDB `sql_mode=MSSQL` is session state no text reveals
    executable_prefixes=frozenset({"/*!"}),  # :1993-1998; read as tokens is not built, so it cuts
)

# MariaDB is MySQL with three fields changed (study section 5): `dollar` and `dollar_closer` (no dollar quote,
# charset.c:85) and `executable_prefixes` (`/*M!` executes, :2450).
MARIADB = replace(
    MYSQL_84,
    dollar=DollarOpen.NONE,
    dollar_closer=DollarCloser.NONE,
    executable_prefixes=frozenset({"/*!", "/*M!"}),
)

SQLITE = LexRules(
    backslash_in_single=Backslash.NONE,  # tokenize.c:396-420
    backslash_in_double=Backslash.NONE,
    double_quote=DoubleQuote.VALUE_POSITION,  # tokenize.c:413-415, DQS
    backtick_run=BacktickRun.NAME,
    bracket=Bracket.TO_FIRST_CLOSE,  # tokenize.c:499-503
    dollar=DollarOpen.NONE,  # tokenize.c:509-538, `$` opens a variable
    dollar_closer=DollarCloser.NONE,
    nested_comments=Reading.NO,  # tokenize.c:321-330
    dash_needs_space=Reading.NO,  # tokenize.c:289-293
    cr_ends_dash=Reading.NO,
    hash=HashRule.VARIABLE,  # tokenize.c:509-538
    q_quote_cuts=False,
    dot_digits_is_name=False,  # tokenize.c:421-433
    digit_dollar=DigitDollar.ILLEGAL,  # tokenize.c:493-496
    radix=frozenset({"0x", "0X", "_"}),  # tokenize.c:438-492
    at_token=False,
    variable_suffix=VariableSuffix.TCL_PAREN,  # tokenize.c:519-531
    cut_backslash=False,
    cut_bracket=False,
    executable_prefixes=frozenset(),
)

# No claim about the server: every reading some real server could take is possible, so a difference cuts.
GENERIC = LexRules(
    backslash_in_single=Backslash.ALWAYS,
    backslash_in_double=Backslash.NONE,  # today's mysql=False: no escape in `"`, a backslash run cuts
    double_quote=DoubleQuote.VALUE_POSITION,
    backtick_run=BacktickRun.NAME_OR_CUT,
    bracket=Bracket.TWO_WAY,
    dollar=DollarOpen.POSTGRESQL_TAG,  # today's mysql=False (Task 12 keeps it); the cut stays a later call
    dollar_closer=DollarCloser.FIRST_IDENTICAL,
    nested_comments=Reading.CUT,
    dash_needs_space=Reading.CUT,
    cr_ends_dash=Reading.CUT,
    hash=HashRule.CUT,
    q_quote_cuts=True,
    dot_digits_is_name=False,
    digit_dollar=DigitDollar.NO_OPEN,
    radix=_RADIX_ALL,
    at_token=False,
    variable_suffix=VariableSuffix.NOT_READ,
    cut_backslash=True,
    cut_bracket=True,
    executable_prefixes=frozenset({"/*!", "/*M!"}),
)

# staged: only today's two readings, so behaviour holds; tasks 16 to 18 give each dialect its own rules
READINGS: Mapping[Dialect, tuple[LexRules, ...]] = {
    Dialect.POSTGRESQL: (GENERIC,),
    Dialect.MYSQL_FAMILY: (MYSQL_84,),
    Dialect.SQLITE: (GENERIC,),
}
