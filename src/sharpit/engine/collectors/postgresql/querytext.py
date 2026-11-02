"""PostgreSQL SQL query text sanitisation, literal masking and truncation."""

from __future__ import annotations

from sharpit.engine.masking import Masker

MAX_QUERY_TEXT_LENGTH = 400


def query_text(masker: Masker, sql: str | None, max_length: int = MAX_QUERY_TEXT_LENGTH) -> str | None:
    del masker, sql, max_length
    return ""


def truncate(value: str | None, max_length: int = MAX_QUERY_TEXT_LENGTH) -> str | None:
    del value, max_length
    return ""
