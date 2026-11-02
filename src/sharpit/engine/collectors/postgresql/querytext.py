"""Catalog query text as the panel shows it: literals masked, secrets masked, whitespace collapsed, 400-char cut.

Port of BootUI ``PostgresQuery.queryText``. ``normalize_sql`` (SQL Trace) is not used: it turns literals into ``?``,
whereas BootUI shows ``'******'`` / ``$$******$$`` and the raw text under ``FULL``.
"""

from __future__ import annotations

import re

from sharpit.engine.masking import MASK, Masker

MAX_QUERY_TEXT_LENGTH = 400

# One left-to-right tokenizer, so whichever token starts first wins (a ``$`` inside a string is not a dollar quote, a
# digit inside an identifier is not a number). Stricter than BootUI (coordinator ruling, review finding 1): numbers and
# comments are masked too, because psycopg2 inlines real parameter values into the text pg_stat_activity shows.
# An unterminated literal runs to the end of the text: pg_stat_activity cuts query text mid-literal. A plain literal
# holding ``\'`` closes differently under standard_conforming_strings on and off, so it is masked to the end of line.
_TOKEN = re.compile(
    r"(?P<dollar>\$(?P<tag>[A-Za-z_][A-Za-z0-9_]*|)\$.*?(?:\$(?P=tag)\$|\Z))"
    r"|(?P<string>[eE]'(?:[^'\\]|''|\\.)*(?:'|\Z)"  # E'...': a backslash always escapes
    r"|'(?:[^'\\]|''|\\\\|\\[^'\\])*(?:'|\Z)"  # plain, closed the same way whatever the setting
    r"|'[^\n]*)"  # plain with an ambiguous \': masked to the end of the line
    r'|(?P<keep>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_$]*|\$\d+)'  # identifiers and $n placeholders
    r"|(?P<comment>--[^\n]*|/\*.*?(?:\*/|\Z))"
    r"|(?P<number>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)",
    re.DOTALL,
)
_WHITESPACE = re.compile(r"\s+")


def _mask_token(m: re.Match[str]) -> str:
    if m.group("dollar") is not None:
        return f"$${MASK}$$"
    if m.group("string") is not None:
        return f"'{MASK}'"
    if m.group("comment") is not None:
        return " "
    if m.group("number") is not None:
        before = m.string[: m.start()].rstrip()[-1:]
        # a lone digit right after a keyword (``SELECT 1``, ``LIMIT 5``) is not a value worth hiding
        return m.group() if len(m.group()) == 1 and before.isalpha() else MASK
    return m.group()


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
    # literals and comments are values: masked exactly when the masker masks a secret value (not FULL, not mask-off)
    if masker.mask("password", "x")[1]:
        masked = masker.mask_text(_TOKEN.sub(_mask_token, sql)) or MASK
    return truncate(masked, max_length)
