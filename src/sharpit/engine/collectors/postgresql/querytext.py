"""Catalog query text as the panel shows it: literals masked, secrets masked, whitespace collapsed, 400-char cut.

Port of BootUI ``PostgresQuery.queryText``. ``normalize_sql`` (SQL Trace) is not used: it turns literals into ``?``,
whereas BootUI shows ``'******'`` / ``$$******$$`` and the raw text under ``FULL``.
"""

from __future__ import annotations

import re

from sharpit.engine.masking import MASK, Masker

MAX_QUERY_TEXT_LENGTH = 400

# One pass, so whichever literal starts first wins (a ``$`` inside a string is not a dollar quote and vice versa).
# An unterminated literal runs to the end of the text: pg_stat_activity cuts query text mid-literal.
_LITERAL = re.compile(
    r"(?P<dollar>\$(?P<tag>[A-Za-z_][A-Za-z0-9_]*|)\$.*?(?:\$(?P=tag)\$|\Z))"
    r"|(?<![A-Za-z0-9_$])[eE]'(?:[^'\\]|''|\\.)*(?:'|\Z)"
    r"|'(?:[^']|'')*(?:'|\Z)",
    re.DOTALL,
)
_WHITESPACE = re.compile(r"\s+")


def _mask_literal(m: re.Match[str]) -> str:
    return f"$${MASK}$$" if m.group("dollar") else f"'{MASK}'"


def is_metadata_only(masker: Masker) -> bool:
    """``METADATA_ONLY``: no value of any kind is shown (``mask_text`` returns ``None`` only then)."""
    return masker.mask_text("") is None


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
    if is_metadata_only(masker):  # the text exists but is withheld
        return MASK
    masked = masker.mask_text(sql) or MASK
    # literals are values: masked exactly when the masker masks a secret value (not under FULL or mask-secrets off)
    if masker.mask("password", "x")[1]:
        masked = masker.mask_text(_LITERAL.sub(_mask_literal, sql)) or MASK
    return truncate(masked, max_length)
