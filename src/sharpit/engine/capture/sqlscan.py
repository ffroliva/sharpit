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

MYSQL_DIALECTS = ("mysql", "mariadb")


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


def _dialect(mysql: bool) -> Dialect:
    """What ``mysql: bool`` meant: MySQL's rules, or the generic ones that cut wherever two servers disagree."""
    return Dialect.MYSQL_FAMILY if mysql else Dialect.UNSUPPORTED


def block_closer(text: str, mysql: bool = False) -> int:
    return sqltext.block_closer(text, _dialect(mysql))


def reads_two_ways(sql: str, mysql: bool = False) -> bool:
    return sqltext.reads_two_ways(sql, _dialect(mysql))


def _is_secret_name(body: str) -> bool:
    """The detector the renderer lacks: a ``"`` run that looks like a secret is a value, not a name."""
    return is_secret_value(body)


def _scan(sql: str, mysql: bool) -> Scan:
    """The one entry to the lexer: ``normalize`` keeps its output, ``shown`` and ``scan_ranges`` its runs."""
    return sqltext.LEXER.scan(sql, _dialect(mysql))


class Reading(NamedTuple):
    """One read of raw text: its shape, and what ``shown`` emits from."""

    shape: Normalized
    scan: Scan
    cuts: list[tuple[int, int]]


def read_statement(sql: str, mysql: bool = False) -> Reading:
    """The one read of ``sql``: ``normalize`` keeps the shape, ``shown`` takes the rest, so neither scans again."""
    scan = _scan(sql, mysql)
    text, literals, predicate_literals = sqltext.shape(scan, _is_secret_name)
    collapsed, cuts = sqltext.collapse_placeholder_lists(text.strip(sqltext.SPACE_CHARS))
    return Reading(Normalized(collapsed, collapsed.lower(), literals, predicate_literals), scan, cuts)


@functools.lru_cache(maxsize=1024)  # the same statements repeat: the scan runs once per distinct text
def normalize(sql: str, mysql: bool = False) -> Normalized:
    """Literals become ``?``, comments and whitespace runs one space, ``IN (?, ?)`` lists ``IN (?)``.

    ``mysql`` is for text known to be MySQL's: ``"..."`` is a string with backslash escapes, ``#`` starts a comment and
    ``--`` needs a space after it. Elsewhere those mean an identifier, an operator and a comment. A statement that reads
    two ways stops at its first opener (``Scan.cut``).
    """
    if not sql.strip(sqltext.SPACE_CHARS):
        return Normalized("", "", 0, 0)
    return read_statement(sql, mysql).shape


def scan_ranges(sql: str, mysql: bool = False) -> list[Range]:
    """The literals and comments of ``sql``, in order, as the scan read them (``SqlStatementNormalizer.ranges``)."""
    scan = _scan(sql, mysql)
    kinds = (sqltext.Kind.LITERAL, sqltext.Kind.COMMENT, sqltext.Kind.DOUBLE_QUOTED)
    found: list[Range] = []
    for start, end, kind in scan.runs:
        if kind not in kinds:
            continue
        if kind is sqltext.Kind.DOUBLE_QUOTED:
            if not _is_secret_name(sqltext.quoted_body(scan.source, start, end)):
                continue
            kind = sqltext.Kind.LITERAL
        found.append(Range(start, end, kind is sqltext.Kind.LITERAL))
    return found


def shown(sql: str, hidden: Sequence[tuple[int, int]], mysql: bool = False, reading: Reading | None = None) -> str:
    """``sql`` as ``normalize`` shows it, with the ``hidden`` raw spans masked (ported from ``SqlSinkText.mask``).

    ``reading`` is ``read_statement``'s, when the caller holds it.
    """
    reading = reading or read_statement(sql, mysql)
    return sqltext.shown(sql, reading.scan, hidden, MASK, _is_secret_name, reading.cuts)


def is_mysql(owner: object) -> bool:
    """Whether a connection, engine or execution context talks to MySQL or MariaDB (also behind a ``mysql://`` URL)."""
    return getattr(getattr(owner, "dialect", None), "name", None) in MYSQL_DIALECTS


def normalize_sql(sql: str, mysql: bool = False) -> str:
    return normalize(sql, mysql).sql
