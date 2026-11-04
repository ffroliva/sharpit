"""The SQL statement scanner (``SqlStatementNormalizer``, verbatim port), kept apart from the recorder that uses it."""

from __future__ import annotations

import functools
import re
from collections.abc import Sequence
from typing import NamedTuple

from sharpit.engine.masking import MASK, is_secret_value

_MAX_SCAN_LENGTH = 20_000
MYSQL_DIALECTS = ("mysql", "mariadb")
_MYSQL_RADIX_LITERAL = re.compile(r"0[xX][0-9a-fA-F]+|0[bB][01]+")
# a square-bracket identifier is a name, words and spaces only: anything else in brackets is a value and stays in the
# scan (``ARRAY['x']``, ``ARRAY [lower($$x$$)]``, ``[2024 sales]``, ``[it's]``); showing a value is the worse mistake
_BRACKET_IDENTIFIER = re.compile(r"\[[^\W\d][\w ]*\]")
# never hidden in code: the statement keeps its shape, and the last masker pass still sees ``password=`` in the render
_STRUCTURAL = frozenset('"`[],;()=<>')
# the runs a scan reads as one: replaced by ``?``, replaced by a space, and copied with their whitespace (a quoted name)
_LITERAL, _COMMENT, _VERBATIM = range(3)


class Normalized(NamedTuple):
    sql: str
    fingerprint: str
    literal_count: int
    predicate_literal_count: int


class Range(NamedTuple):
    """Raw positions of a literal or, when ``literal`` is false, of a comment."""

    start: int
    end: int
    literal: bool


class _Out:
    """The output builder; ``opens`` holds the unmatched ``(`` positions so the IN-list check is O(1), not a
    backward scan per literal (BootUI's scan is quadratic on a long list, too slow in Python)."""

    def __init__(self) -> None:
        self.chars: list[str] = []
        self.opens: list[int] = []
        self.runs: list[tuple[int, int, int]] = []  # (start, end, kind) in the raw text, in order

    def append(self, text: str) -> None:
        for c in text:
            if c == "(":
                self.opens.append(len(self.chars))
            elif c == ")" and self.opens:
                self.opens.pop()
            self.chars.append(c)

    def space(self) -> None:
        if self.chars and self.chars[-1] != " ":
            self.chars.append(" ")

    def last_non_space(self) -> int:
        cursor = len(self.chars) - 1
        while cursor >= 0 and self.chars[cursor] == " ":
            cursor -= 1
        return cursor

    def ends_with_in_list(self) -> bool:
        """The innermost unmatched ``(`` is preceded by the keyword ``in`` (only called at the end of the output)."""
        if not self.opens:
            return False
        before = self.opens[-1] - 1
        while before >= 0 and self.chars[before] == " ":
            before -= 1
        return self.ends_with_keyword(before, "in")

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
        before = self.opens[-1] - 1
        while before >= 0 and self.chars[before] == " ":
            before -= 1
        if self.ends_with_keyword(before, "values"):
            return True
        if before < 0 or self.chars[before] != ",":
            return False
        before -= 1
        while before >= 0 and self.chars[before] == " ":
            before -= 1
        return before >= 0 and self.chars[before] == ")"

    def text(self) -> str:
        return "".join(self.chars)


def _skip_quoted(sql: str, index: int, closing: str, mysql: bool = False) -> int:
    cursor, length = index + 1, len(sql)
    escaped_in = "'\"" if mysql else "'"
    while cursor < length:
        c = sql[cursor]
        if c == "\\" and closing in escaped_in and cursor + 1 < length:
            cursor += 2
            continue
        if c == closing:
            if cursor + 1 < length and sql[cursor + 1] == closing:
                cursor += 2
                continue
            return cursor + 1
        cursor += 1
    return length


def _dollar_quote_end(sql: str, index: int) -> int:
    cursor, length, body_start = index + 1, len(sql), -1
    while cursor < length:
        c = sql[cursor]
        if c == "$":
            body_start = cursor + 1
            break
        if not (c.isalpha() or c == "_" or (cursor > index + 1 and c.isdigit())):
            return -1
        cursor += 1
    if body_start < 0:
        return -1
    tag = sql[index:body_start]
    end = sql.find(tag, body_start)
    return -1 if end < 0 else end + len(tag)


def _identifier_like(sql: str, index: int, end: int) -> bool:
    start = index + 1
    stop = end - 1 if end > start and sql[end - 1] == '"' else end
    if stop <= start:
        return False
    return all((c.isascii() and c.isalnum()) or c in "_$." for c in sql[start:stop])


def _double_quoted_literal(sql: str, index: int, end: int, out: _Out, mysql: bool = False) -> bool:
    """sharpit deviation (0.4.0): MySQL reads ``"..."`` as a string, so an identifier-shaped run is a literal too in a
    value position (unless it qualifies a name, ``"b"."id"``) or when it looks like a secret; identifiers elsewhere
    stay readable. Text known to be MySQL's has every run a literal: ``ANSI_QUOTES`` only masks an identifier."""
    stop = end - 1 if end > index + 1 and sql[end - 1] == '"' else end
    if mysql or not _identifier_like(sql, index, end) or is_secret_value(sql[index + 1 : stop]):
        return True
    return out.value_position() and not sql.startswith(".", end)


def _matches_keyword(sql: str, index: int, keyword: str) -> bool:
    after = index + len(keyword)
    if after > len(sql) or sql[index:after].lower() != keyword:
        return False
    return after >= len(sql) or not (sql[after].isalnum() or sql[after] in "_$")


def _identifier_char_before(out: _Out) -> bool:
    return bool(out.chars) and (out.chars[-1].isalnum() or out.chars[-1] in "_$.")


def _quoted_end(sql: str, index: int, out: _Out, mysql: bool) -> int:
    """Where the run opened at ``index`` ends; ``[`` that opens no identifier ends at once, so the scan reads inside."""
    c = sql[index]
    if c != "[":
        return _skip_quoted(sql, index, c, mysql)
    # ``ARRAY[``, ``items[``, ``(ARRAY[1])[``, ``a[1][``, ``ARRAY [``; a space alone proves nothing: ``SELECT [col]``
    subscript = bool(out.chars) and (out.chars[-1].isalnum() or out.chars[-1] in "_$)]")
    subscript = subscript or out.ends_with_keyword(out.last_non_space(), "array")
    found = None if subscript else _BRACKET_IDENTIFIER.match(sql, index)
    return found.end() if found else index + 1


def _line_comment(sql: str, index: int, mysql: bool) -> bool:
    return sql.startswith("--", index) or (mysql and sql[index] == "#")


def _skip_exponent(sql: str, index: int) -> int:
    """Past the exponent whose ``e`` is at ``index``; at ``index`` when no digit follows: that ``e`` is a name."""
    cursor, length = index + 1, len(sql)
    if cursor < length and sql[cursor] in "+-":
        cursor += 1
    if cursor >= length or not sql[cursor].isdigit():
        return index
    while cursor < length and sql[cursor].isdigit():
        cursor += 1
    return cursor


def _skip_number(sql: str, index: int, mysql: bool = False) -> int:
    if mysql and (radix := _MYSQL_RADIX_LITERAL.match(sql, index)):
        return radix.end()
    cursor, length = index, len(sql)
    while cursor < length and (sql[cursor].isdigit() or sql[cursor] == "."):
        cursor += 1
    if cursor < length and sql[cursor] in "eE":
        return _skip_exponent(sql, cursor)
    return cursor


def _collapse_placeholder_lists(normalized: str) -> str:
    if "?" not in normalized:
        return normalized
    out = _Out()
    index, length = 0, len(normalized)
    while index < length:
        c = normalized[index]
        cursor = out.last_non_space()
        inside = cursor >= 0 and out.chars[cursor] in "(," and out.ends_with_in_list()
        if c != "?" or not inside:
            out.append(c)
            index += 1
            continue
        cursor = last_placeholder = index
        while True:
            following = cursor + 1
            while following < length and normalized[following] == " ":
                following += 1
            if following < length and normalized[following] == ",":
                following += 1
                while following < length and normalized[following] == " ":
                    following += 1
                if following < length and normalized[following] == "?":
                    cursor = last_placeholder = following
                    continue
            break
        out.append("?")
        index = last_placeholder + 1
    return out.text()


# A scanner reads the construct that may open at ``index`` and returns where the scan goes on and whether that construct
# was a literal. Only these first characters cost a Python call; none of them is a space or a digit.
_Scanned = tuple[int, bool]


def _keep(source: str, index: int, out: _Out) -> _Scanned:
    """The character opened nothing after all."""
    out.append(source[index])
    return index + 1, False


def _scan_line_comment(source: str, index: int, out: _Out, mysql: bool) -> _Scanned:
    if not _line_comment(source, index, mysql):
        return _keep(source, index, out)
    out.space()
    newline = source.find("\n", index + 1)
    end = len(source) if newline < 0 else newline
    out.runs.append((index, end, _COMMENT))
    return end, False


def _scan_block_comment(source: str, index: int, out: _Out, _mysql: bool) -> _Scanned:
    if not source.startswith("*", index + 1):
        return _keep(source, index, out)
    out.space()
    close = source.find("*/", index + 2)
    end = len(source) if close < 0 else close + 2
    out.runs.append((index, end, _COMMENT))
    return end, False


def _scan_string(source: str, index: int, _out: _Out, _mysql: bool) -> _Scanned:
    return _skip_quoted(source, index, "'"), True


def _scan_dollar(source: str, index: int, out: _Out, _mysql: bool) -> _Scanned:
    end = _dollar_quote_end(source, index)
    return (end, True) if end > 0 else _keep(source, index, out)


def _scan_quoted(source: str, index: int, out: _Out, mysql: bool) -> _Scanned:
    end = _quoted_end(source, index, out, mysql)
    if source[index] == '"' and _double_quoted_literal(source, index, end, out, mysql):
        return end, True
    out.append(source[index:end])
    out.runs.append((index, end, _VERBATIM))
    return end, False


def _scan_keyword(source: str, index: int, out: _Out, _mysql: bool) -> _Scanned:
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
    **dict.fromkeys('"`[', _scan_quoted),
    **dict.fromkeys("tTfF", _scan_keyword),
}


class _Scan(NamedTuple):
    source: str
    out: _Out  # built from raw text alone, so what is hidden later cannot change a decision the scan made
    literals: int
    predicate_literals: int


def _scan(sql: str, mysql: bool) -> _Scan:
    """The one read of a statement: ``normalize`` keeps its output, ``shown`` and ``scan_ranges`` its runs."""
    source = sql[:_MAX_SCAN_LENGTH]
    out = _Out()
    literals = predicate_literals = 0
    index, length = 0, len(source)
    while index < length:
        start = index
        c = source[index]
        scanner = _SCANNERS.get(c)
        literal = False
        if scanner is not None:
            index, literal = scanner(source, index, out, mysql)
        elif c.isspace():
            out.space()
            index += 1
        elif c.isdigit() and not _identifier_char_before(out):
            index, literal = _skip_number(source, index, mysql), True
        else:
            out.append(c)
            index += 1
        if literal:
            literals += 1
            predicate_literals += out.predicate_position()
            out.append("?")
            out.runs.append((start, index, _LITERAL))
    return _Scan(source, out, literals, predicate_literals)


def _finish(out: _Out) -> str:
    return _collapse_placeholder_lists(out.text().strip())


@functools.lru_cache(maxsize=1024)  # the same statements repeat: the scan runs once per distinct text
def normalize(sql: str, mysql: bool = False) -> Normalized:
    """Literals become ``?``, comments and whitespace runs one space, ``IN (?, ?)`` lists ``IN (?)``.

    ``mysql`` is for text known to be MySQL's: ``"..."`` is a string with backslash escapes, ``#`` starts a comment and
    ``0x``/``0b`` numbers are literals. Elsewhere those mean an identifier, an operator and (mostly) a syntax error.
    """
    if not sql or sql.isspace():
        return Normalized("", "", 0, 0)
    scan = _scan(sql, mysql)
    collapsed = _finish(scan.out)
    return Normalized(collapsed, collapsed.lower(), scan.literals, scan.predicate_literals)


def scan_ranges(sql: str, mysql: bool = False) -> list[Range]:
    """The literals and comments of ``sql``, in order, as the scan read them (``SqlStatementNormalizer.ranges``)."""
    return [Range(start, end, kind == _LITERAL) for start, end, kind in _scan(sql, mysql).out.runs if kind != _VERBATIM]


def _hidden_flags(hidden: Sequence[tuple[int, int]], length: int) -> bytearray:
    """One flag per character. Sorted first, so each character is written once however many spans overlap it."""
    flags, reach = bytearray(length), 0
    for start, end in sorted(hidden):
        first, last = max(start, reach), min(end, length)
        if first < last:
            flags[first:last] = b"\x01" * (last - first)
            reach = last
    return flags


def _copy(source: str, span: tuple[int, int], flags: bytearray, out: _Out, collapse: bool) -> None:
    """Code or a quoted name, character by character: a hidden run is one mask, whitespace is never a hit."""
    masked = False
    for index in range(*span):
        c = source[index]
        if c.isspace() and collapse:
            out.space()
            masked = False
        elif flags[index] and not c.isspace() and c not in _STRUCTURAL:
            if not masked:
                out.append(MASK)
            masked = True
        else:
            out.append(c)
            masked = False


def shown(sql: str, hidden: Sequence[tuple[int, int]], mysql: bool = False) -> str:
    """``sql`` as ``normalize`` shows it, with the ``hidden`` raw spans masked (ported from ``SqlSinkText.mask``).

    Each character is classified once, from the raw scan, and emitted from that alone, so a hidden ``=`` cannot change
    what the scan decided about the ``"x"`` after it. The output is never scanned. A hidden character in a literal or a
    comment needs nothing: neither is copied.
    """
    scan = _scan(sql, mysql)
    source, flags, out = scan.source, _hidden_flags(hidden, len(scan.source)), _Out()
    index = 0
    for start, end, kind in scan.out.runs:
        _copy(source, (index, start), flags, out, True)
        if kind == _LITERAL:
            out.append("?")
        elif kind == _COMMENT:
            out.space()
        else:
            _copy(source, (start, end), flags, out, False)
        index = end
    _copy(source, (index, len(source)), flags, out, True)
    return _finish(out)


def is_mysql(owner: object) -> bool:
    """Whether a connection, engine or execution context talks to MySQL or MariaDB (also behind a ``mysql://`` URL)."""
    return getattr(getattr(owner, "dialect", None), "name", None) in MYSQL_DIALECTS


def normalize_sql(sql: str, mysql: bool = False) -> str:
    return normalize(sql, mysql).sql
