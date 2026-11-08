"""The renderer: what a scan shows (ported from ``SqlSinkText.mask``), and the shape ``normalize`` keeps.

It imports nothing of ``masking``: the facade hands it the mask and the predicate that tells a secret in a ``"`` run.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from sharpit.engine.sqltext.lexer import SPACE_CHARS, Kind, Out, Scan, quoted_body

_SPACE = frozenset(SPACE_CHARS)
_PLACEHOLDER_RUN = re.compile(r"\? *, *\?")  # what a folded list needs
# never hidden in code: the statement keeps its shape, and the last masker pass still sees ``password=`` in the render
_STRUCTURAL = frozenset('"`[],;()=<>')
_NAME_BOUNDARIES = frozenset(" \t\r\n,([{")


def secrets(scan: Scan, double_quoted: Callable[[str], bool]) -> frozenset[int]:
    """The start of each ``DOUBLE_QUOTED`` run that ``double_quoted`` calls a secret: the one place a body is asked
    about, so ``shape`` and ``shown`` cannot disagree. Such a run reads as the literal it would have been."""
    if not scan.candidates:
        return frozenset()
    if scan.hide_double_quoted:
        return frozenset(start for start, _, kind in scan.runs if kind is Kind.DOUBLE_QUOTED)
    source = scan.source
    return frozenset(
        start
        for start, end, kind in scan.runs
        if kind is Kind.DOUBLE_QUOTED and double_quoted(quoted_body(source, start, end))
    )


def shape(scan: Scan, secret: frozenset[int]) -> tuple[str, int, int]:
    """The scan's output, its literal count and its predicate-literal count, each run in ``secret`` read as a literal"""
    if not secret:
        return scan.text, scan.literals, scan.predicate_literals
    text, literals, predicates = scan.text, scan.literals, scan.predicate_literals
    found = [run for run in scan.runs if run[2] is Kind.DOUBLE_QUOTED]
    for (start, end, _), candidate in reversed(list(zip(found, scan.candidates, strict=True))):
        if start in secret:
            text = f"{text[: candidate.at]}?{text[candidate.at + end - start :]}"
            literals += 1
            predicates += candidate.predicate
    return text, literals, predicates


def collapse_placeholder_lists(normalized: str) -> tuple[str, list[tuple[int, int]]]:
    """``normalized`` with each ``IN (?, ?)`` list folded, and what was cut, as positions in ``normalized``."""
    cuts: list[tuple[int, int]] = []
    if _PLACEHOLDER_RUN.search(normalized) is None:
        return normalized, cuts
    out = Out()
    index, length = 0, len(normalized)
    while index < length:
        c = normalized[index]
        if c != "?" or not out.inside_in_list():
            out.append(c)
            index += 1
            continue
        last_placeholder = _last_placeholder(normalized, index)
        out.append("?")
        if last_placeholder > index:
            cuts.append((index + 1, last_placeholder + 1))
        index = last_placeholder + 1
    return out.text(), cuts


def _past_spaces(text: str, at: int) -> int:
    while at < len(text) and text[at] == " ":
        at += 1
    return at


def _last_placeholder(normalized: str, index: int) -> int:
    """The last ``?`` of the ``?, ?`` run whose first ``?`` is at ``index``."""
    length, cursor = len(normalized), index
    while True:
        following = _past_spaces(normalized, cursor + 1)
        if following >= length or normalized[following] != ",":
            return cursor
        following = _past_spaces(normalized, following + 1)
        if following >= length or normalized[following] != "?":
            return cursor
        cursor = following


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


def _release_name(source: str, flags: bytearray, start: int, literal: int, end: int) -> None:
    """A hit running from ``name=`` into the literal at ``literal`` was one token to the masker, ``bio="sk_live_..."``:
    the literal hides the value, so the name stays. Only a hit that is exactly ``name=`` and the literal ending at
    ``end`` releases its name: one that starts before the name, a url's ``?token=abc="v"``, or that joins another hidden
    run across whitespace, either side, stays whole: ``abc`` is its value. The masker's last read still sees a secret
    left in the name."""
    if flags[literal] and literal > start and source[literal - 1] == "=":
        cursor = literal - 2
        while cursor >= start and flags[cursor] and (source[cursor].isalnum() or source[cursor] in "_.-"):
            cursor -= 1
        # A prior value delimiter means the hit may be a value, so keep it hidden.
        name_start = cursor + 1
        boundary = (cursor < start and start == 0) or (
            cursor >= start and not flags[cursor] and source[cursor] in _NAME_BOUNDARIES
        )
        if boundary and not _touches(source, flags, cursor, -1) and not _touches(source, flags, end, 1):
            flags[name_start : literal - 1] = bytes(literal - cursor - 2)


def _touches(source: str, flags: bytearray, at: int, step: int) -> bool:
    """Whether a hidden character sits at ``at``, past any whitespace in the direction ``step``: a hit is the hidden
    runs joined across whitespace, so ``Bearer <name>="v"`` and ``<name>='v'=<url>`` are one hit, not a name."""
    while 0 <= at < len(source) and source[at] in _SPACE:
        at += step
    return 0 <= at < len(source) and bool(flags[at])


def _copy(source: str, span: tuple[int, int], flags: bytearray, pieces: list[str], collapse: bool, mask: str) -> None:
    """Code or a quoted name, character by character: a hidden run is one mask, whitespace is never a hit."""
    masked = False
    for index in range(*span):
        c = source[index]
        if c in _SPACE and collapse:
            _space(pieces)
            masked = False
        elif flags[index] and c not in _SPACE and c not in _STRUCTURAL:
            pieces.append("" if masked else mask)
            masked = True
        else:
            pieces.append(c)
            masked = False


def shown(
    sql: str,
    scan: Scan,
    hidden: Sequence[tuple[int, int]],
    mask: str,
    secret: frozenset[int],
    cuts: Sequence[tuple[int, int]],
) -> str:
    """``sql`` as ``normalize`` shows it, with the ``hidden`` raw spans masked (ported from ``SqlSinkText.mask``).

    Each character is classified once, from the raw scan, and emitted from that alone, so a hidden ``=`` cannot change
    what the scan decided about the ``"x"`` after it. A hidden character in a literal or a comment needs nothing:
    neither is copied. ``pieces`` has one entry per character of the scan's output, so ``cuts``, the placeholder lists
    folded in that output, apply to it by position, and nothing reads what was emitted. A ``DOUBLE_QUOTED`` run is
    decided by ``secret`` (``secrets``): in it, a literal, otherwise a name that is copied.
    """
    source = sql[: len(scan.source)]
    flags = _hidden_flags(hidden, len(source))
    pieces: list[str] = []
    index = 0
    for start, end, kind in scan.runs:
        if kind is Kind.DOUBLE_QUOTED:
            kind = Kind.LITERAL if start in secret else Kind.CODE
        if kind is Kind.LITERAL and start < len(flags):
            _release_name(source, flags, index, start, end)
        _copy(source, (index, start), flags, pieces, True, mask)
        if kind is Kind.LITERAL:
            pieces.append("?")
        elif kind is Kind.COMMENT:
            _space(pieces)
        else:
            _copy(source, (start, end), flags, pieces, False, mask)
        index = end
    _copy(source, (index, len(source)), flags, pieces, True, mask)
    kept: list[str] = []
    index = 0
    for start, end in cuts:
        kept += pieces[index:start]
        index = end
    kept += pieces[index:]
    return "".join(kept).strip(SPACE_CHARS)
