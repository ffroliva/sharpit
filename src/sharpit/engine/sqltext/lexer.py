"""The SQL lexer: raw text to runs (``SqlStatementNormalizer``, deviations in MVP spec §14), apart from what shows.

It decides nothing about secrets and imports nothing of ``masking``: a ``"`` run it cannot place by shape is reported as
``Kind.DOUBLE_QUOTED`` and the renderer, handed the detector by the facade, decides it (predict C1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Literal, NamedTuple, Protocol, cast

from sharpit.engine.sqltext.dialect import Dialect
from sharpit.engine.sqltext.family import family_cut, parting_readings
from sharpit.engine.sqltext.numbers import skip_number as _skip_number
from sharpit.engine.sqltext.numbers import uncertain_number_cut as _uncertain_number_cut
from sharpit.engine.sqltext.rules import (
    READINGS,
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


class Kind(Enum):
    """What a run is: ``CODE`` is a quoted name copied as it stands, ``COMMENT`` becomes a space, ``LITERAL`` a ``?``.

    ``DOUBLE_QUOTED`` is a ``"`` run that reads as a name unless the caller says it is a secret: in a value position,
    on MySQL, past the scan limit or with a character no name holds, it is a ``LITERAL`` already.
    """

    CODE = "code"
    LITERAL = "literal"
    DOUBLE_QUOTED = "double_quoted"
    COMMENT = "comment"


_CODE, _LITERAL, _DOUBLE_QUOTED, _COMMENT = Kind.CODE, Kind.LITERAL, Kind.DOUBLE_QUOTED, Kind.COMMENT


Run = tuple[int, int, Kind]
"""Raw positions of a run, in the text the scan read: start, end, kind. A plain tuple, built once per run on the hot
path; a caller that wants names reads it as ``Range(*run)``."""


class Range(NamedTuple):
    """The named view of one ``Run``; the scan itself never builds one."""

    start: int
    end: int
    kind: Kind


class Candidate(NamedTuple):
    """One ``DOUBLE_QUOTED`` run: where it starts in ``Scan.text`` and whether a literal there is in a predicate."""

    at: int
    predicate: bool


@dataclass(frozen=True, slots=True)
class Scan:
    """One read of raw text. ``text`` is the output with every ``DOUBLE_QUOTED`` run as it stands: ``candidates`` has
    one entry per such run, in order, so a caller that calls one a secret can replace it by ``?`` without a second read.

    ``cut`` is where a statement that reads two ways stops, ``-1`` when it reads one way; ``runs`` ends there, and
    ``uncut_runs`` is the read of the whole text, so that error text needs no second read (predict C4).
    """

    source: str
    text: str
    runs: tuple[Run, ...]
    literals: int
    predicate_literals: int
    cut: int
    uncut_runs: tuple[Run, ...]
    candidates: tuple[Candidate, ...]
    hide_double_quoted: bool = False


class SqlLexer(Protocol):
    def scan(self, sql: str, dialect: Dialect) -> Scan: ...

    def block_closer(self, text: str, dialect: Dialect) -> int: ...

    def reads_two_ways(self, sql: str, dialect: Dialect) -> bool: ...


def readings(dialect: Dialect) -> tuple[LexRules, ...]:
    """The rules a dialect reads with: the one place the lexer meets a ``Dialect`` member.

    ``UNSUPPORTED`` has none: its text is hidden before any read, and an unwired path that reaches here fails closed.
    """
    return READINGS[dialect]  # a KeyError for UNSUPPORTED, or for anything that is no dialect


def quoted_body(source: str, start: int, end: int) -> str:
    """The text inside the quotes of the ``"`` run at ``start``; a run left open has no closing quote."""
    return source[start + 1 : end - 1 if end > start + 1 and source[end - 1] == '"' else end]


_MAX_SCAN_LENGTH = 20_000
# A square-bracket identifier is a name, words and spaces only, no word led by a digit: anything else in brackets is a
# value and stays in the scan (``ARRAY['x']``, ``ARRAY [lower($$x$$)]``, ``[2024 sales]``, ``a [CASE WHEN x THEN 1]``);
# showing a value is the worse mistake
_BRACKET_IDENTIFIER = re.compile(r"\[[^\W\d]\w*(?: +[^\W\d]\w*)* *\]")
# a bracket's body also ends at the next ``[``, so bodies never overlap and a run of open brackets stays linear
_BRACKET_STOP = re.compile(r"[\[\]]")
_OPENER = re.compile("['\"`$#]|--|/\\*")  # what can open a run: a body without one reads one way and pays this search
_QUOTE = re.compile("['\"]")
# where a cut stops, every opener the scan knows: a new kind goes here. ``$1`` opens nothing, so a ``$`` counts only in
# a tag's shape, and a tag can start with a digit on MySQL. No comment: a cut there would take every ``/*!`` statement
_RUN_OPENER = re.compile("['\"`]|\\$[\\w\\x80-\\U0010ffff]*\\$")
_AT_TOKEN = re.compile(r"@[0-9A-Za-z_.$]+")  # my_isalnum: a non-ASCII byte ends a host (sql_lex.cc:2113-2118)
_AT_NUMBER = re.compile(r"[@.]\d")
# a number with a point or an exponent ends its token on MySQL; digits alone run on into a name (``1$a$``)
_REAL = re.compile(r"[\d_]*[.eE]")
# where a read past a real is a guess: a bad exponent's next byte is eaten (``1.5e'``, sql_lex.cc:1809-1817), and a
# signed exponent with a name char or a ``.`` after it was none if a name led to it (``t.1.5e+0x7`` is ``5e``, ``+``,
# ``0x7``), and ``1e+1.$$`` then opens a dollar quote
_BAD_EXPONENT = re.compile(r"(?<=[\d.])(?=[eE](?![+-]?\d))|[eE][+-]\d+(?=[\w.$\x80-\U0010ffff])")
_KEY_COLON = re.compile(r"\s*:")
_SYSTEM_VARIABLE = re.compile(r"@[\w$\x80-\U0010ffff]+")  # the second ``@`` of ``@@``: no ``.`` and no host
_EXECUTABLE_COMMENT = ("/*!", "/*M!")  # MySQL and MariaDB run what these hold
SPACE_CHARS = " \t\n\v\f\r"
_SPACE = frozenset(SPACE_CHARS)  # ASCII only: no server reads U+00A0 or U+2028 as whitespace, `isspace` does
_BLOCK_FOLLOWS = re.compile(r"\s*+(?:\[parameters: |\(Background on |\[SQL parameters hidden|\[SQL: |\Z)")


class Out:
    """The output builder; ``opens`` holds the unmatched ``(`` positions so the IN-list check is O(1), not a
    backward scan per literal (BootUI's scan is quadratic on a long list, too slow in Python). A quoted name keeps a run
    of spaces, the only run the output has: ``past_spaces`` holds where each such run began, so a look past it is O(1).
    """

    def __init__(self) -> None:
        self.chars: list[str] = []
        self.opens: list[int] = []
        self.past_spaces: dict[int, int] = {}  # a space after a space -> the last position before the run
        self.runs: list[Run] = []  # in the raw text, in order
        self.marks: list[Candidate] = []  # one per ``DOUBLE_QUOTED`` run

    def append(self, text: str) -> None:
        for c in text:
            if c == "(":
                self.opens.append(len(self.chars))
            elif c == ")" and self.opens:
                self.opens.pop()
            elif c == " " and self.chars and self.chars[-1] == " ":
                self.past_spaces[len(self.chars)] = self.non_space_at(len(self.chars) - 1)
            self.chars.append(c)

    def space(self) -> None:
        if self.chars and self.chars[-1] != " ":
            self.chars.append(" ")

    def non_space_at(self, cursor: int) -> int:
        """``cursor``, or the last position before it when it is a space; -1 when there is none."""
        if cursor >= 0 and self.chars[cursor] == " ":
            return self.past_spaces.get(cursor, cursor - 1)
        return cursor

    def last_non_space(self) -> int:
        return self.non_space_at(len(self.chars) - 1)

    def ends_with_in_list(self) -> bool:
        """The innermost unmatched ``(`` is preceded by the keyword ``in`` (only called at the end of the output)."""
        if not self.opens:
            return False
        return self.ends_with_keyword(self.non_space_at(self.opens[-1] - 1), "in")

    def inside_in_list(self) -> bool:
        cursor = self.last_non_space()
        return cursor >= 0 and self.chars[cursor] in "(," and self.ends_with_in_list()

    def ends_with_keyword(self, end_inclusive: int, keyword: str) -> bool:
        start = end_inclusive - len(keyword) + 1
        if start < 0:
            return False
        if "".join(self.chars[start : end_inclusive + 1]).lower() != keyword:
            return False
        return start == 0 or not self.chars[start - 1].isalnum()

    def predicate_position(self) -> bool:
        cursor = self.last_non_space()
        if cursor < 0:
            return False
        last = self.chars[cursor]
        if last in "=<>!":
            return True
        if last in ",(":
            return self.ends_with_in_list()
        return self.ends_with_keyword(cursor, "like") or self.ends_with_keyword(cursor, "ilike")

    def value_position(self) -> bool:
        """A predicate position or the inside of a ``VALUES (...)`` row (``values (`` or ``), (``)."""
        if self.predicate_position():
            return True
        cursor = self.last_non_space()
        if cursor < 0 or self.chars[cursor] not in ",(" or not self.opens:
            return False
        before = self.non_space_at(self.opens[-1] - 1)
        if self.ends_with_keyword(before, "values"):
            return True
        if before < 0 or self.chars[before] != ",":
            return False
        before = self.non_space_at(before - 1)
        return before >= 0 and self.chars[before] == ")"

    def text(self) -> str:
        return "".join(self.chars)


def _escapes_in_quoted(sql: str, index: int, closing: str, rules: LexRules) -> bool:
    if closing == '"':
        return rules.backslash_in_double is Backslash.ALWAYS
    if closing != "'":  # no dialect escapes a backtick
        return False
    if rules.backslash_in_single is Backslash.ALWAYS:
        return True
    if rules.backslash_in_single is Backslash.E_ONLY:
        prefix = index > 0 and sql[index - 1] in "eE"
        return prefix and (
            index == 1 or not (not sql[index - 2].isascii() or sql[index - 2].isalnum() or sql[index - 2] in "_$")
        )
    return False


def _skip_quoted(sql: str, index: int, closing: str, rules: LexRules) -> int:
    cursor, length = index + 1, len(sql)
    escaped = _escapes_in_quoted(sql, index, closing, rules)
    while cursor < length:
        c = sql[cursor]
        if c == "\\" and escaped and cursor + 1 < length:
            cursor += 2
            continue
        if c == closing:
            if cursor + 1 < length and sql[cursor + 1] == closing:
                cursor += 2
                continue
            return cursor + 1
        cursor += 1
    return length


def _no_step_back_closer(sql: str, tag: str, start: int) -> int:
    """MySQL 8.4.10's match does not step back: a failed one skips what it read, the failing character too, so the
    ``$a$`` of ``$$a$`` closes nothing and ``$a$x$$a$ y $a$`` is one body."""
    cursor = sql.find("$", start)
    while cursor >= 0:
        matched = 1
        while matched < len(tag) and sql.startswith(tag[matched], cursor + matched):
            matched += 1
        if matched == len(tag):
            return cursor
        cursor = sql.find("$", cursor + matched + 1)
    return -1


def _dollar_quote_end(sql: str, index: int, rules: LexRules) -> int:
    """Where the dollar quote at ``index`` ends, the end of the text when it is open; -1 when none opens there."""
    if rules.dollar is DollarOpen.NONE:
        return -1
    cursor, length, body_start = index + 1, len(sql), -1
    digit_first = rules.dollar is DollarOpen.MYSQL_TAG
    while cursor < length:
        c = sql[cursor]
        if c == "$":
            body_start = cursor + 1
            break
        # PostgreSQL's tag: any non-ASCII character counts, ``€`` too, though no Unicode class calls it a letter;
        # MySQL's may start with a digit: ``$1$ x $1$`` is a body 8.4.10 stores
        if not (c.isalpha() or c == "_" or not c.isascii() or (c.isdigit() and (digit_first or cursor > index + 1))):
            return -1
        cursor += 1
    if body_start < 0:
        return -1
    tag = sql[index:body_start]
    no_step_back = rules.dollar_closer is DollarCloser.NO_STEP_BACK
    end = _no_step_back_closer(sql, tag, body_start) if no_step_back else sql.find(tag, body_start)
    return length if end < 0 else end + len(tag)


def _identifier_like(sql: str, index: int, end: int) -> bool:
    start = index + 1
    stop = end - 1 if end > start and sql[end - 1] == '"' else end
    if stop <= start:
        return False
    return all((c.isascii() and c.isalnum()) or c in "_$." for c in sql[start:stop])


def _double_quoted_literal(sql: str, index: int, end: int, out: Out, rules: LexRules) -> Literal[True] | None:
    """sharpit deviation (0.4.0): MySQL reads ``"..."`` as a string, so an identifier-shaped run is a literal too in a
    value position (unless it qualifies a name, ``"b"."id"``) or when it looks like a secret; identifiers elsewhere
    stay readable. Text known to be MySQL's has every run a literal: ``ANSI_QUOTES`` only masks an identifier.

    ``None`` is a run only the secret detector can place, which the lexer does not hold: ``Kind.DOUBLE_QUOTED``."""
    string = rules.double_quote is DoubleQuote.STRING
    if string or end >= _MAX_SCAN_LENGTH:  # a run the scan limit cut open has no shape to read
        return True
    if not _identifier_like(sql, index, end) or (out.value_position() and not sql.startswith(".", end)):
        return True
    return None


def _matches_keyword(sql: str, index: int, keyword: str) -> bool:
    after = index + len(keyword)
    if after > len(sql) or sql[index:after].lower() != keyword:
        return False
    return after >= len(sql) or not (sql[after].isalnum() or sql[after] in "_$")


def _name_char(c: str) -> bool:
    return bool(c) and (c.isalnum() or c in "_$" or not c.isascii())


def _identifier_char_before(out: Out) -> bool:
    return bool(out.chars) and (out.chars[-1].isalnum() or out.chars[-1] in "_$.")


def _quoted_end(sql: str, index: int, out: Out, rules: LexRules) -> int:
    """Where the run opened at ``index`` ends; ``[`` that opens no identifier ends at once, so the scan reads inside."""
    c = sql[index]
    if c != "[":
        return _skip_quoted(sql, index, c, rules)
    if rules.bracket is Bracket.TO_FIRST_CLOSE:
        close = sql.find("]", index + 1)
        return len(sql) if close < 0 else close + 1
    # ``ARRAY[``, ``items[``, ``(ARRAY[1])[``, ``a[1][``, ``ARRAY [``; a space alone proves nothing: ``SELECT [col]``
    subscript = bool(out.chars) and (out.chars[-1].isalnum() or out.chars[-1] in "_$)]")
    subscript = subscript or out.ends_with_keyword(out.last_non_space(), "array")
    found = None if subscript else _BRACKET_IDENTIFIER.match(sql, index)
    return found.end() if found else index + 1


def _two_way_bracket_end(sql: str, index: int, rules: LexRules) -> int:
    """Where the body of the ``[`` at ``index`` ends when a run opened in it is still open there, otherwise -1.

    SQLite closes a bracket at its first ``]`` whatever it holds, so such a body reads apart and the statement stops
    (``_reads_two_ways``): read inside, ``[it's]`` swallows the next quote; read whole, ``['a]', 'x']`` inverts every
    quote after it. A subscript position proves nothing: on SQLite ``a[it's]`` is ``a`` with an alias. A run closed in
    the body, ``a['it''s']``, leaves every reading in the same state, and so does a further ``[`` with no run open:
    the scan reads that one when it gets there. The sentinel ``]`` is swallowed exactly when a run is open at the end.
    """
    stop = _BRACKET_STOP.search(sql, index + 1)
    end = stop.start() if stop else len(sql)
    if not _OPENER.search(sql, index + 1, end):
        return -1
    runs = _read(sql[index + 1 : end] + "]", rules).out.runs
    if not runs or runs[-1][1] != end - index:
        return -1
    return end + 1 if stop and stop[0] == "]" else end


def _dashes_end_in_space(sql: str, index: int) -> bool:
    """MySQL's ``--`` opens a comment only before whitespace, a control character or the end of the text."""
    after = sql[index + 2 : index + 3]
    return not after or ord(after) <= 32 or ord(after) == 127


def _line_comment(sql: str, index: int, rules: LexRules) -> bool:
    needs_space = rules.dash_needs_space is Reading.YES
    dashes = sql.startswith("--", index) and (not needs_space or _dashes_end_in_space(sql, index))
    return dashes or (rules.hash is HashRule.COMMENT and sql[index] == "#")


def _name_part(out: Out) -> bool:
    """Digits here are a part of a name: the ``.`` after them separates, ``rv.1.$$``."""
    return bool(out.chars) and out.chars[-1] == "."


# A scanner reads the construct that may open at ``index`` and returns where the scan goes on and whether that construct
# was a literal. Only these first characters cost a Python call; none of them is a space or a digit.
_Scanned = tuple[int, bool]


def _keep(source: str, index: int, out: Out) -> _Scanned:
    """The character opened nothing after all."""
    out.append(source[index])
    return index + 1, False


def _tcl_variable_name_end(source: str, index: int) -> tuple[int, int, bool]:
    cursor, length = index + 1, len(source)
    n = 0
    while cursor < length:
        c = source[cursor]
        if c.isalnum() or c == "_" or c == "$" or not c.isascii():
            n += 1
            cursor += 1
        elif c == "(":
            return cursor, n, True
        elif c == ":" and cursor + 1 < length and source[cursor + 1] == ":":
            cursor += 2
        else:
            break
    return cursor, n, False


def _tcl_variable_suffix_end(source: str, cursor: int) -> int:
    opening = cursor
    while cursor < len(source) and source[cursor] not in _SPACE and source[cursor] != ")":
        cursor += 1
    if cursor == len(source) or source[cursor] != ")" or "'" in source[opening:cursor] or '"' in source[opening:cursor]:
        return -1
    return cursor + 1


def _scan_tcl_variable(source: str, index: int, out: Out) -> _Scanned:
    """SQLite's `$`, `@`, `:` or `#` variable, with `::` names and a parenthesized suffix (tokenize.c:509-538)."""
    cursor, n, suffix = _tcl_variable_name_end(source, index)
    if n == 0:
        return _keep(source, index, out)
    if not _opens_a_token(source, index):
        return index, True
    if suffix:
        cursor = _tcl_variable_suffix_end(source, cursor)
        if cursor < 0:
            return index, True
    out.chars.extend(source[index:cursor])
    return cursor, False


def _scan_colon(source: str, index: int, out: Out, rules: LexRules) -> _Scanned:
    if rules.variable_suffix is VariableSuffix.TCL_PAREN:
        return _scan_tcl_variable(source, index, out)
    return _keep(source, index, out)


def _scan_line_comment(source: str, index: int, out: Out, rules: LexRules) -> _Scanned:
    if rules.variable_suffix is VariableSuffix.TCL_PAREN and source[index] == "#":
        return _scan_tcl_variable(source, index, out)
    if not _line_comment(source, index, rules):
        return _keep(source, index, out)
    out.space()
    if rules.cr_ends_dash is Reading.YES:
        lf = source.find("\n", index + 1)
        cr = source.find("\r", index + 1)
        if lf < 0:
            end = len(source) if cr < 0 else cr
        elif cr < 0:
            end = lf
        else:
            end = min(lf, cr)
    else:
        newline = source.find("\n", index + 1)
        end = len(source) if newline < 0 else newline
    out.runs.append((index, end, _COMMENT))
    return end, False


def _scan_block_comment(source: str, index: int, out: Out, rules: LexRules) -> _Scanned:
    if not source.startswith("*", index + 1):
        return _keep(source, index, out)
    out.space()
    if rules.nested_comments is Reading.YES:
        depth, cursor, length = 1, index + 2, len(source)
        while cursor < length and depth:
            if source.startswith("/*", cursor):
                depth += 1
                cursor += 2
            elif source.startswith("*/", cursor):
                depth -= 1
                cursor += 2
            else:
                cursor += 1
        end = cursor if depth == 0 else length
    else:
        close = source.find("*/", index + 2)
        end = len(source) if close < 0 else close + 2
    out.runs.append((index, end, _COMMENT))
    return end, False


def _scan_string(source: str, index: int, _out: Out, rules: LexRules) -> _Scanned:
    return _skip_quoted(source, index, "'", rules), True


def _real_number(source: str, start: int, end: int) -> bool:
    """A point or an exponent, or a ``.`` before it that no word owns: ``x..5``, where ``.5`` is a number on MySQL."""
    return bool(_REAL.match(source, start, end)) or (
        source[start - 1 : start] == "." and not _name_char(source[max(start - 2, 0) : start - 1])
    )


def _name_goes_on(source: str, index: int, out: Out, rules: LexRules) -> bool:
    """The output ends inside a name, so the ``$`` at ``index`` is part of it. A number goes on too: ``1$a$`` is a name
    on MySQL and a syntax error on PostgreSQL and SQLite. A ``.`` holds on MySQL only: 0.4.0 hid what follows ``t.$$``,
    so elsewhere it does not.
    """
    last = out.chars[-1] if out.chars else " "
    number = last == "?" and source[index - 1].isalnum()  # a raw ``?`` is an operator, and a string ends in a quote
    if number and rules.digit_dollar is DigitDollar.NAME and _real_number(source, *out.runs[-1][:2]):
        return False
    return last.isalnum() or last in "_$" or not last.isascii() or number or (rules.dot_digits_is_name and last == ".")


def _opens_a_token(source: str, index: int) -> bool:
    """The start of the text, ASCII whitespace or ASCII punctuation: all PostgreSQL's ``$`` and SQLite's variable
    reading trust before them, read from the source and never from the output."""
    if index == 0:
        return True
    before = source[index - 1]
    return before.isascii() and (before.isspace() or not (before.isalnum() or before == "_"))


def _scan_dollar(source: str, index: int, out: Out, rules: LexRules) -> _Scanned:
    if rules.variable_suffix is VariableSuffix.TCL_PAREN:
        return _scan_tcl_variable(source, index, out)
    # ``SELECT`` refuses one on MySQL 8.4.10, but a routine body is one: where a token starts it opens in every mode
    if not rules.dollar_name_boundary and _name_goes_on(source, index, out, rules):
        return _keep(source, index, out)
    end = _dollar_quote_end(source, index, rules)
    if end > 0 and rules.dollar_name_boundary and not _opens_a_token(source, index):
        return index, True  # ambiguous: the statement is hidden from here
    return (end, True) if end > 0 else _keep(source, index, out)


def _scan_dot(source: str, index: int, out: Out, rules: LexRules) -> _Scanned:
    if _identifier_char_before(out) or not source[index + 1 : index + 2].isdigit():
        return _keep(source, index, out)
    return _skip_number(source, index, fail_unicode=rules.digit_dollar is DigitDollar.NAME), True


def _scan_at(source: str, index: int, out: Out, rules: LexRules) -> _Scanned:
    """MySQL's lexer reads what follows ``@`` as one token, a user variable or an account's host: nothing in it opens a
    run. A number in it hides all of it, so what a digit run hid before stays hidden. ``@@`` is two of these."""
    if rules.variable_suffix is VariableSuffix.TCL_PAREN:
        return _scan_tcl_variable(source, index, out)
    found = (_SYSTEM_VARIABLE if source[index - 1 : index] == "@" else _AT_TOKEN).match(source, index)
    if not rules.at_token or found is None:
        return _keep(source, index, out)
    if _AT_NUMBER.search(found[0]):
        return found.end(), True
    out.append(found[0])
    return found.end(), False


def _scan_quoted(source: str, index: int, out: Out, rules: LexRules) -> _Scanned:
    if source[index] == "[" and rules.bracket is Bracket.CHARACTER and not rules.cut_bracket:
        return _keep(source, index, out)
    if source[index] == "`" and rules.backtick_run is BacktickRun.NONE:
        return _keep(source, index, out)
    if (
        source[index] == "["
        and rules.bracket is not Bracket.TO_FIRST_CLOSE
        and (two_way_end := _two_way_bracket_end(source, index, rules)) > 0
    ):
        return two_way_end, True
    end = _quoted_end(source, index, out, rules)
    # under `sql_mode=MSSQL` a ``]]`` goes on (sql_lex.cc:3026): where the bracket ends is session state, so stop
    if rules.bracket is Bracket.CHARACTER and end > index + 1 and source[index] == "[" and source.startswith("]", end):
        return index, True
    kind = _CODE
    if source[index] == '"':
        read = _scan_double_quoted(source, index, end, out, rules)
        if isinstance(read, tuple):
            return read
        kind = read
    out.append(source[index:end])
    out.runs.append((index, end, kind))
    return end, False


def _scan_double_quoted(source: str, index: int, end: int, out: Out, rules: LexRules) -> _Scanned | Kind:
    """The scan's result when the ``"`` run at ``index`` ends the token here, else the kind of run it is to copy."""
    literal = _double_quoted_literal(source, index, end, out, rules)
    # MySQL hides the key of ``"password":value``, so the masker's last pass cannot see what it keys: stop here
    if rules.double_quote is DoubleQuote.STRING and _KEY_COLON.match(source, end):
        return index, True
    if literal is not None:
        return end, True
    out.marks.append(Candidate(len(out.chars), out.predicate_position()))
    return _DOUBLE_QUOTED


def _scan_backslash(source: str, index: int, out: Out, rules: LexRules) -> _Scanned:
    if not rules.backslash_token:
        return _keep(source, index, out)
    # MY_LEX_ESCAPE reads the next byte whatever it is: a quote there opens nothing, and a token starts after it
    out.append(source[index : index + 2])
    out.space()
    return index + 2, False


def _digit_of_a_name(source: str, out: Out, end: int) -> bool:
    """On MySQL, digits after ``word.`` that run on into a name character are a name (sql_lex.cc:1611-1612)."""
    return (
        len(out.chars) > 1 and out.chars[-1] == "." and _name_char(out.chars[-2]) and _name_char(source[end : end + 1])
    )


def _scan_digits(source: str, index: int, out: Out, rules: LexRules) -> _Scanned:
    """A number, or a digit of a name. All digits after ``word.`` stay a literal: ``THEN.5`` hides on every dialect."""
    fail_unicode = rules.digit_dollar is DigitDollar.NAME
    end = _skip_number(source, index, _name_part(out), fail_unicode)
    if rules.dot_digits_is_name and _digit_of_a_name(source, out, end):
        out.chars.append(source[index])
        return index + 1, False
    return end, True


def _scan_keyword(source: str, index: int, out: Out, _rules: LexRules) -> _Scanned:
    if _identifier_char_before(out):
        return _keep(source, index, out)
    if _matches_keyword(source, index, "true"):
        return index + 4, True
    if _matches_keyword(source, index, "false"):
        return index + 5, True
    return _keep(source, index, out)


_SCANNERS = {
    **dict.fromkeys("-#", _scan_line_comment),
    "/": _scan_block_comment,
    "'": _scan_string,
    "\\": _scan_backslash,
    "$": _scan_dollar,
    ".": _scan_dot,
    "@": _scan_at,
    ":": _scan_colon,
    **dict.fromkeys('"`[', _scan_quoted),
    **dict.fromkeys("tTfF", _scan_keyword),
}


class _Pass(NamedTuple):
    source: str
    out: Out  # built from raw text alone, so what is hidden later cannot change a decision the scan made
    literals: int
    predicate_literals: int
    cut: int = -1


def _sqlite_bom(out: Out) -> None:
    if _identifier_char_before(out):
        out.chars.append("﻿")
    else:
        out.space()


def _number_can_start(out: Out) -> bool:
    return not _identifier_char_before(out) or out.chars[-1] == "."


def _read(source: str, rules: LexRules) -> _Pass:
    out = Out()
    chars = out.chars
    literals = predicate_literals = 0
    cut = -1
    index, length = 0, len(source)
    while index < length:
        start = index
        c = source[index]
        scanner = _SCANNERS.get(c)
        literal = False
        if scanner is not None:
            index, literal = scanner(source, index, out, rules)
            if index == start:
                cut = start
                break
        # SQLite treats a BOM as IdChar inside a name and as whitespace at token start (tokenize.c:575-579, 636).
        elif rules.variable_suffix is VariableSuffix.TCL_PAREN and c == "\ufeff":
            _sqlite_bom(out)
            index += 1
        elif c in _SPACE:
            out.space()
            index += 1
        # after a ``.`` a digit starts a literal: ``THEN.5`` is a number, and no keyword list can tell it from ``t.5``
        elif c.isdigit() and _number_can_start(out):
            index, literal = _scan_digits(source, index, out, rules)
        elif c in "()":
            out.append(c)
            index += 1
        else:  # no paren and no space, so ``out.append`` would only append: most of a statement comes here
            chars.append(c)
            index += 1
        if literal:
            literals += 1
            predicate_literals += out.predicate_position()
            out.append("?")
            out.runs.append((start, index, _LITERAL))
    return _Pass(source, out, literals, predicate_literals, cut)


def _holds_a_trigger(source: str) -> bool:
    """A statement with none of these reads one way, and pays only these tests."""
    return "\\" in source or "/*" in source


def _comment_reads_two_ways(source: str, start: int, end: int, rules: LexRules) -> bool:
    if source.startswith("/*", start):
        # The safety cut also covers nested-comment text on the MySQL family (spec §14, D7).
        if rules.nested_comments is Reading.CUT and source.find("/*", start + 2, end) >= 0:
            return True
        # Executable comments may run quotes or names that the scan treats as inert.
        return source.startswith(tuple(rules.executable_prefixes), start)
    return False  # a line comment reads one way on each known dialect: each read knows where it ends


def _backslash_reads_two_ways(scan: _Pass, rules: LexRules) -> bool:
    """Ported from ``isAmbiguous``. The text without its backslashes is the one derived text the scan reads (spec §3,
    r4)."""
    source = scan.source
    if "\\" not in source:
        return False
    if rules.backslash_in_single is Backslash.E_ONLY:
        return _read(source, _escaping_single(rules)).out.text() != scan.out.text()
    return _read(_without_backslashes(scan), rules).out.text() != scan.out.text()


def _escaping_single(rules: LexRules) -> LexRules:
    """``rules`` with a backslash escaping in every single-quoted string, typed as the class ``_read`` takes."""
    return cast(LexRules, replace(rules, backslash_in_single=Backslash.ALWAYS))  # pyright: ignore[reportUnnecessaryCast]


def _without_backslashes(scan: _Pass) -> str:
    """The source with its backslashes removed, but those inside a closed backtick name: a backtick name takes no
    escape on any reading, so its ``\\`` changes the name's text and never where a run ends."""
    source = scan.source
    parts: list[str] = []
    cursor = 0
    for start, end, kind in scan.out.runs:
        if kind == _CODE and source[start] == "`" and end - start > 1 and source[end - 1] == "`":
            parts += (source[cursor:start].replace("\\", ""), source[start:end])
            cursor = end
    parts.append(source[cursor:].replace("\\", ""))
    return "".join(parts)


def _reads_two_ways(scan: _Pass, rules: LexRules) -> bool:
    source, runs = scan.source, scan.out.runs
    # Task 18's SQLite wiring makes this gate reachable and owes a test.
    if (
        rules.cut_bracket
        and "[" in source
        and any(kind == _LITERAL and source[start] == "[" for start, _, kind in runs)
    ):
        return True
    if not _holds_a_trigger(source):
        return False
    if any(_comment_reads_two_ways(source, start, end, rules) for start, end, kind in runs if kind == _COMMENT):
        return True
    return rules.cut_backslash and _backslash_reads_two_ways(scan, rules)


def _bracket_opener(scan: _Pass) -> re.Match[str] | None:
    """The first opener of the first bracket that reads two ways: past it a dollar quote or a comment is read apart."""
    source = scan.source
    for start, end, kind in scan.out.runs:
        if kind == _LITERAL and source[start] == "[":
            return _OPENER.search(source, start, end)
    return None


def _bad_exponent_cut(scan: _Pass) -> int:
    """The end of a real that MySQL's lexer leaves past a byte it ate; -1 when none."""
    source = scan.source
    literals = [(start, end) for start, end, kind in scan.out.runs if kind == _LITERAL]
    ends = {
        end
        for start, end in literals
        if _real_number(source, start, end) or source[end : end + 1] in "eE" and _real_number(source, start, end + 1)
    }
    found = [match.end() for match in _BAD_EXPONENT.finditer(source) if match.end() in ends]
    return min(found, default=-1)


def _bracket_cut(scan: _Pass) -> int:
    source = scan.source
    literals = iter((start, end) for start, end, kind in scan.out.runs if kind == _LITERAL)
    literal = next(literals, None)
    openings: list[int] = []
    index = 0
    while index < len(source):
        if literal and literal[0] <= index < literal[1]:
            index = literal[1]
            literal = next(literals, None)
        elif source.startswith("]]", index):
            if openings:
                return openings[0]
            index += 2
        else:
            if source[index] == "[":
                openings.append(index)
            elif source[index] == "]" and openings:
                openings.pop()
            index += 1
    return -1


def _ambiguous_cut(scan: _Pass, rules: LexRules) -> int:
    """Where a statement that reads two ways stops, its first opener; -1 when it reads one way or holds none.

    An opener is one of ``_RUN_OPENER``, or what opened a run left open in a bracket.

    Ported from ``JournalTextExposure.isAmbiguous``, which runs on the journal; here a trigger inside a literal is text
    (MVP spec §14), and the nested and backslash checks also run on MySQL (decision D7).
    """
    if not _reads_two_ways(scan, rules):
        return -1
    found = _RUN_OPENER.search(scan.source)
    return min((stop.start() for stop in (found, _bracket_opener(scan)) if stop), default=-1)


def _statement_cut(scan: _Pass, rule_sets: tuple[LexRules, ...]) -> int:
    """Where the statement stops: the first reading's own cuts, read whatever any other test says, then the first run
    a later reading places apart. A run that swallowed the rest of the text hides that the rest reads apart, so the
    head that shows is read again without it."""
    source, rules = scan.source, rule_sets[0]
    bracket = _bracket_cut(scan) if rules.bracket is Bracket.CHARACTER and rules.cut_bracket else -1
    cuts = [
        _ambiguous_cut(scan, rules),
        bracket,
        *(source.find(prefix) for prefix in rules.cut_prefixes),
    ]
    if rules.digit_dollar is DigitDollar.NAME:
        literals = [(start, end) for start, end, kind in scan.out.runs if kind == _LITERAL]
        cuts.extend((_bad_exponent_cut(scan), _uncertain_number_cut(source, literals)))
    executable = (other for other in rule_sets[1:] if other.executable_prefixes != rules.executable_prefixes)
    cuts += [
        _ambiguous_cut(scan, other)
        for other in executable
        if any(prefix in source for prefix in other.executable_prefixes - rules.executable_prefixes)
    ]
    parting = parting_readings(source, rule_sets)
    cuts += [family_cut(scan, _read(source, other), _LITERAL) for other in parting]
    cut = min((at for at in cuts if at >= 0), default=-1)
    if cut < 0 or not parting:
        return cut
    shown = _read(source[:cut], rules)
    parted = (family_cut(shown, _read(source[:cut], other), _LITERAL) for other in parting)
    return min((at for at in parted if at >= 0), default=cut)


def read_all(sql: str, rule_sets: tuple[LexRules, ...]) -> Scan:
    """The read of a tuple of rule sets: the output is the first's, cut where any of them stops."""
    source = sql[:_MAX_SCAN_LENGTH]
    rules = rule_sets[0]
    scan = _read(source, rules)
    cut = _statement_cut(scan, rule_sets)
    if scan.cut >= 0 and (cut < 0 or scan.cut < cut):
        cut = scan.cut
    uncut = tuple(scan.out.runs)
    if cut < 0:
        return Scan(
            source,
            scan.out.text(),
            uncut,
            scan.literals,
            scan.predicate_literals,
            -1,
            uncut,
            tuple(scan.out.marks),
            rules.hide_double_quoted,
        )
    head = _read(source[:cut], rules)
    out = head.out
    out.space()
    literals, predicate_literals = head.literals, head.predicate_literals
    out.runs.append((cut, cut, _COMMENT))  # the space, so that ``shown`` replays it
    predicate_literals += out.predicate_position()
    out.append("?")
    out.runs.append((cut, len(source), _LITERAL))
    literals += 1
    return Scan(
        source,
        out.text(),
        tuple(out.runs),
        literals,
        predicate_literals,
        cut,
        uncut,
        tuple(out.marks),
        rules.hide_double_quoted,
    )


class HandLexer:
    """The scan by hand, one pass over the text; the only ``SqlLexer`` there is. ``readings`` names the rules."""

    def scan(self, sql: str, dialect: Dialect) -> Scan:
        return read_all(sql, readings(dialect))

    def block_closer(self, text: str, dialect: Dialect) -> int:
        """Where the ``]`` closing a ``[SQL: `` block is in ``text``, the text after its opener; -1 when none does.

        The first ``]`` outside a literal, at bracket depth 0, in the scanned range, that ends the text or comes
        before what SQLAlchemy writes next (spec §3). One walk: literals and brackets both ascend. A line comment and
        an unclosed block comment are read, so that the ``]`` of ``-- arr[1]]`` counts; a closed ``/* ... */`` is
        skipped as a literal is: what it holds cannot end the block. No ambiguity cut: parameters are no statement, so
        what they hold cannot cut one.
        """
        return _first_closer(_read(text[:_MAX_SCAN_LENGTH], readings(dialect)[0]), text)

    def reads_two_ways(self, sql: str, dialect: Dialect) -> bool:
        """Whether ``sql`` stops at its first opener: a closer found in such a statement is a guess."""
        rule_sets = readings(dialect)
        scan = _read(sql[:_MAX_SCAN_LENGTH], rule_sets[0])
        # shortcut: SQLite alone, Task 18 changes no other dialect; PostgreSQL's boundary cut needs this line too
        variable_cut = rule_sets[0].variable_suffix is VariableSuffix.TCL_PAREN and scan.cut >= 0
        return variable_cut or _statement_cut(scan, rule_sets) >= 0


def _closed_block_comment(source: str, start: int, end: int) -> bool:
    """A ``/* ... */`` run ending in its own ``*/``: what it holds is no closer. A line or unclosed comment can be."""
    return end - start >= 4 and source.startswith("/*", start) and source.startswith("*/", end - 2)


def _first_closer(scan: _Pass, text: str) -> int:
    source = scan.source
    literals = (
        run
        for run in scan.out.runs
        if run[2] == _LITERAL or (run[2] == _COMMENT and _closed_block_comment(source, run[0], run[1]))
    )
    literal = next(literals, None)
    depth = 0
    for found in _BRACKET_STOP.finditer(scan.source):
        at = found.start()
        while literal is not None and literal[1] <= at:
            literal = next(literals, None)
        if literal is not None and literal[0] <= at:
            continue
        if found[0] == "[":
            depth += 1
        elif depth:
            depth -= 1
        elif _BLOCK_FOLLOWS.match(text, at + 1):
            return at
    return -1
