from __future__ import annotations

import json
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


_CLAUDE_CANONICAL: dict[str, str] = dict(
    p.split(":")
    for p in [
        "Task:SUB_AGENT",
        "Agent:SUB_AGENT",
        "Bash:SHELL",
        "GlobTool:SEARCH",
        "GrepTool:SEARCH",
        "FileReadTool:FILE_READ",
        "FileEditTool:FILE_EDIT",
        "FileWriteTool:FILE_EDIT",
        "NotebookEditTool:FILE_EDIT",
        "WebFetchTool:WEB",
        "WebSearchTool:WEB",
        "ListMcpServersTool:SKILL",
        "ListMcpToolsTool:SKILL",
        "CallMcpTool:MCP",
        "ListMcpResourcesTool:SKILL",
        "ReadMcpResourceTool:SKILL",
    ]
)

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
    tt = _as_dict(data.get("toolTelemetry"))
    if tt:
        props = _as_dict(tt.get("properties"))
        if props and isinstance(props.get("fileExtension"), str):
            return cast(str, props["fileExtension"])
    inp = _as_dict(data.get("input"))
    if inp:
        tr = _as_dict(inp.get("toolResult"))
        if tr:
            tt2 = _as_dict(tr.get("toolTelemetry"))
            if tt2:
                props2 = _as_dict(tt2.get("properties"))
                if props2 and isinstance(props2.get("fileExtension"), str):
                    return cast(str, props2["fileExtension"])
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
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return int(dt.timestamp() * 1000)
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


class _BaseParser:
    def __init__(
        self,
        session_id: str,
        file_path: Path,
        stat_result: Any,
        max_events: int = 2000,
        include_lifecycle: bool = False,
    ):
        self.session_id = session_id
        self.file_path = file_path
        self.mtime = int(stat_result.st_mtime * 1000)
        self.file_size = stat_result.st_size
        self.max_events = max_events

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


class _LegacyParser(_BaseParser):
    def add_event(self, node: dict[str, Any], turn_idx: int, idx_in_turn: int) -> None:
        type_val = _first_string(node, "type", "kind", "event", "role")
        tool_val = _first_string(node, "tool", "name", "tool_name", "toolName", "function")
        if not type_val and not tool_val:
            return
        ts = parse_timestamp(node.get("timestamp") or node.get("ts") or node.get("created_at") or node.get("createdAt"))
        if ts is not None:
            if self.started_at is None or ts < self.started_at:
                self.started_at = ts
            if self.updated_at is None or ts > self.updated_at:
                self.updated_at = ts

        succ = _legacy_event_success(node)
        category = categorize(type_val, tool_val)
        summary_str = sanitized_summary(type_val, tool_val, category, node)
        eid = f"t{turn_idx}-i{idx_in_turn}-{tool_val or ''}"
        event_dict: dict[str, Any] = {
            "id": eid,
            "turnIndex": turn_idx,
            "timestampEpochMillis": ts,
            "type": truncate(type_val, 64),
            "toolName": truncate(tool_val, 96),
            "category": category,
            "summary": truncate(summary_str, 240),
            "success": succ,
        }
        if len(self.events) < self.max_events:
            self.events.append(event_dict)
            self.raw_by_id[eid] = node
        if succ is False and len(self.failure_events) < self.max_events:
            self.failure_events.append(event_dict)
        self.by_category[category] = self.by_category.get(category, 0) + 1
        if tool_val:
            self.tool_counts[tool_val] = self.tool_counts.get(tool_val, 0) + 1
        in_t, out_t, _ = _extract_tokens_from_dict(node, None, None)
        _record_activity(self.activity_by_hour, ts, succ, in_t, out_t)

    def process_turns(self, turns_raw: list[Any]) -> None:
        for t_idx, turn_raw in enumerate(turns_raw):
            turn_obj = _as_dict(turn_raw)
            if not turn_obj:
                continue
            turn_start = parse_timestamp(
                turn_obj.get("started_at")
                or turn_obj.get("startedAt")
                or turn_obj.get("timestamp")
                or turn_obj.get("created_at")
            )
            duration_ms = _first_int(turn_obj, "duration_ms", "durationMs", "duration")
            turn_summary = _first_string(turn_obj, "summary", "title", "intent")
            before_cnt = len(self.events)

            sub_events = _first_list(turn_obj, "events", "activity", "tool_calls", "toolCalls")
            if sub_events:
                for i_idx, ev in enumerate(sub_events):
                    ev_dict = _as_dict(ev)
                    if ev_dict and len(self.events) < self.max_events:
                        self.add_event(ev_dict, t_idx, i_idx)

            t_in, t_out, _ = _extract_tokens_from_dict(turn_obj, None, None)
            if t_in is not None:
                self.session_in_tokens = (self.session_in_tokens or 0) + t_in
            if t_out is not None:
                self.session_out_tokens = (self.session_out_tokens or 0) + t_out

            self.turns.append(
                {
                    "index": t_idx,
                    "startedAtEpochMillis": turn_start,
                    "durationMillis": duration_ms,
                    "summary": turn_summary,
                    "eventCount": len(self.events) - before_cnt,
                    "inputTokens": t_in,
                    "outputTokens": t_out,
                }
            )

    def process_events(self, events_raw: list[Any]) -> None:
        for i_idx, ev in enumerate(events_raw):
            ev_dict = _as_dict(ev)
            if ev_dict and len(self.events) < self.max_events:
                self.add_event(ev_dict, 0, i_idx)
                in_t, out_t, _ = _extract_tokens_from_dict(ev_dict, None, None)
                if in_t is not None:
                    self.session_in_tokens = (self.session_in_tokens or 0) + in_t
                if out_t is not None:
                    self.session_out_tokens = (self.session_out_tokens or 0) + out_t

    def process_messages(self, messages_raw: list[Any]) -> None:
        valid: list[Any] = []
        for m in messages_raw:
            m_dict = _as_dict(m)
            if m_dict and (str(m_dict.get("role") or m_dict.get("type")).lower() != "user"):
                valid.append(m_dict)
        self.process_events(valid)

    def _extract_root_info(self, root: dict[str, Any]) -> tuple[list[Any] | None, list[Any] | None, list[Any] | None]:
        self.model = _first_string(root, "model", "active_model", "activeModel")
        self.cwd = _first_string(root, "cwd", "working_dir", "workingDirectory", "workdir")
        self.status = _first_string(root, "status", "state")
        self.started_at = parse_timestamp(root.get("created_at") or root.get("started_at") or root.get("startedAt"))
        self.updated_at = parse_timestamp(root.get("updated_at") or root.get("updatedAt"))
        events_raw = _first_list(root, "events", "activity", "tool_calls", "toolCalls")
        turns_raw = root.get("turns") if isinstance(root.get("turns"), list) else None
        messages_raw = _first_list(root, "messages", "history")
        return events_raw, turns_raw, messages_raw

    def parse(self) -> ParsedSession:
        try:
            with open(self.file_path, "rb") as f:
                raw_bytes = f.read()
            root = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            summary = _default_summary()
            summary["id"], summary["filename"], summary["schemaDrift"] = self.session_id, self.file_path.name, True
            summary["updatedAtEpochMillis"] = self.mtime
            counts: dict[str, Any] = {"total": 0, "byCategory": {}, "errors": 0, "lastActivityEpochMillis": None}
            return ParsedSession(summary=summary, counts=counts, file_size=self.file_size, file_mtime=self.mtime)

        events_raw, turns_raw, messages_raw = (None, None, None)
        root_dict = _as_dict(root)
        if root_dict is not None:
            events_raw, turns_raw, messages_raw = self._extract_root_info(root_dict)
        elif isinstance(root, list):
            events_raw = cast(list[Any], root)

        if self.updated_at is None:
            self.updated_at = self.mtime

        if turns_raw is not None:
            self.process_turns(turns_raw)
        elif events_raw is not None:
            self.process_events(events_raw)
        elif messages_raw is not None:
            self.process_messages(messages_raw)

        if self.session_in_tokens is None and self.session_out_tokens is None and root_dict is not None:
            self.session_in_tokens, self.session_out_tokens, _ = _extract_tokens_from_dict(root_dict, None, None)

        if self.events:
            self.last_summary = self.events[-1]["summary"]
            ts = self.events[-1].get("timestampEpochMillis")
            self.last_activity = ts if ts is not None else self.updated_at
        else:
            self.last_activity = self.updated_at

        schema_drift = len(self.events) == 0 and events_raw is None and turns_raw is None
        return self.make_session(self.file_path.name, schema_drift)


def _parse_claude_content_blocks(
    message: dict[str, Any],
    line_no: int,
    turn_idx: int,
    ts: int | None,
    tool_name_by_event_id: dict[str, str],
) -> list[dict[str, Any]]:
    claude_events: list[dict[str, Any]] = []
    content_val = message.get("content")
    blocks = cast(list[Any], content_val) if isinstance(content_val, list) else [content_val]
    for b_idx, block_raw in enumerate(blocks):
        block = _as_dict(block_raw)
        if not block:
            continue
        b_type = block.get("type")
        if b_type == "tool_use":
            t_name = _first_string(block, "name")
            if not t_name:
                continue
            b_id = _first_string(block, "id") or f"l{line_no}-b{b_idx}"
            cat = categorize("tool_use", t_name)
            summ = sanitized_jsonl_summary("tool_use", t_name, cat, None, True)
            claude_events.append(
                {
                    "id": b_id,
                    "turnIndex": turn_idx,
                    "timestampEpochMillis": ts,
                    "type": "tool_use",
                    "toolName": truncate(t_name, 96),
                    "category": cat,
                    "summary": truncate(summ, 240),
                    "success": True,
                }
            )
            tool_name_by_event_id[b_id] = t_name
        elif b_type == "tool_result":
            t_use_id = _first_string(block, "tool_use_id", "toolUseId")
            t_name = tool_name_by_event_id.get(t_use_id) if t_use_id else None
            is_err = block.get("is_error")
            succ_val = not is_err if isinstance(is_err, bool) else None
            cat = categorize("tool_result", t_name)
            summ = sanitized_jsonl_summary("tool_result", t_name, cat, None, succ_val)
            res_id = (t_use_id or f"l{line_no}-b{b_idx}-tool-result") + "-result"
            claude_events.append(
                {
                    "id": res_id,
                    "turnIndex": turn_idx,
                    "timestampEpochMillis": ts,
                    "type": "tool_result",
                    "toolName": truncate(t_name, 96),
                    "category": cat,
                    "summary": truncate(summ, 240),
                    "success": succ_val,
                }
            )
    return claude_events


def _extract_copilot_tool_name(
    data: dict[str, Any] | None, node: dict[str, Any], tool_name_by_event_id: dict[str, str]
) -> str | None:
    tool = None
    if data:
        tool = _first_string(data, "toolName", "tool_name", "name")
        inp = _as_dict(data.get("input"))
        if not tool and inp:
            tool = _first_string(inp, "toolName", "tool_name", "name")
        tr_list = _as_list(data.get("toolRequests"))
        if not tool and tr_list:
            first_tr = _as_dict(tr_list[0])
            if first_tr:
                tool = _first_string(first_tr, "name", "toolName", "tool_name")
    if not tool and node.get("parentId"):
        tool = tool_name_by_event_id.get(str(node["parentId"]))
    return tool


def _extract_copilot_success(data: dict[str, Any] | None, node: dict[str, Any]) -> bool | None:
    succ = None
    if data:
        succ = data.get("success") if isinstance(data.get("success"), bool) else data.get("ok")
    if succ is None:
        succ = node.get("success") if isinstance(node.get("success"), bool) else node.get("ok")
    status_val = _first_string(data, "status") or _first_string(node, "status")
    if succ is None and status_val:
        st_low = status_val.lower()
        if "error" in st_low or "fail" in st_low:
            return False
        if "ok" in st_low or "success" in st_low or "complete" in st_low:
            return True
    return succ


class _JsonlParser(_BaseParser):
    def __init__(
        self,
        session_id: str,
        file_path: Path,
        stat_result: Any,
        max_events: int = 2000,
        include_lifecycle: bool = False,
    ):
        super().__init__(session_id, file_path, stat_result, max_events)
        self.include_lifecycle = include_lifecycle
        self.authoritative_tokens = self.schema_drift = self.parsed_any_line = False
        self.tool_name_by_event_id: dict[str, str] = {}
        self.turn_accumulators: dict[str, dict[str, Any]] = {}
        self.incremental_token_by_hour: dict[int, list[Any]] = {}
        self.authoritative_token_by_hour: dict[int, list[Any]] = {}

    def _extract_ts(self, node: dict[str, Any], data: dict[str, Any] | None) -> int | None:
        keys = ("timestamp", "ts", "created_at", "createdAt", "time", "startTime")
        return next(
            (ts for d in (node, data) if d for k in keys if (ts := parse_timestamp(d.get(k))) is not None), None
        )

    def _update_context(
        self, node: dict[str, Any], data: dict[str, Any] | None, message: dict[str, Any] | None
    ) -> None:
        ctx = data.get("context") if data and isinstance(data.get("context"), dict) else None
        if not self.model:
            self.model = _first_string(data, "model") or _first_string(node, "model") or _first_string(message, "model")
        if not self.cwd:
            self.cwd = _first_string(ctx, "cwd") or _first_string(node, "cwd")
        if not self.status:
            self.status = (
                _first_string(data, "status")
                or _first_string(node, "status", "state")
                or _first_string(message, "stop_reason")
            )

    def _get_turn_idx(
        self, node: dict[str, Any], data: dict[str, Any] | None, type_val: str | None, ts: int | None
    ) -> int:
        turn_key = None
        if data:
            turn_key = _first_string(data, "turnId", "turn_id")
            if not turn_key and type_val and type_val.startswith("assistant.turn"):
                turn_key = _first_string(data, "id", "messageId")
        if not turn_key:
            turn_key = _first_string(node, "uuid", "parentUuid", "parent_uuid") or "__session"

        if turn_key not in self.turn_accumulators:
            self.turn_accumulators[turn_key] = {
                "index": len(self.turn_accumulators),
                "startedAt": ts,
                "lastSeenAt": ts,
                "eventCount": 0,
                "summary": type_val,
                "inputTokens": None,
                "outputTokens": None,
            }
        t_acc = self.turn_accumulators[turn_key]
        if ts is not None:
            if t_acc["startedAt"] is None or ts < t_acc["startedAt"]:
                t_acc["startedAt"] = ts
            if t_acc["lastSeenAt"] is None or ts > t_acc["lastSeenAt"]:
                t_acc["lastSeenAt"] = ts
        t_acc["eventCount"] += 1
        if not t_acc["summary"] and type_val:
            t_acc["summary"] = type_val
        return t_acc["index"]

    def _apply_authoritative_tokens(self, in_tok: int | None, out_tok: int | None, ts: int | None) -> None:
        self.session_in_tokens, self.session_out_tokens = in_tok, out_tok
        self.authoritative_tokens = True
        self.authoritative_token_by_hour.clear()
        if ts is not None:
            self.authoritative_token_by_hour[_hour_start(ts)] = [0, 0, in_tok, out_tok]

    def _apply_turn_tokens(self, in_tok: int | None, out_tok: int | None, turn_idx: int) -> None:
        for t_acc in self.turn_accumulators.values():
            if t_acc["index"] == turn_idx:
                if in_tok is not None:
                    t_acc["inputTokens"] = (t_acc["inputTokens"] or 0) + in_tok
                if out_tok is not None:
                    t_acc["outputTokens"] = (t_acc["outputTokens"] or 0) + out_tok
                break

    def _apply_incremental_tokens(self, in_tok: int | None, out_tok: int | None, ts: int | None, turn_idx: int) -> None:
        self._apply_turn_tokens(in_tok, out_tok, turn_idx)
        if not self.authoritative_tokens:
            if in_tok is not None:
                self.session_in_tokens = (self.session_in_tokens or 0) + in_tok
            if out_tok is not None:
                self.session_out_tokens = (self.session_out_tokens or 0) + out_tok
            if ts is not None:
                rec = self.incremental_token_by_hour.setdefault(_hour_start(ts), [0, 0, None, None])
                if in_tok is not None:
                    rec[2] = (rec[2] or 0) + in_tok
                if out_tok is not None:
                    rec[3] = (rec[3] or 0) + out_tok

    def _accumulate_tokens(
        self,
        node: dict[str, Any],
        data: dict[str, Any] | None,
        message: dict[str, Any] | None,
        ts: int | None,
        turn_idx: int,
    ) -> None:
        in_tok, out_tok, is_total = _extract_tokens_from_dict(node, data, message)
        if in_tok is None and out_tok is None:
            return
        if is_total:
            self._apply_authoritative_tokens(in_tok, out_tok, ts)
        else:
            self._apply_incremental_tokens(in_tok, out_tok, ts, turn_idx)

    def _record_event_activity(self, ts_val: int | None, is_err: bool) -> None:
        if ts_val is not None:
            rec = self.activity_by_hour.setdefault(_hour_start(ts_val), [0, 0, None, None])
            rec[0] += 1
            rec[1] += int(is_err)

    def _append_single_event(self, ev: dict[str, Any], node_id: str | None, line_no: int) -> None:
        ev_id, t_name = ev["id"], ev.get("toolName")
        if t_name:
            self.tool_name_by_event_id[ev_id] = t_name
            if node_id:
                self.tool_name_by_event_id[node_id] = t_name
            self.tool_counts[t_name] = self.tool_counts.get(t_name, 0) + 1

        self.last_summary = ev["summary"]
        ts_val = ev.get("timestampEpochMillis")
        if ts_val is not None:
            self.last_activity = ts_val

        is_err = ev.get("success") is False
        if is_err:
            if len(self.failure_events) >= self.max_events:
                self.failure_events.pop(0)
            self.failure_events.append(ev)

        self.by_category[ev["category"]] = self.by_category.get(ev["category"], 0) + 1
        self._record_event_activity(ts_val, is_err)

        if len(self.events) >= self.max_events:
            evicted = self.events.pop(0)
            self.raw_by_id.pop(evicted["id"], None)
        self.events.append(ev)
        self.raw_by_id[ev_id] = (self.file_path, line_no)

    def _append_events(self, line_events: list[dict[str, Any]], node: dict[str, Any], line_no: int) -> None:
        node_id = _first_string(node, "id", "eventId", "messageId")
        for ev in line_events:
            self._append_single_event(ev, node_id, line_no)

    def feed_line(self, line_no: int, line: str) -> None:
        try:
            raw_node = json.loads(line)
        except Exception:
            self.schema_drift = True
            return
        node = _as_dict(raw_node)
        if node is None:
            self.schema_drift = True
            return

        self.parsed_any_line = True
        data = _as_dict(node.get("data"))
        message = _as_dict(node.get("message"))
        type_val = _first_string(node, "type", "kind", "event", "role")

        ts = self._extract_ts(node, data)
        if ts is not None:
            if self.started_at is None or ts < self.started_at:
                self.started_at = ts
            if self.updated_at is None or ts > self.updated_at:
                self.updated_at = ts

        self._update_context(node, data, message)
        turn_idx = self._get_turn_idx(node, data, type_val, ts)
        self._accumulate_tokens(node, data, message, ts, turn_idx)

        line_events = (
            _parse_claude_content_blocks(message, line_no, turn_idx, ts, self.tool_name_by_event_id)
            if message and "content" in message
            else []
        )

        if not line_events:
            if is_sensitive_message_event(type_val):
                return
            if not self.include_lifecycle and is_lifecycle_event(type_val):
                return

            tool = _extract_copilot_tool_name(data, node, self.tool_name_by_event_id)
            if not type_val and not tool:
                return

            succ = _extract_copilot_success(data, node)
            cat = categorize(type_val, tool)
            summ = sanitized_jsonl_summary(type_val, tool, cat, data, succ)
            eid = _first_string(node, "id", "eventId", "messageId") or f"l{line_no}-t{turn_idx}-{tool or 'event'}"
            line_events = [
                {
                    "id": eid,
                    "turnIndex": turn_idx,
                    "timestampEpochMillis": ts,
                    "type": truncate(type_val, 64),
                    "toolName": truncate(tool, 96),
                    "category": cat,
                    "summary": truncate(summ, 240),
                    "success": succ,
                }
            ]

        self._append_events(line_events, node, line_no)

    def parse(self) -> ParsedSession:
        try:
            with open(self.file_path, encoding="utf-8", errors="replace") as f:
                for line_no, raw_line in enumerate(f, start=1):
                    line = raw_line.strip()
                    if line:
                        self.feed_line(line_no, line)
        except Exception:
            self.schema_drift = True

        if self.updated_at is None:
            self.updated_at = self.mtime
        if self.last_summary is None and self.events:
            self.last_summary = self.events[-1]["summary"]

        tokens_by_hour = (
            self.authoritative_token_by_hour if self.authoritative_tokens else self.incremental_token_by_hour
        )
        for h, t_rec in tokens_by_hour.items():
            t_entry = self.activity_by_hour.setdefault(h, [0, 0, None, None])
            if t_rec[2] is not None:
                t_entry[2] = (t_entry[2] or 0) + t_rec[2]
            if t_rec[3] is not None:
                t_entry[3] = (t_entry[3] or 0) + t_rec[3]

        turns: list[dict[str, Any]] = []
        for t_acc in self.turn_accumulators.values():
            st, last = t_acc["startedAt"], t_acc["lastSeenAt"]
            dur = (last - st) if (st is not None and last is not None) else None
            turns.append(
                {
                    "index": t_acc["index"],
                    "startedAtEpochMillis": st,
                    "durationMillis": dur,
                    "summary": t_acc["summary"],
                    "eventCount": t_acc["eventCount"],
                    "inputTokens": t_acc["inputTokens"],
                    "outputTokens": t_acc["outputTokens"],
                }
            )
        self.turns = turns

        rel_name = (
            f"{self.file_path.parent.name}/{self.file_path.name}"
            if self.file_path.name == "events.jsonl"
            else self.file_path.name
        )
        return self.make_session(rel_name, self.schema_drift or not self.parsed_any_line)


def parse_session(
    path: Path,
    layout: Layout,
    max_events: int = 2000,
    include_lifecycle: bool = False,
) -> ParsedSession:
    target = path / "events.jsonl" if path.is_dir() and (path / "events.jsonl").is_file() else path
    session_id = target.parent.name if target.name == "events.jsonl" else target.stem
    try:
        st = target.stat()
    except Exception:
        summary = _default_summary()
        summary["id"] = session_id
        summary["schemaDrift"] = True
        counts: dict[str, Any] = {"total": 0, "byCategory": {}, "errors": 0, "lastActivityEpochMillis": None}
        return ParsedSession(summary=summary, counts=counts)
    return parse_session_file(session_id, target, st, layout, max_events, include_lifecycle)


def parse_session_file(
    session_id: str,
    path: Path,
    stat_result: Any,
    layout: Layout,
    max_events: int = 2000,
    include_lifecycle: bool = False,
) -> ParsedSession:
    parser_cls = _JsonlParser if path.name.lower().endswith(".jsonl") else _LegacyParser
    return parser_cls(session_id, path, stat_result, max_events, include_lifecycle).parse()
