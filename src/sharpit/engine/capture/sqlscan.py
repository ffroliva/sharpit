"""The SQL statement scanner's facade (``SqlStatementNormalizer``, deviations in MVP spec §14), apart from its recorder.

The lexer and the renderer live in ``sharpit.engine.sqltext`` and know no secret detector: this module hands the
renderer the one thing it lacks, whether the body of a ``"`` run is a secret. It forwards the old names until Task 30.
"""

from __future__ import annotations

import functools
from collections.abc import Sequence
from typing import NamedTuple

from sharpit.engine import sqltext
from sharpit.engine.masking import MASK, is_secret_value
from sharpit.engine.sqltext import Dialect, Scan


class Normalized(NamedTuple):
    sql: str
    fingerprint: str
    literal_count: int
    predicate_literal_count: int
    dialect: Dialect


class Range(NamedTuple):
    """Raw positions of a literal or, when ``literal`` is false, of a comment.

    A statement that reads two ways ends in a zero-length comment range at its cut, then a literal range to the end.
    """

    start: int
    end: int
    literal: bool


def block_closer(text: str, dialect: Dialect) -> int:
    return sqltext.LEXER.block_closer(text, dialect)


def reads_two_ways(sql: str, dialect: Dialect) -> bool:
    return sqltext.LEXER.reads_two_ways(sql, dialect)


def _is_secret_name(body: str) -> bool:
    """The detector the renderer lacks: a ``"`` run that looks like a secret is a value, not a name."""
    return is_secret_value(body)


def _scan(sql: str, dialect: Dialect) -> Scan:
    """The one entry to the lexer: ``normalize`` keeps its output, ``shown`` and ``scan_ranges`` its runs."""
    return sqltext.LEXER.scan(sql, dialect)


class Reading(NamedTuple):
    """One read of raw text: its shape, and what ``shown`` emits from."""

    shape: Normalized
    scan: Scan
    cuts: list[tuple[int, int]]
    secret: frozenset[int]  # the ``"`` runs the detector called a secret, decided once


def read_statement(sql: str, dialect: Dialect) -> Reading:
    """The one read of ``sql``: ``normalize`` keeps the shape, ``shown`` takes the rest, so neither scans again."""
    scan = _scan(sql, dialect)
    secret = sqltext.secrets(scan, _is_secret_name)
    text, literals, predicate_literals = sqltext.shape(scan, secret)
    collapsed, cuts = sqltext.collapse_placeholder_lists(text.strip(sqltext.SPACE_CHARS))
    shape_read = Normalized(collapsed, collapsed.lower(), literals, predicate_literals, dialect)
    return Reading(shape_read, scan, cuts, secret)


@functools.lru_cache(maxsize=1024)  # the same statements repeat: the scan runs once per distinct text and lexer
def _normalized(lexer: sqltext.SqlLexer, sql: str, dialect: Dialect) -> Normalized:
    return read_statement(sql, dialect).shape  # blank text too: the scan is what refuses a dialect that is not one


def normalize(sql: str, dialect: Dialect) -> Normalized:
    """Literals become ``?``, comments and whitespace runs one space, ``IN (?, ?)`` lists ``IN (?)``.

    ``Dialect.MYSQL_FAMILY`` is text known to be MySQL's: ``"..."`` is a string with backslash escapes, ``#`` starts a
    comment and ``--`` needs a space after it. Elsewhere those mean an identifier, an operator and a comment. A
    statement that reads two ways stops at its first opener (``Scan.cut``). The cache is keyed on the lexer, so swapping
    ``sqltext.LEXER`` cannot serve a reading the old one made.
    """
    return _normalized(sqltext.LEXER, sql, dialect)


def scan_ranges(sql: str, dialect: Dialect) -> list[Range]:
    """The literals and comments of ``sql``, in order, as the scan read them (``SqlStatementNormalizer.ranges``)."""
    scan = _scan(sql, dialect)
    secret = sqltext.secrets(scan, _is_secret_name)
    kinds = (sqltext.Kind.LITERAL, sqltext.Kind.COMMENT)
    return [
        Range(start, end, kind is sqltext.Kind.LITERAL or start in secret)
        for start, end, kind in scan.runs
        if kind in kinds or start in secret
    ]


def shown(sql: str, hidden: Sequence[tuple[int, int]], dialect: Dialect, reading: Reading | None = None) -> str:
    """``sql`` as ``normalize`` shows it, with the ``hidden`` raw spans masked (ported from ``SqlSinkText.mask``).

    ``reading`` is ``read_statement``'s, when the caller holds it.
    """
    reading = reading or read_statement(sql, dialect)
    return sqltext.shown(sql, reading.scan, hidden, MASK, reading.secret, reading.cuts)


def normalize_sql(sql: str, dialect: Dialect) -> str:
    return normalize(sql, dialect).sql
