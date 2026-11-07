"""Read SQL number and exponent tokens from raw text."""

from __future__ import annotations

import re

_RADIX_LITERAL = re.compile(r"0[xX]_?[0-9a-fA-F]+(?:_[0-9a-fA-F]+)*|0[bB]_?[01]+(?:_[01]+)*|0[oO]_?[0-7]+(?:_[0-7]+)*")


def _digit_goes_on(sql: str, cursor: int) -> bool:
    return sql[cursor].isdigit() or (sql[cursor] == "_" and sql[cursor + 1 : cursor + 2].isdigit())


def _skip_exponent(sql: str, index: int, fail_unicode: bool = False) -> int:
    """Past the exponent whose ``e`` is at ``index``; at ``index`` when no digit follows: that ``e`` is a name."""
    cursor, length = index + 1, len(sql)
    if cursor < length and sql[cursor] in "+-":
        cursor += 1
    if cursor >= length:
        return index
    if not fail_unicode:
        if not sql[cursor].isdigit():
            return index
        while cursor < length and _digit_goes_on(sql, cursor):
            cursor += 1
        return cursor
    if not "0" <= sql[cursor] <= "9":
        return index
    while cursor < length and _digit_goes_on(sql, cursor):
        if not sql[cursor].isascii():
            return index
        cursor += 1
    if fail_unicode and cursor < length and not sql[cursor].isascii():
        return index
    return cursor


def skip_number(sql: str, index: int, name_part: bool = False, fail_unicode: bool = False) -> int:
    if sql[index] == "0" and (radix := _RADIX_LITERAL.match(sql, index)):
        return radix.end()
    cursor, length = index, len(sql)
    while cursor < length and ((sql[cursor] == "." and not name_part) or _digit_goes_on(sql, cursor)):
        cursor += 1
    if cursor < length and sql[cursor] in "eE":
        return _skip_exponent(sql, cursor, fail_unicode)
    return cursor
