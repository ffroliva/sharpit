"""MySQL statement text normalisation and masking: literals masked, whitespace collapsed, cut at 400 chars."""

from __future__ import annotations

import re

from sharpit.engine.capture.sqltrace import normalize_sql
from sharpit.engine.masking import MASK, Masker

MAX_QUERY_TEXT_LENGTH = 400
_WHITESPACE = re.compile(r"\s+")


def is_metadata_only(masker: Masker) -> bool:
    """METADATA_ONLY: no value of any kind is shown."""
    return masker.mask_text("") is None


def truncate(value: str | None, max_length: int = MAX_QUERY_TEXT_LENGTH) -> str | None:
    if value is None or not value.strip():
        return None
    collapsed = _WHITESPACE.sub(" ", value).strip()
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max(1, max_length)] + "..."


def mysql_query_text(masker: Masker, sql: str | None, max_length: int = MAX_QUERY_TEXT_LENGTH) -> str | None:
    if sql is None or not sql.strip():
        return None
    if is_metadata_only(masker):
        return MASK
    try:
        normalized = normalize_sql(sql, mysql=True)
    except Exception:
        normalized = _WHITESPACE.sub(" ", sql).strip()
    masked = masker.mask_text(normalized) or normalized
    return truncate(masked, max_length)
