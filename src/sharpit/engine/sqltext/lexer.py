"""The SQL lexer: raw text to runs (``SqlStatementNormalizer``, deviations in MVP spec §14), apart from what shows.

It decides nothing about secrets and imports nothing of ``masking``: a ``"`` run it cannot place by shape is reported as
``Kind.DOUBLE_QUOTED`` and the renderer, handed the detector by the facade, decides it (predict C1).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum
from itertools import zip_longest
from typing import NamedTuple, Protocol

from sharpit.engine.sqltext.dialect import Dialect
from sharpit.engine.sqltext.rules import (
    GENERIC,
    READINGS,
    Backslash,
    BacktickRun,
    Bracket,
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
    """The rules a dialect reads with: the one place the lexer meets a ``Dialect`` member."""
    return (GENERIC,) if dialect is Dialect.UNSUPPORTED else READINGS[dialect]


def quoted_body(source: str, start: int, end: int) -> str:
    """The text inside the quotes of the ``"`` run at ``start``; a run left open has no closing quote."""
    return source[start + 1 : end - 1 if end > start + 1 and source[end - 1] == '"' else end]


_MAX_SCAN_LENGTH = 20_000
_RADIX_LITERAL = re.compile(r"0[xX]_?[0-9a-fA-F]+(?:_[0-9a-fA-F]+)*|0[bB]_?[01]+(?:_[01]+)*|0[oO]_?[0-7]+(?:_[0-7]+)*")
# a square-bracket identifier is a name, words and spaces only, no word led by a digit: anything else in brackets is a
# value and stays in the scan (``ARRAY['x']``, ``ARRAY [lower($$x$$)]``, ``[2024 sales]``, ``a [CASE WHEN x THEN 1]``);
# showing a value is the worse mistake
_BRACKET_IDENTIFIER = re.compile(r"\[[^\W\d]\w*(?: +[^\W\d]\w*)* *\]")
# a bracket's body also ends at the next ``[``, so bodies never overlap and a run of open brackets stays linear
_BRACKET_STOP = re.compile(r"[\[\]]")
_OPENER = re.compile("['\"`$#]|--|/\\*")  # what can open a run: a body without one reads one way and pays this search
_ALTERNATIVE_QUOTE = re.compile(r"(?<![\w$])n?q'", re.IGNORECASE)
_QUOTE = re.compile("['\"]")
# where a cut stops, every opener the scan knows: a new kind goes here. ``$1`` opens nothing, so a ``$`` counts only in
# a tag's shape, and a tag can start with a digit on MySQL. No comment: a cut there would take every ``/*!`` statement
_RUN_OPENER = re.compile("['\"`]|\\$[\\w\\x80-\\U0010ffff]*\\$")
_TIGHT_DASH_OPENER = re.compile(rf"{_RUN_OPENER.pattern}|/\*")
_AT_TOKEN = re.compile(r"@[\w.$\x80-\U0010ffff]+")
_AT_NUMBER = re.compile(r"[@.]\d")
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


def _double_quoted_literal(sql: str, index: int, end: int, out: Out, rules: LexRules) -> bool | None:
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


def _digit_goes_on(sql: str, cursor: int) -> bool:
    return sql[cursor].isdigit() or (sql[cursor] == "_" and sql[cursor + 1 : cursor + 2].isdigit())


def _skip_exponent(sql: str, index: int) -> int:
    """Past the exponent whose ``e`` is at ``index``; at ``index`` when no digit follows: that ``e`` is a name."""
    cursor, length = index + 1, len(sql)
    if cursor < length and sql[cursor] in "+-":
        cursor += 1
    if cursor >= length or not sql[cursor].isdigit():
        return index
    while cursor < length and _digit_goes_on(sql, cursor):
        cursor += 1
    return cursor


def _name_part(out: Out) -> bool:
    """Digits here are a part of a name: the ``.`` after them separates, ``rv.1.$$``."""
    return bool(out.chars) and out.chars[-1] == "."


def _skip_number(sql: str, index: int, name_part: bool = False) -> int:
    if sql[index] == "0" and (radix := _RADIX_LITERAL.match(sql, index)):
        return radix.end()
    cursor, length = index, len(sql)
    while cursor < length and ((sql[cursor] == "." and not name_part) or _digit_goes_on(sql, cursor)):
        cursor += 1
    if cursor < length and sql[cursor] in "eE":
        return _skip_exponent(sql, cursor)
    return cursor


# A scanner reads the construct that may open at ``index`` and returns where the scan goes on and whether that construct
# was a literal. Only these first characters cost a Python call; none of them is a space or a digit.
_Scanned = tuple[int, bool]


def _keep(source: str, index: int, out: Out) -> _Scanned:
    """The character opened nothing after all."""
    out.append(source[index])
    return index + 1, False


def _scan_tcl_variable(source: str, index: int, out: Out) -> _Scanned:
    """SQLite's variable: `$`, `@`, `:` or `#`, a name, `::` namespaces and a `(...)` suffix to `)` or an ASCII space
    (tokenize.c:509-538). It hides from the opener, where only a boundary in the source may precede a variable (a
    `$` goes on a name, and no reading here tells a name's character from the rest), and at a suffix that is left open
    or holds a quote: a reader that does not know the suffix opens a string there. A name with no variable keeps its
    characters: `a$`.
    """
    cursor, length = index + 1, len(source)
    n = 0
    suffix = False
    while cursor < length:
        c = source[cursor]
        if c.isalnum() or c == "_" or c == "$" or not c.isascii():
            n += 1
            cursor += 1
        elif c == "(":
            suffix = True
            break
        elif c == ":" and cursor + 1 < length and source[cursor + 1] == ":":
            cursor += 2
        else:
            break
    if n == 0:
        return _keep(source, index, out)
    if not _opens_a_token(source, index):
        return index, True
    if suffix:
        opening = cursor
        while cursor < length and source[cursor] not in _SPACE and source[cursor] != ")":
            cursor += 1
        if cursor == length or source[cursor] != ")":
            return index, True
        if "'" in source[opening:cursor] or '"' in source[opening:cursor]:
            return index, True
        cursor += 1
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


def _name_goes_on(source: str, index: int, out: Out, rules: LexRules) -> bool:
    """The output ends inside a name, so the ``$`` at ``index`` is part of it. A number goes on too: ``1$a$`` is a name
    on MySQL and a syntax error on PostgreSQL and SQLite. A ``.`` holds on MySQL only: 0.4.0 hid what follows ``t.$$``,
    so elsewhere the statement stops there (``_generic_trigger``), as it does at ``@$$``, a value on PostgreSQL.
    """
    last = out.chars[-1] if out.chars else " "
    number = last == "?" and source[index - 1].isalnum()  # a raw ``?`` is an operator, and a string ends in a quote
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


def _scan_dot(source: str, index: int, out: Out, _rules: LexRules) -> _Scanned:
    if _identifier_char_before(out) or not source[index + 1 : index + 2].isdigit():
        return _keep(source, index, out)
    return _skip_number(source, index), True


def _scan_at(source: str, index: int, out: Out, rules: LexRules) -> _Scanned:
    """MySQL's lexer reads what follows ``@`` as one token, a user variable or an account's host: nothing in it opens a
    run. A number in it hides all of it, so what a digit run hid before stays hidden. ``@@`` is two of these."""
    if rules.variable_suffix is VariableSuffix.TCL_PAREN:
        return _scan_tcl_variable(source, index, out)
    found = _AT_TOKEN.match(source, index)
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
    kind = _CODE
    if source[index] == '"':
        literal = _double_quoted_literal(source, index, end, out, rules)
        if literal:
            return end, True
        if literal is None:
            kind = _DOUBLE_QUOTED
            out.marks.append(Candidate(len(out.chars), out.predicate_position()))
    out.append(source[index:end])
    out.runs.append((index, end, kind))
    return end, False


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
    "$": _scan_dollar,
    ".": _scan_dot,
    "@": _scan_at,
    ":": _scan_colon,
    **dict.fromkeys('"`[', _scan_quoted),
    **dict.fromkeys("tTfF", _scan_keyword),
}
_NO_DOLLAR_SCANNERS = {c: scanner for c, scanner in _SCANNERS.items() if c != "$"}  # ``$`` is then a name's character


class _Pass(NamedTuple):
    source: str
    out: Out  # built from raw text alone, so what is hidden later cannot change a decision the scan made
    literals: int
    predicate_literals: int
    cut: int = -1


def _read(source: str, rules: LexRules, dollar: bool = True) -> _Pass:
    """``dollar`` off reads as MariaDB and MySQL before 8.1 do: no dollar quote, which is all they differ in here. A
    bracket's body keeps its own read: a dollar quote that opens in it reads two ways, and that cut comes first."""
    scanners = _SCANNERS if dollar else _NO_DOLLAR_SCANNERS
    out = Out()
    chars = out.chars
    literals = predicate_literals = 0
    cut = -1
    index, length = 0, len(source)
    while index < length:
        start = index
        c = source[index]
        scanner = scanners.get(c)
        literal = False
        if scanner is not None:
            index, literal = scanner(source, index, out, rules)
            if index == start:
                cut = start
                break
        # SQLite treats a BOM as IdChar inside a name and as whitespace at token start (tokenize.c:575-579, 636).
        elif rules.variable_suffix is VariableSuffix.TCL_PAREN and c == "\ufeff":
            if _identifier_char_before(out):
                chars.append(c)
            else:
                out.space()
            index += 1
        elif c in _SPACE:
            out.space()
            index += 1
        # after a ``.`` a digit starts a literal: ``THEN.5`` is a number, and no keyword list can tell it from ``t.5``
        elif c.isdigit() and (not _identifier_char_before(out) or out.chars[-1] == "."):
            index, literal = _skip_number(source, index, _name_part(out)), True
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
    """A statement with none of these reads one way, and pays only these tests. A lone CR needs a ``--`` to matter."""
    return (
        "\\" in source or "#" in source or "/*" in source or "--" in source or "q'" in source or "Q'" in source
        or "@$" in source or ".$" in source
    )  # fmt: skip


def _comment_reads_two_ways(source: str, start: int, end: int, rules: LexRules) -> bool:
    if source.startswith("/*", start):
        # The safety cut also covers nested-comment text on the MySQL family (spec §14, D7).
        if rules.nested_comments is Reading.CUT and source.find("/*", start + 2, end) >= 0:
            return True
        # Executable comments may run quotes or names that the scan treats as inert.
        return source.startswith(tuple(rules.executable_prefixes), start)
    # a lone CR ends it on PostgreSQL, not on MySQL or SQLite
    if rules.cr_ends_dash is Reading.CUT and "\r" in source[start:end].rstrip("\r"):
        return True
    # a ``--`` tight against text is two minus signs on MySQL, so what it holds opens a run there
    tight = not _dashes_end_in_space(source, start)
    return rules.dash_needs_space is Reading.CUT and tight and _TIGHT_DASH_OPENER.search(source, start, end) is not None


def _trigger_spans(source: str, runs: Sequence[Run]) -> list[tuple[int, int]]:
    """The raw text a ``#`` or a ``q`` counts in: all of it outside a literal (spec §3)."""
    spans: list[tuple[int, int]] = []
    index = 0
    for start, end, kind in runs:
        if kind == _LITERAL:
            spans.append((index, start))
            index = end
    spans.append((index, len(source)))
    return spans


def _opener_beside_dollar_quote(source: str, start: int, rules: LexRules) -> bool:
    """An opener in the body of the dollar quote at ``start`` or past its closer: with none, nothing can flip."""
    tag = source.index("$", start + 1) + 1 - start
    end = _dollar_quote_end(source, start, rules)
    return bool(_OPENER.search(source, start + tag, end - tag) or _OPENER.search(source, end))


def _generic_trigger(source: str, runs: Sequence[Run], rules: LexRules) -> bool:
    """A ``q'`` (the span's end takes in the quote that opens a literal), a ``#`` with an opener after it anywhere, a
    dollar quote after ``@``, a value on PostgreSQL and a name on MySQL, or one after ``.`` beside another opener, a
    syntax error on PostgreSQL and a name on MySQL."""
    last_opener = max((found.start() for found in _RUN_OPENER.finditer(source)), default=-1)
    for start, end in _trigger_spans(source, runs):
        if _ALTERNATIVE_QUOTE.search(source, start, end + 1):
            return True
        if 0 <= source.find("#", start, end) < last_opener:
            return True
        if source.startswith("@$", end - 1):
            return True
        if source.startswith(".$", end - 1) and _opener_beside_dollar_quote(source, end, rules):
            return True
    return False


def _backslash_reads_two_ways(scan: _Pass, rules: LexRules) -> bool:
    """Ported from ``isAmbiguous``. ``MySQL`` escapes in ``"..."`` and the generic scan does not, so such a run always
    counts there. The text without its backslashes is the one derived text the scan reads (spec §3, r4)."""
    source, runs = scan.source, scan.out.runs
    if "\\" not in source:
        return False
    no_escape = rules.backslash_in_double is Backslash.NONE
    if (
        no_escape
        and rules.double_quote is not DoubleQuote.NAME
        and any(source[start] == '"' and source.find("\\", start, end) >= 0 for start, end, _ in runs)
    ):
        return True
    if rules.backslash_in_single is Backslash.E_ONLY:
        return _read(source, replace(rules, backslash_in_single=Backslash.ALWAYS)).out.text() != scan.out.text()
    return _read(source.replace("\\", ""), rules).out.text() != scan.out.text()


def _backtick_reads_two_ways(source: str, runs: Sequence[Run]) -> bool:
    """A name on MySQL and SQLite, an operator on PostgreSQL after ``CREATE OPERATOR``: a quote in it opens a string,
    and left open, an odd count of backticks, it holds code there and is invalid on the other two."""
    if "`" not in source:
        return False
    return any(
        kind == _CODE and source[start] == "`"
        and (_QUOTE.search(source, start, end) or source.count("`", start, end) % 2)
        for start, end, kind in runs
    )  # fmt: skip


def _reads_two_ways(scan: _Pass, rules: LexRules) -> bool:
    source, runs = scan.source, scan.out.runs
    # Task 18's SQLite wiring makes this gate reachable and owes a test.
    if (
        rules.cut_bracket
        and "[" in source
        and any(kind == _LITERAL and source[start] == "[" for start, _, kind in runs)
    ):
        return True
    if rules.backtick_run is BacktickRun.NAME_OR_CUT and _backtick_reads_two_ways(source, runs):
        return True
    if not _holds_a_trigger(source):
        return False
    if any(_comment_reads_two_ways(source, start, end, rules) for start, end, kind in runs if kind == _COMMENT):
        return True
    if rules.cut_backslash and _backslash_reads_two_ways(scan, rules):
        return True
    # shortcut: one field gates all four of these triggers; Task 29 removes them with generic mode
    return rules.q_quote_cuts and _generic_trigger(source, runs, rules)  # on MySQL ``#`` is a comment


def _bracket_opener(scan: _Pass) -> re.Match[str] | None:
    """The first opener of the first bracket that reads two ways: past it a dollar quote or a comment is read apart."""
    source = scan.source
    for start, end, kind in scan.out.runs:
        if kind == _LITERAL and source[start] == "[":
            return _OPENER.search(source, start, end)
    return None


def _family_cut(scan: _Pass, rules: LexRules) -> int:
    """The first run the MySQL family's two reads place apart; -1 when a ``$`` opens no dollar quote on either."""
    source = scan.source
    if "$" not in source:
        return -1
    other = _read(source, rules, dollar=False).out.runs
    end = (len(source), len(source), _LITERAL)  # the read with fewer runs goes on to the end of the text
    return next((min(a[0], b[0]) for a, b in zip_longest(scan.out.runs, other, fillvalue=end) if a != b), -1)


def _ambiguous_cut(scan: _Pass, rules: LexRules) -> int:
    """Where a statement that reads two ways stops, its first opener; -1 when it reads one way or holds none.

    An opener is one of ``_RUN_OPENER``, or what opened a run left open in a bracket. On MySQL a statement that reads
    one way can still stop, where the family's reads part: never before that first opener, so the cuts need no merge.

    Ported from ``JournalTextExposure.isAmbiguous``, which runs on the journal; here a trigger inside a literal is text
    (MVP spec §14), and the nested and backslash checks also run on MySQL (decision D7).
    """
    if not _reads_two_ways(scan, rules):
        return _family_cut(scan, rules) if rules.dollar is DollarOpen.MYSQL_TAG else -1
    found = _RUN_OPENER.search(scan.source)
    return min((stop.start() for stop in (found, _bracket_opener(scan)) if stop), default=-1)


def _scan(sql: str, rules: LexRules) -> Scan:
    """The one entry to the read: the output, the runs, and where a statement that reads two ways stops."""
    source = sql[:_MAX_SCAN_LENGTH]
    scan = _read(source, rules)
    cut = _ambiguous_cut(scan, rules)
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
    out.runs.append((cut, cut, _COMMENT))  # the space, so that ``shown`` replays it
    predicate = out.predicate_position()
    out.append("?")
    out.runs.append((cut, len(source), _LITERAL))
    literals, predicate_literals = head.literals + 1, head.predicate_literals + predicate
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
        return _scan(sql, readings(dialect)[0])

    def block_closer(self, text: str, dialect: Dialect) -> int:
        """Where the ``]`` closing a ``[SQL: `` block is in ``text``, the text after its opener; -1 when none does.

        The first ``]`` outside a literal, at bracket depth 0, in the scanned range, that ends the text or comes
        before what SQLAlchemy writes next (spec §3). One walk: literals and brackets both ascend. A comment is read,
        so that the ``]`` of ``-- arr[1]]`` counts. No ambiguity cut: parameters are no statement, so what they hold
        cannot cut one.
        """
        return _first_closer(_read(text[:_MAX_SCAN_LENGTH], readings(dialect)[0]), text)

    def reads_two_ways(self, sql: str, dialect: Dialect) -> bool:
        """Whether ``sql`` stops at its first opener: a closer found in such a statement is a guess."""
        rules = readings(dialect)[0]
        scan = _read(sql[:_MAX_SCAN_LENGTH], rules)
        # shortcut: SQLite alone, Task 18 changes no other dialect; PostgreSQL's boundary cut needs this line too
        variable_cut = rules.variable_suffix is VariableSuffix.TCL_PAREN and scan.cut >= 0
        return variable_cut or _ambiguous_cut(scan, rules) >= 0


def _first_closer(scan: _Pass, text: str) -> int:
    literals = (run for run in scan.out.runs if run[2] == _LITERAL)
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
