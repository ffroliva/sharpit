"""Read SQL number and exponent tokens from raw text."""

from __future__ import annotations

import re
from collections.abc import Sequence

# one pattern per radix: their prefixes differ, so at most one matches, as the alternation they were did
_RADIX_LITERALS = (
    re.compile(r"0[xX]_?[0-9a-fA-F]+(?:_[0-9a-fA-F]+)*"),
    re.compile(r"0[bB]_?[01]+(?:_[01]+)*"),
    re.compile(r"0[oO]_?[0-7]+(?:_[0-7]+)*"),
)


def _radix_literal(sql: str, index: int) -> re.Match[str] | None:
    return next((found for pattern in _RADIX_LITERALS if (found := pattern.match(sql, index))), None)


def _digit_goes_on(sql: str, cursor: int) -> bool:
    return sql[cursor].isdigit() or (sql[cursor] == "_" and sql[cursor + 1 : cursor + 2].isdigit())


def _skip_exponent(sql: str, index: int, fail_unicode: bool = False) -> int:
    """Past the exponent whose ``e`` is at ``index``; at ``index`` when no digit follows: that ``e`` is a name."""
    cursor, length = index + 1, len(sql)
    if cursor < length and sql[cursor] in "+-":
        cursor += 1
    if cursor >= length:
        return index
    if fail_unicode:
        return _ascii_exponent_end(sql, index, cursor)
    if not sql[cursor].isdigit():
        return index
    while cursor < length and _digit_goes_on(sql, cursor):
        cursor += 1
    return cursor


def _ascii_exponent_end(sql: str, index: int, cursor: int) -> int:
    """Past the exponent digits at ``cursor``; at ``index``, the ``e``, when a non-ASCII digit is in them or next."""
    length = len(sql)
    if not "0" <= sql[cursor] <= "9":
        return index
    while cursor < length and _digit_goes_on(sql, cursor):
        if not sql[cursor].isascii():
            return index
        cursor += 1
    if cursor < length and not sql[cursor].isascii():
        return index
    return cursor


def skip_number(sql: str, index: int, name_part: bool = False, fail_unicode: bool = False) -> int:
    if sql[index] == "0" and (radix := _radix_literal(sql, index)):
        return radix.end()
    cursor, length = index, len(sql)
    while cursor < length and ((sql[cursor] == "." and not name_part) or _digit_goes_on(sql, cursor)):
        cursor += 1
    if cursor < length and sql[cursor] in "eE":
        return _skip_exponent(sql, cursor, fail_unicode)
    return cursor


def _unicode_number_cut(sql: str, runs: Sequence[tuple[int, int]]) -> int:
    quoted = tuple((start, end) for start, end in runs if sql[start : start + 1] in "'\"`$")
    quoted_index = 0
    for index, char in enumerate(sql):
        while quoted_index < len(quoted) and quoted[quoted_index][1] <= index:
            quoted_index += 1
        if quoted_index < len(quoted) and quoted[quoted_index][0] <= index:
            continue
        if (
            char.isdigit()
            and not char.isascii()
            and (
                sql[index + 1 : index + 2] in ("e", "E", ".")
                or sql[index - 1 : index] == "."
                or sql[index + 1 : index + 2].isdigit()
            )
        ):
            return index
    return -1


def _number_char(sql: str, index: int) -> bool:
    return sql[index].isdigit() or sql[index] in "._+-" or sql[index].isascii() and sql[index].isalnum()


def _ascii_number_end(sql: str, cursor: int) -> int:
    """Past the number characters from ``cursor``; ``-1`` at a non-ASCII one."""
    length = len(sql)
    while cursor < length and _number_char(sql, cursor):
        if not sql[cursor].isascii():
            return -1
        cursor += 1
    return cursor


def _number_run_cut(sql: str, start: int) -> int:
    first = sql[start : start + 1]
    if not (first.isdigit() or first == "." and sql[start + 1 : start + 2].isdigit()):
        return -1
    if not first.isascii():
        return start
    dot_start = start
    while dot_start and sql[dot_start - 1] == ".":
        dot_start -= 1
    if start - dot_start >= 2:
        return dot_start
    cursor, length = _ascii_number_end(sql, start + 1), len(sql)
    if cursor < 0:
        return start
    if cursor < length and not sql[cursor].isascii() or start and not sql[start - 1].isascii():
        return start
    return start if ".." in sql[start : min(length, cursor + 1)] else -1


def uncertain_number_cut(sql: str, runs: Sequence[tuple[int, int]]) -> int:
    """Return the start of a MySQL number whose boundary touches Unicode or a dot run."""
    cuts = [_unicode_number_cut(sql, runs)]
    for start, _ in runs:
        cut = _number_run_cut(sql, start)
        if cut >= 0:
            cuts.append(cut)
    return min((cut for cut in cuts if cut >= 0), default=-1)
