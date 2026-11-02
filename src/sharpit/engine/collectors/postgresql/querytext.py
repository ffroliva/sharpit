"""PostgreSQL SQL query text sanitisation, literal masking and truncation."""

from __future__ import annotations

import re

from sharpit.engine.masking import MASK, Masker

MAX_QUERY_TEXT_LENGTH = 400

_DOLLAR_QUOTED_LITERAL = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*|)\$.*?(?:\$\1\$|\Z)", re.DOTALL)
_STRING_LITERAL = re.compile(
    r"(?<![A-Za-z0-9_$])[eE]'(?:[^'\\]|''|\\.)*(?:'|\Z)|'(?:[^']|'')*(?:'|\Z)",
    re.DOTALL,
)
_WHITESPACE = re.compile(r"\s+")


def truncate(value: str | None, max_length: int = MAX_QUERY_TEXT_LENGTH) -> str | None:
    if value is None or not value.strip():
        return None
    collapsed = _WHITESPACE.sub(" ", value).strip()
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max(1, max_length)] + "..."


def query_text(masker: Masker, sql: str | None, max_length: int = MAX_QUERY_TEXT_LENGTH) -> str | None:
    if sql is None or not sql.strip():
        return None
    _, metadata_only = masker.mask_value("x", "probe")
    if metadata_only:
        return MASK
    sanitized = sql
    _, mask_secrets = masker.mask_value("password", "probe")
    if mask_secrets:
        sanitized = _DOLLAR_QUOTED_LITERAL.sub(f"$${MASK}$$", sanitized)
        sanitized = _STRING_LITERAL.sub(f"'{MASK}'", sanitized)
        sanitized = masker.mask_text(sanitized) or sanitized
    return truncate(sanitized, max_length)
