"""Compatibility names for the SQL text facade."""

from __future__ import annotations

from sharpit.engine import sqltext
from sharpit.engine.capture.sqlscan import Normalized, Reading, read_statement
from sharpit.engine.masking import Masker
from sharpit.engine.sqltext import Dialect, fingerprint


def statement_text(masker: Masker, sql: str, dialect: Dialect, reading: Reading | None = None) -> str | None:
    del reading
    return sqltext.statement_text(masker, sql, dialect)


def masked_shape(masker: Masker, sql: str, dialect: Dialect) -> Normalized:
    """The scan's shape of ``sql`` with ``statement_text`` as its text and, lower-cased, as its fingerprint.

    A fingerprint built before the masker keeps a secret in code, and lower-casing hides a vendor token from a later
    pass. Under ``METADATA_ONLY``, which gives no text, the scan's shape stands.
    """
    reading = read_statement(sql, dialect)
    text = statement_text(masker, sql, dialect, reading)
    if dialect is Dialect.SQLITE:
        raw_fingerprint = read_statement(sql, Dialect.UNSUPPORTED).shape.fingerprint
        identity = fingerprint(raw_fingerprint, masker.identity_key) if raw_fingerprint is not None else None
    else:
        identity = text.lower() if text is not None else reading.shape.fingerprint
    return reading.shape._replace(sql=reading.shape.sql if text is None else text, fingerprint=identity)
