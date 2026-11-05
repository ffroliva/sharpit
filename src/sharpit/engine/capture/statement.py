"""One statement path: raw text read once, then rendered (spec §3). Apart from ``sqlscan``, which has no ``Masker``."""

from __future__ import annotations

import re

from sharpit.engine.capture.sqlscan import shown
from sharpit.engine.masking import MASK, Masker

# The words a statement starts with on PostgreSQL, MySQL or SQLite. A first word outside this list only hides more.
_VERB = re.compile(
    r"[(\s]*(?:alter|analyze|attach|begin|call|checkpoint|commit|copy|create|deallocate|declare|delete|desc|describe"
    r"|detach|do|drop|exec|execute|explain|fetch|flush|grant|handler|insert|kill|listen|load|lock|merge|notify|optimize"
    r"|pragma|prepare|refresh|reindex|release|rename|replace|reset|revoke|rollback|savepoint|select|set|show|start"
    r"|table|truncate|unlock|update|use|vacuum|values|with)(?=[\s(;]|$)",
    re.IGNORECASE,
)


def statement_text(masker: Masker, sql: str, mysql: bool = False) -> str | None:
    """``sql`` with its literals and secrets gone; ``None`` under ``METADATA_ONLY``, ``******`` if the render fails.

    Text that starts with no verb is no statement, though it reaches ``db.statement``: a hit there hides all of it,
    because a value's end is a guess and ``_mask_glued`` cannot read past a ``?`` the scan left beside a token. With
    no hit the raw text holds nothing the passes know, so what is left is the render, as at 0.4.0.
    """
    try:
        relaxed = masker.mask_spans(sql, False)
        if relaxed is None:
            return None
        render = shown(sql, relaxed, mysql)
        if _VERB.match(render):
            return masker.mask_statement(render)
        if relaxed or masker.mask_spans(sql, True):
            return MASK
        return masker.mask_text(render)
    except Exception:
        return MASK
