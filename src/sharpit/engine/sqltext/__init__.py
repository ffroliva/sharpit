"""SQL text: dialect naming, lexing and rendering. Only this package imports its own internals."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from sharpit.engine.sqltext.constants import MASK
from sharpit.engine.sqltext.dialect import (
    ChainReading,
    Dialect,
    DialectContext,
    DialectSource,
    dialect_of_name,
    exception_leaves,
    read_chain,
    resolve,
)
from sharpit.engine.sqltext.identity import fingerprint, load_key
from sharpit.engine.sqltext.lexer import (
    SPACE_CHARS,
    Candidate,
    HandLexer,
    Kind,
    Range,
    Scan,
    SqlLexer,
    quoted_body,
)
from sharpit.engine.sqltext.render import collapse_placeholder_lists, secrets, shape, shown

if TYPE_CHECKING:
    from sharpit.engine.masking import Masker

LEXER: SqlLexer = HandLexer()
"""The one lexer. The facade reads it at each call, so the contract suite and a test can swap it."""


class Shape(NamedTuple):
    text: str
    fingerprint: str | None
    dialect: Dialect
    literal_count: int
    predicate_literal_count: int


type ErrorSource = str | BaseException


_VERB = re.compile(
    r"[(\s]*(?:alter|analyze|attach|begin|binlog|call|change|checkpoint|clone|cluster|comment|commit|copy|create|deallocate"
    r"|declare|delete|desc|describe|detach|do|drop|exec|execute|explain|fetch|flush|grant|handler|insert|kill|listen"
    r"|load|lock|merge|notify|optimize|pragma|prepare|refresh|reindex|release|rename|replace|reset|resignal|revoke"
    r"|rollback|savepoint|select|set|show|signal|start|table|truncate|unlock|update|use|vacuum|values|with)"
    r"(?=[^\w$-]|$)",
    re.IGNORECASE,
)


def _statement_text(
    masker: Masker,
    sql: str,
    scan: Scan,
    secret: frozenset[int] | None = None,
    normalized: str | None = None,
    cuts: list[tuple[int, int]] | None = None,
) -> str | None:
    from sharpit.engine.masking import is_secret_value

    relaxed = masker.mask_spans(sql, False)
    if relaxed is None:
        return None
    # A value joined after a literal to a SQL @-variable stays part of the same hidden run.
    for _, end in tuple(relaxed):
        if end + 1 < len(sql) and sql[end] in "'\"" and sql[end + 1] == "@":
            tail = end + 2
            while tail < len(sql) and (sql[tail].isalnum() or sql[tail] in "_.-"):
                tail += 1
            if tail > end + 2:
                relaxed.append((end, tail))
    if secret is None:
        secret = secrets(scan, is_secret_value)
    if normalized is None or cuts is None:
        scanned, _, _ = shape(scan, secret)
        normalized, cuts = collapse_placeholder_lists(scanned.strip(SPACE_CHARS))
    rendered = normalized if not relaxed and sql.isascii() else shown(sql, scan, relaxed, MASK, secret, cuts)
    if _VERB.match(rendered):
        return masker.mask_statement(rendered)
    if relaxed or masker.mask_spans(sql, True):
        return MASK
    return masker.mask_text(rendered)


def statement_text(masker: Masker, sql: str, dialect: Dialect) -> str | None:
    """A statement with inline values and secrets removed under the selected exposure policy."""
    try:
        if masker.mask_spans("") is None:
            return None
        return _statement_text(masker, sql, LEXER.scan(sql, dialect))
    except Exception:
        return MASK


def statement_shape(masker: Masker, sql: str, dialect: Dialect) -> Shape:
    """The emitted statement and its masked identity, counts and resolved dialect."""
    from sharpit.engine.masking import is_secret_value

    scan = LEXER.scan(sql, dialect)
    secret = secrets(scan, is_secret_value)
    normalized, literals, predicates = shape(scan, secret)
    normalized, cuts = collapse_placeholder_lists(normalized.strip(SPACE_CHARS))
    try:
        text = _statement_text(masker, sql, scan, secret, normalized, cuts)
    except Exception:
        text = MASK
    shown_text = normalized if text is None else text
    return Shape(shown_text, shown_text.lower(), dialect, literals, predicates)


def error_text(
    masker: Masker, source: ErrorSource, dialect: Dialect, known: bool = False, keep_frames: bool = True
) -> str | None:
    """Render free text or a database exception through the same regions and exposure policy."""
    try:
        from sharpit.engine.sqltext.errors import error_text as render_error_text

        return render_error_text(masker, source, dialect, known, keep_frames)
    except Exception:
        return MASK


def mask_error(masker: Masker, text: str | None, dialect: Dialect, known: bool = False) -> str | None:
    from sharpit.engine.sqltext.errors import mask_error as render_error_text

    return render_error_text(masker, text, dialect, known)


def render_error(masker: Masker, text: str, dialect: Dialect, keep_frames: bool = True) -> str:
    from sharpit.engine.sqltext.errors import render_error as render_error_text

    return render_error_text(masker, text, dialect, keep_frames)


def log_statement(masker: Masker, text: str, dialect: Dialect) -> str | None:
    from sharpit.engine.sqltext.errors import log_statement as render_statement

    return render_statement(masker, text, dialect)


__all__ = [
    "LEXER",
    "MASK",
    "SPACE_CHARS",
    "Candidate",
    "ChainReading",
    "Dialect",
    "DialectContext",
    "DialectSource",
    "ErrorSource",
    "HandLexer",
    "Kind",
    "Range",
    "Scan",
    "Shape",
    "SqlLexer",
    "collapse_placeholder_lists",
    "dialect_of_name",
    "exception_leaves",
    "fingerprint",
    "load_key",
    "quoted_body",
    "read_chain",
    "resolve",
    "secrets",
    "statement_shape",
    "statement_text",
    "shape",
    "shown",
    "error_text",
    "log_statement",
    "mask_error",
    "render_error",
]
