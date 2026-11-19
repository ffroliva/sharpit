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


def is_unreadable_or_compound(statement: str) -> bool:
    """Whether statement is unreadable, truncated, or contains set operations."""
    return not readable(statement) or statement.endswith("…") or SET_OPERATION.search(statement) is not None


def event_duration(event: dict[str, object]) -> int:
    """The event's duration in nanoseconds, or -1 when missing or negative."""
    duration = event.get("durationNanos")
    return duration if isinstance(duration, int) and duration >= 0 else -1


def event_call_site(event: dict[str, object]) -> str:
    """The event's call site string, or empty string when missing or non-string."""
    site = event.get("callSite")
    return site if isinstance(site, str) else ""
