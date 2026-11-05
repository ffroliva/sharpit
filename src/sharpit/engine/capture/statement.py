"""One statement path: raw text read once, then rendered (spec §3). Apart from ``sqlscan``, which has no ``Masker``."""

from __future__ import annotations

import re

from sharpit.engine.capture.sqlscan import Normalized, Reading, read_statement, shown
from sharpit.engine.masking import MASK, Masker

# Words a statement starts with on PostgreSQL, MySQL or SQLite. The list is partial, ``REPAIR`` and ``ABORT`` are not in
# it: a first word outside it only hides more. A ``-`` after a word makes it no verb: ``set-cookie``.
_VERB = re.compile(
    r"[(\s]*(?:alter|analyze|attach|begin|binlog|call|change|checkpoint|clone|cluster|comment|commit|copy|create"
    r"|deallocate|declare|delete|desc|describe|detach|do|drop|exec|execute|explain|fetch|flush|grant|handler|insert|kill"
    r"|listen|load|lock|merge|notify|optimize|pragma|prepare|refresh|reindex|release|rename|replace|reset|resignal"
    r"|revoke|rollback|savepoint|select|set|show|signal|start|table|truncate|unlock|update|use|vacuum|values|with)"
    r"(?=[^\w$-]|$)",
    re.IGNORECASE,
)


def statement_text(masker: Masker, sql: str, mysql: bool = False, reading: Reading | None = None) -> str | None:
    """``sql`` with its literals and secrets gone; ``None`` under ``METADATA_ONLY``, ``******`` if the render fails.

    Text that starts with no verb is no statement, though it reaches ``db.statement``: a hit there hides all of it,
    because a value's end is a guess and ``_mask_glued`` cannot read past a ``?`` the scan left beside a token. With
    no hit the raw text holds nothing the passes know, so what is left is the render, as at 0.4.0. ``reading`` is
    ``read_statement``'s, when the caller holds it.
    """
    try:
        relaxed = masker.mask_spans(sql, False)
        if relaxed is None:
            return None
        render = shown(sql, relaxed, mysql, reading)
        if _VERB.match(render):
            return masker.mask_statement(render)
        if relaxed or masker.mask_spans(sql, True):
            return MASK
        return masker.mask_text(render)
    except Exception:
        return MASK


def masked_shape(masker: Masker, sql: str, mysql: bool) -> Normalized:
    """The scan's shape of ``sql`` with ``statement_text`` as its text and, lower-cased, as its fingerprint.

    A fingerprint built before the masker keeps a secret in code, and lower-casing hides a vendor token from a later
    pass. Under ``METADATA_ONLY``, which gives no text, the scan's shape stands.
    """
    reading = read_statement(sql, mysql)
    text = statement_text(masker, sql, mysql, reading)
    return reading.shape if text is None else reading.shape._replace(sql=text, fingerprint=text.lower())
