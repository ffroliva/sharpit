"""Shared tests for deciding whether journal SQL can be read as a statement."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass

from sharpit.engine.collectors.insights.text import stable_hash
from sharpit.engine.sqltext import MASK, UNSUPPORTED_STATEMENT

UNREADABLE = frozenset({MASK, UNSUPPORTED_STATEMENT})
DML = ("insert", "update", "delete", "merge")
SET_OPERATION = re.compile(r"\b(union|intersect|except)\b", re.IGNORECASE)
WRITE = re.compile(r"\s*(insert|update|delete|merge)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SqlStatement:
    normalized: str
    fingerprint: str
    unreadable_or_compound: bool
    is_select: bool
    is_write: bool
    dml_verb: str | None
    readable: bool


def readable(text: object) -> bool:
    return isinstance(text, str) and bool(text.strip()) and text not in UNREADABLE


@functools.lru_cache(maxsize=1024)
def read_statement(statement: str) -> SqlStatement:
    """Parse and classify a SQL statement string once, cached across kinds."""
    is_read = bool(statement.strip()) and statement not in UNREADABLE
    is_unreadable = not is_read or statement.endswith("…") or SET_OPERATION.search(statement) is not None
    normalized = " ".join(statement.split())
    fp = stable_hash(normalized)
    is_sel = normalized.lower().startswith("select")
    write_match = WRITE.match(statement)
    is_write = write_match is not None and not is_sel
    verb = write_match.group(1).lower() if write_match and write_match.group(1).lower() in DML else None
    return SqlStatement(
        normalized=normalized,
        fingerprint=fp,
        unreadable_or_compound=is_unreadable,
        is_select=is_sel,
        is_write=is_write,
        dml_verb=verb,
        readable=is_read,
    )


def is_unreadable_or_compound(statement: str) -> bool:
    """Whether statement is unreadable, truncated, or contains set operations."""
    return read_statement(statement).unreadable_or_compound


def event_duration(event: dict[str, object]) -> int:
    """The event's duration in nanoseconds, or -1 when missing or negative."""
    duration = event.get("durationNanos")
    return duration if isinstance(duration, int) and duration >= 0 else -1


def event_call_site(event: dict[str, object]) -> str:
    """The event's call site string, or empty string when missing or non-string."""
    site = event.get("callSite")
    return site if isinstance(site, str) else ""


def event_start(event: dict[str, object]) -> int:
    """Monotonic start in nanoseconds (completedNanos - durationNanos), or 2**63 - 1 when unknown."""
    completed = event.get("completedNanos")
    duration = event.get("durationNanos")
    if isinstance(completed, int) and isinstance(duration, int) and completed >= 0 and duration >= 0:
        return completed - duration
    return 2**63 - 1
