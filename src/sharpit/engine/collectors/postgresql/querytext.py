"""Catalog query text as the panel shows it: literals masked, secrets masked, whitespace collapsed, 400-char cut.

Port of BootUI ``PostgresQuery.queryText``. ``normalize_sql`` (SQL Trace) is not used: it turns literals into ``?``,
whereas BootUI shows ``'******'`` / ``$$******$$`` and the raw text under ``FULL``.
"""

from __future__ import annotations

import re

from sharpit.engine.masking import MASK, Masker, is_sensitive_key
from sharpit.engine.sqltext import Dialect, secret_spans, statement_text

MAX_QUERY_TEXT_LENGTH = 400

# One left-to-right tokenizer, so whichever token starts first wins (a ``$`` inside a string is not a dollar quote, a
# digit inside an identifier is not a number). Stricter than BootUI (coordinator ruling, review finding 1): numbers and
# comments are masked too, because psycopg2 inlines real parameter values into the text pg_stat_activity shows.
# An unterminated literal runs to the end of the text: pg_stat_activity cuts query text mid-literal. A plain literal
# holding ``\'`` closes differently under standard_conforming_strings on and off, so it may close on any later line:
# everything after it is masked.
_TOKEN = re.compile(
    r"(?P<dollar>\$(?P<tag>[A-Za-z_][A-Za-z0-9_]*|)\$.*?(?:\$(?P=tag)\$|\Z))"
    r"|(?P<string>[eE]'(?:[^'\\]|''|\\.)*(?:'|\Z)"  # E'...': a backslash always escapes
    r"|'(?:[^'\\]|''|\\\\|\\[^'\\])*(?:'|\Z)"  # plain, closed the same way whatever the setting
    r"|'.*)"  # plain with an ambiguous \': masked to the end of the text
    r"|(?P<number>0[xX][0-9A-Fa-f_]+|0[oO][0-7_]+|0[bB][01_]+"  # PostgreSQL 16 forms, masked whole
    r"|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d+)?)"
    r'|(?P<keep>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_$]*|\$\d+'  # identifiers and $n placeholders
    r"|[^\x00-\x7f]+\$+)"  # _NAME_DOLLARS: scan.l ident_cont, a ``$`` run ending a name after a non-ASCII char
    r"|(?P<comment>--[^\n]*|/\*)",  # a block comment's end is found by _comment_end: they nest
    re.DOTALL,
)
_PLAIN_NAME = re.compile(r'"[A-Za-z0-9_$.]+"')
_COMMENT_MARK = re.compile(r"/\*|\*/")
_WHITESPACE = re.compile(r"\s+", re.ASCII)
# _NAME_DOLLARS' other half: a ``$`` that reads two ways next to a non-ASCII name character (a name character before
# it, ``$tag$`` text after it, or a non-ASCII tag) still goes to the lexer, which cuts it; only a ``$`` run that ends
# the name after a non-ASCII character (``x<U+202F>$$,``) stays on this tokenizer
_TWO_WAY_DOLLAR = re.compile(
    r"[^\x00-\x7f][A-Za-z0-9_$\x80-\U0010ffff]*?(?:[A-Za-z0-9_]\$|\$[A-Za-z0-9_\x80-\U0010ffff])|\$[^\x00-\x7f]"
)
# a sensitive key's masked literal, which BootUI shows bare: ``password = ******``, not ``password = '******'``
_KEYED_LITERAL = re.compile(rf"(?<![\w.-])([\w.-]+)(\s*[=:]\s*)'{re.escape(MASK)}'", re.ASCII)


def _bare(m: re.Match[str]) -> str:
    return f"{m[1]}{m[2]}{MASK}" if is_sensitive_key(m[1]) else m[0]


def _comment_end(sql: str, start: int) -> int:
    """The index after the ``*/`` closing the (nested) block comment opened at ``start``; the end if unclosed."""
    depth = 0
    for mark in _COMMENT_MARK.finditer(sql, start):
        depth += 1 if mark.group() == "/*" else -1
        if depth == 0:
            return mark.end()
    return len(sql)


def _mask_all(sql: str, secret: list[tuple[int, int]] | None = None) -> str:
    """Literals, numbers and comments masked; what is kept (code, names) loses each raw ``secret`` span too."""
    out: list[str] = []
    spans = iter(secret or ())
    span = next(spans, None)

    def keep(start: int, end: int) -> None:
        nonlocal span
        while span is not None and span[1] <= start:
            span = next(spans, None)
        while span is not None and span[0] < end:
            if gap := sql[start : max(span[0], start)]:
                out.append(gap)
            if out[-1:] != [MASK]:  # one mask for a span cut by a masked token
                out.append(MASK)
            start = min(span[1], end)
            if span[1] > end:
                break
            span = next(spans, None)
        out.append(sql[start:end])

    pos = 0
    while (m := _TOKEN.search(sql, pos)) is not None:
        keep(pos, m.start())
        if m.group() == "/*":
            out.append(" ")
            pos = _comment_end(sql, m.start())
        elif (masked := _mask_token(m)) == m.group():
            keep(m.start(), m.end())
            pos = m.end()
        else:
            out.append(masked)
            pos = m.end()
    keep(pos, len(sql))
    return "".join(out)


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
    # spec A1: a ``"`` run no name would be spelled like hides here too, as the lexer hides it on every other surface
    if m.group().startswith('"') and not _PLAIN_NAME.fullmatch(m.group()):
        return f"'{MASK}'"
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
    if _TWO_WAY_DOLLAR.search(sql):
        return truncate(statement_text(masker, sql, Dialect.POSTGRESQL), max_length)
    masked = masker.mask_text(sql) or MASK
    # literals and comments are values: masked exactly when the masker masks a secret value (not FULL, not mask-off)
    if masker.mask("password", "x")[1]:
        # the raw text's secret spans, read before ``_mask_all`` masks a quoted key (``'pwd': v``) out of every pass.
        # The text is a statement, so its last pass is the statement's (MVP spec section 14): a sensitive key hides
        # one value and the clauses after it stay, as on every other statement surface
        spans = secret_spans(masker, sql)
        masked = (
            MASK if spans is None else _KEYED_LITERAL.sub(_bare, masker.mask_statement(_mask_all(sql, spans)) or MASK)
        )
    return truncate(masked, max_length)
