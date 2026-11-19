"""Shared tests for deciding whether journal SQL can be read as a statement."""

from __future__ import annotations

import re

from sharpit.engine.sqltext import MASK, UNSUPPORTED_STATEMENT

UNREADABLE = frozenset({MASK, UNSUPPORTED_STATEMENT})
DML = ("insert", "update", "delete", "merge")
SET_OPERATION = re.compile(r"\b(union|intersect|except)\b", re.IGNORECASE)
WRITE = re.compile(r"\s*(insert|update|delete|merge)\b", re.IGNORECASE)


def readable(text: object) -> bool:
    return isinstance(text, str) and bool(text.strip()) and text not in UNREADABLE
