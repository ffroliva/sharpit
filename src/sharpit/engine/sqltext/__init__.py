"""SQL text: dialect naming, lexing and rendering. Only this package imports its own internals."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from sharpit.engine.sqltext.constants import MASK, UNSUPPORTED_STATEMENT
from sharpit.engine.sqltext.dialect import (
    ChainReading,
    Dialect,
    DialectContext,
    DialectSource,
    dialect_of_name,
    exception_leaves,
    is_database_exception,
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


_TAIL_WORD = re.compile(r"\w")
_MASK_MARGIN = 4_096  # past the longest shape the masker reads whole: a JWT, a vendor token, a key and its value


def _hide_joined_tails(sql: str, spans: list[tuple[int, int]]) -> None:
    """A secret span also hides its contiguous tail; a closing bracket continues it when a token follows."""
    reach = 0
    for index, (start, end) in enumerate(spans):
        end = max(end, reach)
        while end < len(sql):
            char = sql[end]
            if char.isspace() or char == ",":
                break
            if char in ")]}" and not _TAIL_WORD.match(sql, end + 1):
                break
            end += 1
        spans[index] = (start, end)
        reach = end


def secret_spans(masker: Masker, sql: str) -> list[tuple[int, int]] | None:
    """The raw ``(start, end)`` runs a statement's secrets cover, each with its joined tail; ``None`` hides all."""
    spans = masker.mask_spans(sql, False)
    if spans is not None:
        _hide_joined_tails(sql, spans)
    return spans


def _masked_twin(masker: Masker) -> Masker:
    """``MASKED`` with ``masker``'s own token and key: what a ``METADATA_ONLY`` shape shows is never more (council)."""
    from sharpit.engine.masking import Exposure
    from sharpit.engine.masking import Masker as MaskerType

    token = masker._token  # pyright: ignore[reportPrivateUsage]
    return MaskerType(Exposure.MASKED, True, token, identity_key=masker.identity_key)


def _statement_text(
    masker: Masker,
    sql: str,
    scan: Scan,
    secret: frozenset[int] | None = None,
    normalized: str | None = None,
    cuts: list[tuple[int, int]] | None = None,
) -> str | None:
    from sharpit.engine.masking import is_secret_value

    # nothing past the scan is shown: the masker reads the scan and a margin, so a secret across the cut is whole
    relaxed = secret_spans(masker, sql[: len(scan.source) + _MASK_MARGIN])
    if relaxed is None:
        return None
    if secret is None:
        secret = secrets(scan, is_secret_value)
    if normalized is None or cuts is None:
        scanned, _, _ = shape(scan, secret)
        normalized, cuts = collapse_placeholder_lists(scanned.strip(SPACE_CHARS))
    # the surface says: this text is a statement, whatever its first word. The last pass over the raw text hides each
    # secret and its joined tail before the emit, so a literal that split a secret cannot show the secret's remainder
    rendered = normalized if not relaxed and sql.isascii() else shown(sql, scan, relaxed, MASK, secret, cuts)
    return masker.mask_statement(rendered)


def statement_text(masker: Masker, sql: str, dialect: Dialect) -> str | None:
    """A statement with inline values and secrets removed under the selected exposure policy."""
    try:
        if masker.mask_spans("") is None:
            return None
        if dialect is Dialect.UNSUPPORTED:  # after the None check: METADATA_ONLY gives nothing
            return UNSUPPORTED_STATEMENT
        return _statement_text(masker, sql, LEXER.scan(sql, dialect))
    except Exception:
        return MASK


def statement_shape(masker: Masker, sql: str, dialect: Dialect) -> Shape:
    """The emitted statement and its masked identity, counts and resolved dialect.

    An ``UNSUPPORTED`` statement is the marker with no identity, and never reaches the lexer. A shape that cannot be
    read degrades to the mask with no identity: it never raises into the host (safety rule 5).
    """
    if dialect is Dialect.UNSUPPORTED:
        return Shape(UNSUPPORTED_STATEMENT, None, dialect, 0, 0)
    try:
        return _shape(masker, sql, dialect)
    except Exception:
        return Shape(MASK, None, dialect, 0, 0)


def _shape(masker: Masker, sql: str, dialect: Dialect) -> Shape:
    from sharpit.engine.masking import is_secret_value

    scan = LEXER.scan(sql, dialect)
    secret = secrets(scan, is_secret_value)
    normalized, literals, predicates = shape(scan, secret)
    normalized, cuts = collapse_placeholder_lists(normalized.strip(SPACE_CHARS))
    try:
        text = _statement_text(masker, sql, scan, secret, normalized, cuts)
        if text is None:  # METADATA_ONLY: a shape shows what MASKED shows, never the scan's text with no masker pass
            text = _statement_text(_masked_twin(masker), sql, scan, secret, normalized, cuts)
    except Exception:
        text = MASK
    shown_text = MASK if text is None else text
    if dialect is Dialect.SQLITE:
        if masker.identity_key is None:
            identity = None
        else:
            identity_text, _, _ = shape(scan, frozenset())
            identity_text, _ = collapse_placeholder_lists(identity_text.strip(SPACE_CHARS))
            identity = fingerprint(identity_text.lower(), masker.identity_key)
    else:
        identity = shown_text.lower()
    return Shape(shown_text, identity, dialect, literals, predicates)


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
    "UNSUPPORTED_STATEMENT",
    "collapse_placeholder_lists",
    "dialect_of_name",
    "exception_leaves",
    "fingerprint",
    "is_database_exception",
    "load_key",
    "quoted_body",
    "read_chain",
    "resolve",
    "secret_spans",
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
