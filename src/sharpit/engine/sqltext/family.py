"""Reads that can part within the MySQL family or from session state."""

from __future__ import annotations

import functools
from collections.abc import Sequence
from dataclasses import replace
from itertools import zip_longest
from typing import Protocol

from sharpit.engine.sqltext.rules import Backslash, LexRules


class _Runs(Protocol):
    @property
    def runs(self) -> Sequence[tuple[int, int, object]]: ...


class _Pass(Protocol):
    @property
    def source(self) -> str: ...

    @property
    def out(self) -> _Runs: ...


def family_cut(first: _Pass, other: _Pass, literal_kind: object) -> int:
    """The first run two readings place apart: what precedes it reads alike, and what follows it may not."""
    end = (len(first.source), len(first.source), literal_kind)
    return next((min(a[0], b[0]) for a, b in zip_longest(first.out.runs, other.out.runs, fillvalue=end) if a != b), -1)


@functools.cache
def _session_readings(rules: LexRules) -> tuple[LexRules, LexRules]:
    """``rules`` under ``NO_BACKSLASH_ESCAPES`` and under ``ANSI_QUOTES``: session state no text reveals, so a statement
    those read apart stops there. Removing the backslashes is no stand-in: ``'\\'\\', 'x'`` reads alike without them."""
    no_double = replace(rules, backslash_in_double=Backslash.NONE)
    return replace(no_double, backslash_in_single=Backslash.NONE), no_double


def parting_readings(source: str, rule_sets: tuple[LexRules, ...]) -> tuple[LexRules, ...]:
    """The readings ``source`` can part from the first on; none for one rule set, and none for text with no ``$`` or
    ``\\``, which is what makes the second read pay only where the rule sets differ."""
    backslash = "\\" in source
    if len(rule_sets) == 1 or not (backslash or "$" in source):
        return ()
    session = tuple(r for rules in rule_sets for r in _session_readings(rules)) if backslash else ()
    return rule_sets[1:] + session
