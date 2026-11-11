from __future__ import annotations

from pathlib import Path
from typing import Any

from sharpit.engine.collectors.agentsessions._common import (
    BaseParser,
    Layout,
    ParsedSession,
    as_dict,
    as_list,
    categorize,
    default_summary,
    is_lifecycle_event,
    is_sensitive_message_event,
    normalize_extension_hint,
    parse_timestamp,
    path_hint,
    sanitized_jsonl_summary,
    sanitized_summary,
    truncate,
    url_hint,
)
from sharpit.engine.collectors.agentsessions._jsonl import (
    JsonlParser,
    extract_copilot_success,
    extract_copilot_tool_name,
    parse_claude_content_blocks,
)
from sharpit.engine.collectors.agentsessions._legacy import LegacyParser

_LegacyParser = LegacyParser
_JsonlParser = JsonlParser
_BaseParser = BaseParser
_as_dict = as_dict
_as_list = as_list
_default_summary = default_summary
_extract_copilot_tool_name = extract_copilot_tool_name
_extract_copilot_success = extract_copilot_success
_parse_claude_content_blocks = parse_claude_content_blocks

__all__ = [
    "BaseParser",
    "JsonlParser",
    "Layout",
    "LegacyParser",
    "ParsedSession",
    "_BaseParser",
    "_JsonlParser",
    "_LegacyParser",
    "_as_dict",
    "_as_list",
    "_default_summary",
    "_extract_copilot_success",
    "_extract_copilot_tool_name",
    "_parse_claude_content_blocks",
    "as_dict",
    "as_list",
    "categorize",
    "default_summary",
    "extract_copilot_success",
    "extract_copilot_tool_name",
    "is_lifecycle_event",
    "is_sensitive_message_event",
    "normalize_extension_hint",
    "parse_claude_content_blocks",
    "parse_session",
    "parse_session_file",
    "parse_timestamp",
    "path_hint",
    "sanitized_jsonl_summary",
    "sanitized_summary",
    "truncate",
    "url_hint",
]

_EVENTS_FILE = "events.jsonl"


def parse_session(
    path: Path,
    max_events: int = 2000,
    include_lifecycle: bool = False,
    max_bytes: int = 32 * 1024 * 1024,
) -> ParsedSession:
    target = path / _EVENTS_FILE if path.is_dir() and (path / _EVENTS_FILE).is_file() else path
    session_id = target.parent.name if target.name == _EVENTS_FILE else target.stem
    try:
        st = target.stat()
    except Exception:
        summary = default_summary()
        summary["id"] = session_id
        summary["schemaDrift"] = True
        counts: dict[str, Any] = {"total": 0, "byCategory": {}, "errors": 0, "lastActivityEpochMillis": None}
        return ParsedSession(summary=summary, counts=counts)
    return parse_session_file(session_id, target, st, max_events, include_lifecycle, max_bytes)


def parse_session_file(
    session_id: str,
    path: Path,
    stat_result: Any,
    max_events: int = 2000,
    include_lifecycle: bool = False,
    max_bytes: int = 32 * 1024 * 1024,
) -> ParsedSession:
    parser_cls = JsonlParser if path.name.lower().endswith(".jsonl") else LegacyParser
    return parser_cls(session_id, path, stat_result, max_events, include_lifecycle, max_bytes).parse()
