"""Compatibility names for the SQL text facade."""

from __future__ import annotations

from sharpit.engine import sqltext
from sharpit.engine.capture.sqlscan import Normalized, Reading, normalize
from sharpit.engine.masking import Masker
from sharpit.engine.sqltext import Dialect, fingerprint


def statement_text(masker: Masker, sql: str, dialect: Dialect, reading: Reading | None = None) -> str | None:
    del reading
    return sqltext.statement_text(masker, sql, dialect)


def masked_shape(masker: Masker, sql: str, dialect: Dialect) -> Normalized:
    """Build rendered text and identity from one scan; SQLite identities require the local key."""
    shape = sqltext.statement_shape(masker, sql, dialect)
    if dialect is Dialect.SQLITE:
        raw_fingerprint = normalize(sql, Dialect.UNSUPPORTED).fingerprint
        identity = fingerprint(raw_fingerprint, masker.identity_key) if raw_fingerprint is not None else None
    else:
        identity = shape.fingerprint
    return Normalized(shape.text, identity, shape.literal_count, shape.predicate_literal_count, shape.dialect)
