"""The SQL statement scanner (``SqlStatementNormalizer``, deviations in MVP spec §14), apart from its recorder."""

from __future__ import annotations

import functools
import re
from collections.abc import Sequence
from typing import NamedTuple

from sharpit.engine.masking import MASK, is_secret_value

_MAX_SCAN_LENGTH = 20_000
MYSQL_DIALECTS = ("mysql", "mariadb")
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
    """Raw positions of a literal or, when ``literal`` is false, of a comment.

    A statement that reads two ways ends in a zero-length comment range at its cut, then a literal range to the end.
    """

    start: int
    end: int
    literal: bool


class _Out:
    """The output builder; ``opens`` holds the unmatched ``(`` positions so the IN-list check is O(1), not a
    backward scan per literal (BootUI's scan is quadratic on a long list, too slow in Python). A quoted name keeps a run
    of spaces, the only run the output has: ``past_spaces`` holds where each such run began, so a look past it is O(1).
    """

    def __init__(self) -> None:
        self.chars: list[str] = []
        self.opens: list[int] = []
        self.past_spaces: dict[int, int] = {}  # a space after a space -> the last position before the run
        self.runs: list[tuple[int, int, int]] = []  # (start, end, kind) in the raw text, in order

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


def _mysql_closer(sql: str, tag: str, start: int) -> int:
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


def _dollar_quote_end(sql: str, index: int, mysql: bool) -> int:
    """Where the dollar quote at ``index`` ends, the end of the text when it is open; -1 when none opens there."""
    cursor, length, body_start = index + 1, len(sql), -1
    while cursor < length:
        c = sql[cursor]
        if c == "$":
            body_start = cursor + 1
            break
        # PostgreSQL's tag: any non-ASCII character counts, ``€`` too, though no Unicode class calls it a letter;
        # MySQL's may start with a digit: ``$1$ x $1$`` is a body 8.4.10 stores
        if not (c.isalpha() or c == "_" or not c.isascii() or (c.isdigit() and (mysql or cursor > index + 1))):
            return -1
        cursor += 1
    if body_start < 0:
        return -1
    tag = sql[index:body_start]
    end = _mysql_closer(sql, tag, body_start) if mysql else sql.find(tag, body_start)
    return length if end < 0 else end + len(tag)


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
    if mysql or end >= _MAX_SCAN_LENGTH:  # a run the scan limit cut open has no shape to read
        return True
    if not _identifier_like(sql, index, end) or is_secret_value(sql[index + 1 : stop]):
        return True
    return out.value_position() and not sql.startswith(".", end)


def _matches_keyword(sql: str, index: int, keyword: str) -> bool:
    after = index + len(keyword)
    if after > len(sql) or sql[index:after].lower() != keyword:
        return False
    return after >= len(sql) or not (sql[after].isalnum() or sql[after] in "_$")


def _identifier_char_before(out: _Out) -> bool:
    return bool(out.chars) and (out.chars[-1].isalnum() or out.chars[-1] in "_$.")


def _name_goes_on(source: str, index: int, out: _Out, mysql: bool) -> bool:
    """The output ends inside a name, so the ``$`` at ``index`` is part of it. A number goes on too: ``1$a$`` is a name
    on MySQL and a syntax error on PostgreSQL and SQLite. A ``.`` holds on MySQL only: 0.4.0 hid what follows ``t.$$``,
    so elsewhere the statement stops there (``_generic_trigger``), as it does at ``@$$``, a value on PostgreSQL.
    """
    last = out.chars[-1] if out.chars else " "
    number = last == "?" and source[index - 1].isalnum()  # a raw ``?`` is an operator, and a string ends in a quote
    return last.isalnum() or last in "_$" or not last.isascii() or number or (mysql and last == ".")


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


def _two_way_bracket_end(sql: str, index: int, mysql: bool) -> int:
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
    runs = _read(sql[index + 1 : end] + "]", mysql).out.runs
    if not runs or runs[-1][1] != end - index:
        return -1
    return end + 1 if stop and stop[0] == "]" else end


def _mysql_dashes(sql: str, index: int) -> bool:
    """MySQL's ``--`` opens a comment only before whitespace, a control character or the end of the text."""
    after = sql[index + 2 : index + 3]
    return not after or ord(after) <= 32 or ord(after) == 127


def _line_comment(sql: str, index: int, mysql: bool) -> bool:
    dashes = sql.startswith("--", index) and (not mysql or _mysql_dashes(sql, index))
    return dashes or (mysql and sql[index] == "#")


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


def _name_part(out: _Out) -> bool:
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


def _collapse_placeholder_lists(normalized: str) -> tuple[str, list[tuple[int, int]]]:
    """``normalized`` with each ``IN (?, ?)`` list folded, and what was cut, as positions in ``normalized``."""
    cuts: list[tuple[int, int]] = []
    if "?" not in normalized:
        return normalized, cuts
    out = _Out()
    index, length = 0, len(normalized)
    while index < length:
        c = normalized[index]
        if c != "?" or not out.inside_in_list():
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
        if last_placeholder > index:
            cuts.append((index + 1, last_placeholder + 1))
        index = last_placeholder + 1
    return out.text(), cuts


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


def _scan_dollar(source: str, index: int, out: _Out, mysql: bool) -> _Scanned:
    # ``SELECT`` refuses one on MySQL 8.4.10, but a routine body is one: where a token starts it opens in every mode
    end = -1 if _name_goes_on(source, index, out, mysql) else _dollar_quote_end(source, index, mysql)
    return (end, True) if end > 0 else _keep(source, index, out)


def _scan_dot(source: str, index: int, out: _Out, _mysql: bool) -> _Scanned:
    if _identifier_char_before(out) or not source[index + 1 : index + 2].isdigit():
        return _keep(source, index, out)
    return _skip_number(source, index), True


def _scan_at(source: str, index: int, out: _Out, mysql: bool) -> _Scanned:
    """MySQL's lexer reads what follows ``@`` as one token, a user variable or an account's host: nothing in it opens a
    run. A number in it hides all of it, so what a digit run hid before stays hidden. ``@@`` is two of these."""
    found = _AT_TOKEN.match(source, index)
    if not mysql or found is None:
        return _keep(source, index, out)
    if _AT_NUMBER.search(found[0]):
        return found.end(), True
    out.append(found[0])
    return found.end(), False


def _scan_quoted(source: str, index: int, out: _Out, mysql: bool) -> _Scanned:
    if source[index] == "[" and (two_way_end := _two_way_bracket_end(source, index, mysql)) > 0:
        return two_way_end, True
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
    ".": _scan_dot,
    "@": _scan_at,
    **dict.fromkeys('"`[', _scan_quoted),
    **dict.fromkeys("tTfF", _scan_keyword),
}


class _Scan(NamedTuple):
    source: str
    out: _Out  # built from raw text alone, so what is hidden later cannot change a decision the scan made
    literals: int
    predicate_literals: int


def _read(source: str, mysql: bool) -> _Scan:
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
        # after a ``.`` a digit starts a literal: ``THEN.5`` is a number, and no keyword list can tell it from ``t.5``
        elif c.isdigit() and (not _identifier_char_before(out) or out.chars[-1] == "."):
            index, literal = _skip_number(source, index, _name_part(out)), True
        else:
            out.append(c)
            index += 1
        if literal:
            literals += 1
            predicate_literals += out.predicate_position()
            out.append("?")
            out.runs.append((start, index, _LITERAL))
    return _Scan(source, out, literals, predicate_literals)


def _holds_a_trigger(source: str) -> bool:
    """A statement with none of these reads one way, and pays only these tests. A lone CR needs a ``--`` to matter."""
    return (
        "\\" in source or "#" in source or "/*" in source or "--" in source or "q'" in source or "Q'" in source
        or "@$" in source or ".$" in source
    )  # fmt: skip


def _comment_reads_two_ways(source: str, start: int, end: int, mysql: bool) -> bool:
    if source.startswith("/*", start):
        if source.find("/*", start + 2, end) >= 0:  # PostgreSQL nests, the scan closes at the first ``*/``
            return True
        # MySQL skips a comment or a name inside one, so it ends past the first ``*/``, and only MySQL knows where
        return source.startswith(_EXECUTABLE_COMMENT, start)
    if mysql:  # a line comment of known MySQL text ends at its newline
        return False
    if "\r" in source[start:end].rstrip("\r"):  # a lone CR ends it on PostgreSQL, not on MySQL or SQLite
        return True
    # a ``--`` tight against text is two minus signs on MySQL, so what it holds opens a run there
    return not _mysql_dashes(source, start) and _TIGHT_DASH_OPENER.search(source, start, end) is not None


def _trigger_spans(source: str, runs: list[tuple[int, int, int]]) -> list[tuple[int, int]]:
    """The raw text a ``#`` or a ``q`` counts in: all of it outside a literal (spec §3)."""
    spans: list[tuple[int, int]] = []
    index = 0
    for start, end, kind in runs:
        if kind == _LITERAL:
            spans.append((index, start))
            index = end
    spans.append((index, len(source)))
    return spans


def _opener_beside_dollar_quote(source: str, start: int) -> bool:
    """An opener in the body of the dollar quote at ``start`` or past its closer: with none, nothing can flip."""
    tag = source.index("$", start + 1) + 1 - start
    end = _dollar_quote_end(source, start, False)
    return bool(_OPENER.search(source, start + tag, end - tag) or _OPENER.search(source, end))


def _generic_trigger(source: str, runs: list[tuple[int, int, int]]) -> bool:
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
        if source.startswith(".$", end - 1) and _opener_beside_dollar_quote(source, end):
            return True
    return False


def _backslash_reads_two_ways(scan: _Scan, mysql: bool) -> bool:
    """Ported from ``isAmbiguous``. ``MySQL`` escapes in ``"..."`` and the generic scan does not, so such a run always
    counts there. The text without its backslashes is the one derived text the scan reads (spec §3, r4)."""
    source, runs = scan.source, scan.out.runs
    if "\\" not in source:
        return False
    if not mysql and any(source[start] == '"' and source.find("\\", start, end) >= 0 for start, end, _ in runs):
        return True
    return _read(source.replace("\\", ""), mysql).out.text() != scan.out.text()


def _backtick_reads_two_ways(source: str, runs: list[tuple[int, int, int]]) -> bool:
    """A name on MySQL and SQLite, an operator on PostgreSQL after ``CREATE OPERATOR``: a quote in it opens a string,
    and left open, an odd count of backticks, it holds code there and is invalid on the other two."""
    if "`" not in source:
        return False
    return any(
        kind == _VERBATIM and source[start] == "`"
        and (_QUOTE.search(source, start, end) or source.count("`", start, end) % 2)
        for start, end, kind in runs
    )  # fmt: skip


def _reads_two_ways(scan: _Scan, mysql: bool) -> bool:
    source, runs = scan.source, scan.out.runs
    if "[" in source and any(kind == _LITERAL and source[start] == "[" for start, _, kind in runs):
        return True
    if not mysql and _backtick_reads_two_ways(source, runs):
        return True
    if not _holds_a_trigger(source):
        return False
    if any(_comment_reads_two_ways(source, start, end, mysql) for start, end, kind in runs if kind == _COMMENT):
        return True
    if _backslash_reads_two_ways(scan, mysql):
        return True
    return not mysql and _generic_trigger(source, runs)  # on MySQL ``#`` is a comment and ``q'`` is nothing


def _bracket_opener(scan: _Scan) -> re.Match[str] | None:
    """The first opener of the first bracket that reads two ways: past it a dollar quote or a comment is read apart."""
    source = scan.source
    for start, end, kind in scan.out.runs:
        if kind == _LITERAL and source[start] == "[":
            return _OPENER.search(source, start, end)
    return None


def _ambiguous_cut(scan: _Scan, mysql: bool) -> int:
    """Where a statement that reads two ways stops, its first opener; -1 when it reads one way or holds none.

    An opener is one of ``_RUN_OPENER``, or what opened a run left open in a bracket.

    Ported from ``JournalTextExposure.isAmbiguous``, which runs on the journal; here a trigger inside a literal is text
    (MVP spec §14), and the nested and backslash checks also run on MySQL (decision D7).
    """
    if not _reads_two_ways(scan, mysql):
        return -1
    found = _RUN_OPENER.search(scan.source)
    return min((stop.start() for stop in (found, _bracket_opener(scan)) if stop), default=-1)


def _scan(sql: str, mysql: bool) -> _Scan:
    """The one entry to the read: ``normalize`` keeps its output, ``shown`` and ``scan_ranges`` its runs."""
    source = sql[:_MAX_SCAN_LENGTH]
    scan = _read(source, mysql)
    cut = _ambiguous_cut(scan, mysql)
    if cut < 0:
        return scan
    head = _read(source[:cut], mysql)
    out = head.out
    out.space()
    out.runs.append((cut, cut, _COMMENT))  # the space, so that ``shown`` replays it
    predicate = out.predicate_position()
    out.append("?")
    out.runs.append((cut, len(source), _LITERAL))
    return _Scan(source, out, head.literals + 1, head.predicate_literals + predicate)


@functools.lru_cache(maxsize=1024)  # the same statements repeat: the scan runs once per distinct text
def normalize(sql: str, mysql: bool = False) -> Normalized:
    """Literals become ``?``, comments and whitespace runs one space, ``IN (?, ?)`` lists ``IN (?)``.

    ``mysql`` is for text known to be MySQL's: ``"..."`` is a string with backslash escapes, ``#`` starts a comment and
    ``--`` needs a space after it. Elsewhere those mean an identifier, an operator and a comment. A statement that reads
    two ways stops at its first opener (``_ambiguous_cut``).
    """
    if not sql or sql.isspace():
        return Normalized("", "", 0, 0)
    scan = _scan(sql, mysql)
    collapsed, _ = _collapse_placeholder_lists(scan.out.text().strip())
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


def _space(pieces: list[str]) -> None:
    if pieces and pieces[-1] != " ":
        pieces.append(" ")


def _release_name(source: str, flags: bytearray, start: int, literal: int) -> None:
    """A hit running from ``name=`` into the literal at ``literal`` was one token to the masker, ``bio="sk_live_..."``:
    the literal hides the value, so the name stays. A hit that starts before the name, a url's ``?token=abc="v"``, stays
    whole: ``abc`` is its value. The masker's last read still sees a secret left in the name."""
    if flags[literal] and literal > start and source[literal - 1] == "=":
        cursor = literal - 2
        while cursor >= start and flags[cursor] and (source[cursor].isalnum() or source[cursor] in "_.-"):
            cursor -= 1
        if cursor < start or not flags[cursor]:
            flags[cursor + 1 : literal - 1] = bytes(literal - cursor - 2)


def _copy(source: str, span: tuple[int, int], flags: bytearray, pieces: list[str], collapse: bool) -> None:
    """Code or a quoted name, character by character: a hidden run is one mask, whitespace is never a hit."""
    masked = False
    for index in range(*span):
        c = source[index]
        if c.isspace() and collapse:
            _space(pieces)
            masked = False
        elif flags[index] and not c.isspace() and c not in _STRUCTURAL:
            pieces.append("" if masked else MASK)
            masked = True
        else:
            pieces.append(c)
            masked = False


def shown(sql: str, hidden: Sequence[tuple[int, int]], mysql: bool = False) -> str:
    """``sql`` as ``normalize`` shows it, with the ``hidden`` raw spans masked (ported from ``SqlSinkText.mask``).

    Each character is classified once, from the raw scan, and emitted from that alone, so a hidden ``=`` cannot change
    what the scan decided about the ``"x"`` after it. A hidden character in a literal or a comment needs nothing:
    neither is copied. ``pieces`` has one entry per character of the scan's output, so the scan's list cuts apply to it
    by position, and nothing reads what was emitted.
    """
    scan = _scan(sql, mysql)
    source, flags = scan.source, _hidden_flags(hidden, len(scan.source))
    pieces: list[str] = []
    index = 0
    for start, end, kind in scan.out.runs:
        if kind == _LITERAL and start < len(flags):
            _release_name(source, flags, index, start)
        _copy(source, (index, start), flags, pieces, True)
        if kind == _LITERAL:
            pieces.append("?")
        elif kind == _COMMENT:
            _space(pieces)
        else:
            _copy(source, (start, end), flags, pieces, False)
        index = end
    _copy(source, (index, len(source)), flags, pieces, True)
    kept: list[str] = []
    index = 0
    for start, end in _collapse_placeholder_lists(scan.out.text().strip())[1]:
        kept += pieces[index:start]
        index = end
    kept += pieces[index:]
    return "".join(kept).strip()


def is_mysql(owner: object) -> bool:
    """Whether a connection, engine or execution context talks to MySQL or MariaDB (also behind a ``mysql://`` URL)."""
    return getattr(getattr(owner, "dialect", None), "name", None) in MYSQL_DIALECTS


def normalize_sql(sql: str, mysql: bool = False) -> str:
    return normalize(sql, mysql).sql
