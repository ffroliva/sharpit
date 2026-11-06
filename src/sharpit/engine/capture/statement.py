"""Compatibility names for the SQL text facade."""

from __future__ import annotations

from sharpit.engine import sqltext
from sharpit.engine.capture.sqlscan import Normalized, Reading
from sharpit.engine.masking import Masker
from sharpit.engine.sqltext import Dialect


def statement_text(masker: Masker, sql: str, dialect: Dialect, reading: Reading | None = None) -> str | None:
    del reading
    return sqltext.statement_text(masker, sql, dialect)


def masked_shape(masker: Masker, sql: str, dialect: Dialect) -> Normalized:
    """Build rendered text and its keyed identity through the SQL text facade."""
    shape = sqltext.statement_shape(masker, sql, dialect)
    return Normalized(shape.text, shape.fingerprint, shape.literal_count, shape.predicate_literal_count, shape.dialect)
