"""The built-in SQL filter of the test-session sink (0.3.0 spec §6.4): statements that are not the app's queries."""

from __future__ import annotations

import re

FILTER_RULES = ("PRAGMA", "sqlite_schema", "alembic_version", "transaction control")

_LEADING_COMMENTS = re.compile(r"\A\s*(?:/\*.*?\*/\s*|--[^\n]*\n\s*)*", re.DOTALL)
_PRAGMA = re.compile(r"PRAGMA\b", re.IGNORECASE)
_TRANSACTION = re.compile(r"(?:BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE)\b", re.IGNORECASE)
_SCHEMA_READ = re.compile(r"\b(?:FROM|JOIN)\s+[\"`\[]?(?:\w+\.)?sqlite_(?:temp_)?(?:master|schema)\b", re.IGNORECASE)
_ALEMBIC = re.compile(r"\balembic_version\b", re.IGNORECASE)


def filtered_rule(sql: str) -> str | None:
    """The name of the filter rule ``sql`` hits, else None."""
    body = _LEADING_COMMENTS.sub("", sql, count=1)
    if _PRAGMA.match(body):
        return FILTER_RULES[0]
    if _TRANSACTION.match(body):
        return FILTER_RULES[3]
    if _SCHEMA_READ.search(body):
        return FILTER_RULES[1]
    if _ALEMBIC.search(body):
        return FILTER_RULES[2]
    return None
