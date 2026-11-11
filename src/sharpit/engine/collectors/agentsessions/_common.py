from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse


def _as_dict(val: Any) -> dict[str, Any] | None:
    return cast(dict[str, Any], val) if isinstance(val, dict) else None


def _as_list(val: Any) -> list[Any] | None:
    return cast(list[Any], val) if isinstance(val, list) else None


class Layout(Enum):
    COPILOT = "COPILOT"
    CLAUDE_CODE = "CLAUDE_CODE"


def _default_summary() -> dict[str, Any]:
    return {
        "id": "unknown",
        "filename": "",
        "startedAtEpochMillis": None,
        "updatedAtEpochMillis": None,
        "model": None,
        "workingDirectory": None,
        "status": None,
        "eventCount": 0,
        "turnCount": 0,
        "inputTokens": None,
        "outputTokens": None,
        "errorCount": 0,
        "lastActivitySummary": None,
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
    activity_by_hour: dict[int, tuple[int, int, int | None, int | None]] = field(
        default_factory=dict[int, tuple[int, int, int | None, int | None]]
    )
    file_size: int = 0
    file_mtime: int = 0


_CANONICAL_SKILLS = (
    "Skill",
    "ToolSearch",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
    "ListMcpServersTool",
    "ListMcpToolsTool",
)
_CANONICAL_EDITS = ("Write", "Edit", "MultiEdit", "NotebookEdit", "FileEditTool", "FileWriteTool", "NotebookEditTool")
_CANONICAL_AGENTS = (
    "Task",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskOutput",
    "TaskStop",
    "TaskGet",
    "Agent",
    "SubAgent",
)
_CANONICAL_GROUPS = (
    ("SHELL", ("Bash",)),
    ("FILE_READ", ("Read", "NotebookRead", "FileReadTool")),
    ("FILE_EDIT", _CANONICAL_EDITS),
    ("SEARCH", ("Glob", "Grep", "GlobTool", "GrepTool")),
    ("SUB_AGENT", _CANONICAL_AGENTS),
    ("WEB", ("WebSearch", "WebFetch", "WebFetchTool", "WebSearchTool")),
    ("ASK", ("EnterPlanMode", "ExitPlanMode", "AskUserQuestion", "TodoWrite")),
    ("SKILL", _CANONICAL_SKILLS),
    ("MCP", ("CallMcpTool",)),
)
_CLAUDE_CANONICAL: dict[str, str] = {k: v for v, keys in _CANONICAL_GROUPS for k in keys}

_MatcherFunc = Callable[[str, str], bool]

_MATCHERS: tuple[tuple[str, _MatcherFunc], ...] = (
    ("MCP", lambda t, n: bool(n.startswith(("mcp.", "mcp_")) or "mcp" in t)),
    ("HOOK", lambda t, n: bool("hook" in t or "hook" in n)),
    ("SKILL", lambda t, n: bool("skill" in t or "skill" in n)),
    ("SUB_AGENT", lambda t, n: bool("sub_agent" in t or "subagent" in t or "sub_agent" in n or n == "task")),
    ("FILE_EDIT", lambda t, n: any(k in n for k in ("apply_patch", "edit", "write", "create"))),
    ("FILE_READ", lambda t, n: bool(n == "view" or any(k in n for k in ("read", "cat", "head", "tail")))),
    ("SEARCH", lambda t, n: bool(any(k in n for k in ("grep", "glob", "search")) or n in ("rg", "find"))),
    ("SHELL", lambda t, n: any(k in n for k in ("shell", "bash", "terminal", "run_command", "execute"))),
    ("WEB", lambda t, n: any(k in n for k in ("web_fetch", "web_search", "fetch", "http"))),
    ("DOCS", lambda t, n: any(k in n for k in ("github", "docs"))),
    ("FALLBACK", lambda t, n: bool("fallback" in t or "fallback" in n)),
    ("ASK", lambda t, n: any(k in t for k in ("ask", "intent", "plan", "schedule"))),
)


def categorize(type_val: str | None, tool_val: str | None) -> str:
    if tool_val and tool_val in _CLAUDE_CANONICAL:
        return _CLAUDE_CANONICAL[tool_val]
    t, n = (type_val or "").lower(), (tool_val or "").lower()
    for cat, predicate in _MATCHERS:
        if predicate(t, n):
            return cat
    return "OTHER"


_SENSITIVE_TYPES = {"user", "assistant", "system", "summary", "user.message", "assistant.message", "system.message"}


def is_sensitive_message_event(type_val: str | None) -> bool:
    return bool(type_val and type_val.lower() in _SENSITIVE_TYPES)


def is_lifecycle_event(type_val: str | None) -> bool:
    return bool(type_val and type_val.lower() in {"session.start", "session.shutdown", "session.end"})


def truncate(s: str | None, max_len: int) -> str | None:
    return s if (s is None or len(s) <= max_len) else s[:max_len] + "…"


def path_hint(path: str | None) -> str | None:
    if not path or not path.strip():
        return None
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    dot = base.rfind(".")
    return f"*.{base[dot + 1 :]}" if 0 < dot < len(base) - 1 else None


def url_hint(url: str | None) -> str | None:
    try:
        return urlparse(url).hostname if url and url.strip() else None
    except Exception:
        return None


def normalize_extension_hint(ext: str | None) -> str | None:
    if not ext:
        return None
    s = ext.strip().lstrip(".")
    if not s or any(ch in s for ch in (" ", "/", "\\", "?", "*", ":")):
        return None
    return s[:12]


def sanitized_summary(type_val: str | None, tool_val: str | None, category: str, node: dict[str, Any]) -> str:
    display = tool_val if tool_val is not None else (type_val if type_val is not None else "event")
    res = f"{category} · {display}"
    if node.get("success") is False:
        res += " · failed"
    for k in ("path", "file", "target", "filePath", "filename", "url", "uri"):
        val = node.get(k)
        if isinstance(val, str) and val.strip():
            hint = url_hint(val) if k in ("url", "uri") else path_hint(val)
            if hint:
                res += f" · {hint}"
                break
    return res


def _extract_telemetry_ext(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    inp = _as_dict(data.get("input"))
    tr = _as_dict(inp.get("toolResult")) if inp else None
    for raw in (data.get("toolTelemetry"), tr.get("toolTelemetry") if tr else None):
        tt = _as_dict(raw)
        if tt:
            props = _as_dict(tt.get("properties"))
            if props and isinstance(props.get("fileExtension"), str):
                return cast(str, props["fileExtension"])
    return None


def sanitized_jsonl_summary(
    type_val: str | None,
    tool_val: str | None,
    category: str,
    data: dict[str, Any] | None,
    success: bool | None,
) -> str:
    display = tool_val if tool_val is not None else (type_val if type_val is not None else "event")
    res = f"{category} · {display}"
    if success is False:
        res += " · failed"
    ext = normalize_extension_hint(_extract_telemetry_ext(data))
    if ext:
        res += f" · *.{ext}"
    return res


def _parse_str_timestamp(s: str) -> int | None:
    if s.isdigit():
        v = int(s)
        return v * 1000 if 0 < v < 10_000_000_000 else v
    try:
        dt = datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
        return int((dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp() * 1000)
    except Exception:
        return None


def parse_timestamp(val: Any) -> int | None:
    if isinstance(val, (int, float)):
        v = int(val)
        return v * 1000 if 0 < v < 10_000_000_000 else v
    if isinstance(val, str) and val.strip():
        return _parse_str_timestamp(val.strip())
    return None


def _first_string(d: dict[str, Any] | None, *keys: str) -> str | None:
    return next((v.strip() for k in keys if d and isinstance((v := d.get(k)), str) and v.strip()), None)


def _first_int(d: dict[str, Any] | None, *keys: str) -> int | None:
    return next((int(v) for k in keys if d and isinstance((v := d.get(k)), (int, float))), None)


def _first_list(d: dict[str, Any] | None, *keys: str) -> list[Any] | None:
    return next((cast(list[Any], v) for k in keys if d and isinstance((v := d.get(k)), list)), None)


def _hour_start(ts: int) -> int:
    return ts - (ts % 3600_000)


def _bucket_tokens(bucket: Any) -> int | None:
    if isinstance(bucket, (int, float)):
        return int(bucket)
    b_dict = _as_dict(bucket)
    if b_dict:
        for ck in ("tokenCount", "token_count", "tokens", "count"):
            val = b_dict.get(ck)
            if isinstance(val, (int, float)):
                return int(val)
    return None


_IN_TOKEN_KEYS = [
    "input",
    "inputTokens",
    "input_tokens",
    "cache_read",
    "cacheRead",
    "cacheReadTokens",
    "cache_read_tokens",
    "cache_write",
    "cacheWrite",
    "cacheWriteTokens",
    "cache_write_tokens",
]
_OUT_TOKEN_KEYS = ("output", "outputTokens", "output_tokens")

_IN_USAGE_KEYS = [
    "inputTokens",
    "input_tokens",
    "promptTokens",
    "prompt_tokens",
    "input",
    "prompt",
    "input_token_count",
    "cacheReadTokens",
    "cache_read_tokens",
    "cache_read_input_tokens",
    "cached_prompt_tokens",
    "cacheCreationTokens",
    "cache_creation_tokens",
    "cache_creation_input_tokens",
]
_OUT_USAGE_KEYS = [
    "outputTokens",
    "output_tokens",
    "completionTokens",
    "completion_tokens",
    "output",
    "completion",
    "output_token_count",
]


def _from_token_details(td: dict[str, Any]) -> tuple[int | None, int | None, bool] | None:
    in_tokens = sum(_bucket_tokens(td[k]) or 0 for k in _IN_TOKEN_KEYS if td.get(k) is not None) or None
    out_tokens = sum(_bucket_tokens(td[k]) or 0 for k in _OUT_TOKEN_KEYS if td.get(k) is not None) or None
    if in_tokens is not None or out_tokens is not None:
        return in_tokens, out_tokens, True
    return None


def _from_usage_dict(u: dict[str, Any]) -> tuple[int | None, int | None]:
    return (
        sum(int(u[k]) for k in _IN_USAGE_KEYS if isinstance(u.get(k), (int, float))) or None,
        sum(int(u[k]) for k in _OUT_USAGE_KEYS if isinstance(u.get(k), (int, float))) or None,
    )


def _from_model_metrics(mm: dict[str, Any]) -> tuple[int | None, int | None, bool] | None:
    in_tok, out_tok = None, None
    for mobj in mm.values():
        m_dict = _as_dict(mobj)
        if m_dict:
            u = _as_dict(m_dict.get("usage"))
            if u:
                i, o = _from_usage_dict(u)
                if i is not None:
                    in_tok = (in_tok or 0) + i
                if o is not None:
                    out_tok = (out_tok or 0) + o
    return (in_tok, out_tok, True) if (in_tok is not None or out_tok is not None) else None


def _check_special_token_details(data: dict[str, Any] | None) -> tuple[int | None, int | None, bool] | None:
    if not data:
        return None
    td = _as_dict(data.get("tokenDetails"))
    if td:
        res = _from_token_details(td)
        if res:
            return res
    mm = _as_dict(data.get("modelMetrics"))
    return _from_model_metrics(mm) if mm else None


def _extract_tokens_from_dict(
    node: dict[str, Any], data: dict[str, Any] | None, message: dict[str, Any] | None
) -> tuple[int | None, int | None, bool]:
    special = _check_special_token_details(data)
    if special:
        return special
    candidates: list[Any] = []
    for d in (data, message, node):
        if d:
            candidates.extend([d.get("usage"), d.get("usageMetadata"), d.get("usage_metadata"), d])
    for raw_obj in candidates:
        obj = _as_dict(raw_obj)
        if obj:
            i_tok, o_tok = _from_usage_dict(obj)
            if i_tok is not None or o_tok is not None:
                return i_tok, o_tok, False
    return None, None, False


def _record_activity(
    activity_by_hour: dict[int, list[Any]],
    ts: int | None,
    success: bool | None,
    in_tok: int | None,
    out_tok: int | None,
) -> None:
    if ts is None:
        return
    h = _hour_start(ts)
    rec = activity_by_hour.setdefault(h, [0, 0, None, None])
    rec[0] += 1
    if success is False:
        rec[1] += 1
    if in_tok is not None:
        rec[2] = (rec[2] or 0) + in_tok
    if out_tok is not None:
        rec[3] = (rec[3] or 0) + out_tok


def _legacy_event_success(node: dict[str, Any]) -> bool | None:
    succ = node.get("success") if isinstance(node.get("success"), bool) else node.get("ok")
    if isinstance(succ, bool):
        return succ
    st_low = str(node.get("status") or "").lower()
    if any(k in st_low for k in ("error", "fail")):
        return False
    return True if any(k in st_low for k in ("ok", "success", "complete")) else None


def read_capped_file(file_path: Path, max_bytes: int) -> bytes | None:
    try:
        with open(file_path, "rb") as f:
            raw_bytes = f.read(max_bytes + 1)
        if len(raw_bytes) > max_bytes:
            return None
        return raw_bytes
    except Exception:
        return None


class _BaseParser:
    def __init__(
        self,
        session_id: str,
        file_path: Path,
        stat_result: Any,
        max_events: int = 2000,
        include_lifecycle: bool = False,
        max_bytes: int = 32 * 1024 * 1024,
    ):
        self.session_id = session_id
        self.file_path = file_path
        self.mtime = int(stat_result.st_mtime * 1000)
        self.file_size = stat_result.st_size
        self.max_events = max_events
        self.max_bytes = max_bytes

        self.model: str | None = None
        self.cwd: str | None = None
        self.status: str | None = None
        self.started_at: int | None = None
        self.updated_at: int | None = None
        self.last_activity: int | None = None
        self.last_summary: str | None = None
        self.session_in_tokens: int | None = None
        self.session_out_tokens: int | None = None

        self.events: list[dict[str, Any]] = []
        self.failure_events: list[dict[str, Any]] = []
        self.raw_by_id: dict[str, Any] = {}
        self.turns: list[dict[str, Any]] = []
        self.tool_counts: dict[str, int] = {}
        self.by_category: dict[str, int] = {}
        self.activity_by_hour: dict[int, list[Any]] = {}

    def _record_timestamp(self, ts: int | None) -> None:
        if ts is not None:
            if self.started_at is None or ts < self.started_at:
                self.started_at = ts
            if self.updated_at is None or ts > self.updated_at:
                self.updated_at = ts

    def make_session(self, filename: str, schema_drift: bool) -> ParsedSession:
        summary = {
            "id": self.session_id,
            "filename": filename,
            "startedAtEpochMillis": self.started_at,
            "updatedAtEpochMillis": self.updated_at,
            "model": self.model,
            "workingDirectory": self.cwd,
            "status": self.status,
            "eventCount": len(self.events),
            "turnCount": len(self.turns) if self.turns else (1 if self.events else 0),
            "inputTokens": self.session_in_tokens,
            "outputTokens": self.session_out_tokens,
            "errorCount": len(self.failure_events),
            "lastActivitySummary": self.last_summary,
            "schemaDrift": schema_drift,
        }
        counts = {
            "total": len(self.events),
            "byCategory": self.by_category,
            "errors": len(self.failure_events),
            "lastActivityEpochMillis": self.last_activity,
        }
        frozen = {h: (rec[0], rec[1], rec[2], rec[3]) for h, rec in self.activity_by_hour.items()}
        return ParsedSession(
            summary=summary,
            counts=counts,
            turns=self.turns,
            events=self.events,
            failure_events=self.failure_events,
            raw_by_id=self.raw_by_id,
            tool_counts=self.tool_counts,
            activity_by_hour=frozen,
            file_size=self.file_size,
            file_mtime=self.mtime,
        )


as_dict = _as_dict
as_list = _as_list
default_summary = _default_summary
first_string = _first_string
first_int = _first_int
first_list = _first_list
hour_start = _hour_start
extract_tokens_from_dict = _extract_tokens_from_dict
record_activity = _record_activity
legacy_event_success = _legacy_event_success
BaseParser = _BaseParser

__all__ = [
    "BaseParser",
    "Layout",
    "ParsedSession",
    "as_dict",
    "as_list",
    "categorize",
    "default_summary",
    "extract_tokens_from_dict",
    "first_int",
    "first_list",
    "first_string",
    "hour_start",
    "is_lifecycle_event",
    "is_sensitive_message_event",
    "legacy_event_success",
    "normalize_extension_hint",
    "parse_timestamp",
    "path_hint",
    "read_capped_file",
    "record_activity",
    "sanitized_jsonl_summary",
    "sanitized_summary",
    "truncate",
    "url_hint",
]
