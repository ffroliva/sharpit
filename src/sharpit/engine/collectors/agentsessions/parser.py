from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Layout(Enum):
    COPILOT = "COPILOT"
    CLAUDE_CODE = "CLAUDE_CODE"


def _default_summary() -> dict[str, Any]:
    return {
        "id": "stub-id",
        "model": "stub-model",
        "workingDirectory": "stub-dir",
        "eventCount": -1,
        "errorCount": -1,
        "schemaDrift": False,
    }


@dataclass
class ParsedSession:
    summary: dict[str, Any] = field(default_factory=_default_summary)
    counts: dict[str, Any] = field(default_factory=dict[str, Any])
    turns: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    events: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    failure_events: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    raw_by_id: dict[str, Any] = field(default_factory=dict[str, Any])
    tool_counts: dict[str, int] = field(default_factory=dict[str, int])
    activity_by_hour: dict[int, Any] = field(default_factory=dict[int, Any])
    file_size: int = 0
    file_mtime: int = 0


def categorize(type: str | None, tool: str | None) -> str:
    return "OTHER"


def parse_session(path: Path, layout: Layout, max_events: int = 2000) -> ParsedSession:
    return ParsedSession()
