from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from sharpit.engine.collectors.agentsessions._common import (
    BaseParser,
    ParsedSession,
    as_dict,
    as_list,
    categorize,
    extract_tokens_from_dict,
    first_string,
    hour_start,
    is_lifecycle_event,
    is_sensitive_message_event,
    parse_timestamp,
    read_capped_file,
    sanitized_jsonl_summary,
    truncate,
)


def parse_claude_content_blocks(
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
        block = as_dict(block_raw)
        if not block:
            continue
        b_type = block.get("type")
        if b_type == "tool_use":
            t_name = first_string(block, "name")
            if not t_name:
                continue
            b_id = first_string(block, "id") or f"l{line_no}-b{b_idx}"
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
            t_use_id = first_string(block, "tool_use_id", "toolUseId")
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


def extract_copilot_tool_name(
    data: dict[str, Any] | None, node: dict[str, Any], tool_name_by_event_id: dict[str, str]
) -> str | None:
    tool = None
    if data:
        tool = first_string(data, "toolName", "tool_name", "name")
        inp = as_dict(data.get("input"))
        if not tool and inp:
            tool = first_string(inp, "toolName", "tool_name", "name")
        tr_list = as_list(data.get("toolRequests"))
        if not tool and tr_list:
            first_tr = as_dict(tr_list[0])
            if first_tr:
                tool = first_string(first_tr, "name", "toolName", "tool_name")
    if not tool and node.get("parentId"):
        tool = tool_name_by_event_id.get(str(node["parentId"]))
    return tool


def extract_copilot_success(data: dict[str, Any] | None, node: dict[str, Any]) -> bool | None:
    succ = None
    if data:
        succ = data.get("success") if isinstance(data.get("success"), bool) else data.get("ok")
    if succ is None:
        succ = node.get("success") if isinstance(node.get("success"), bool) else node.get("ok")
    status_val = first_string(data, "status") or first_string(node, "status")
    if succ is None and status_val:
        st_low = status_val.lower()
        if "error" in st_low or "fail" in st_low:
            return False
        if "ok" in st_low or "success" in st_low or "complete" in st_low:
            return True
    return succ


class JsonlParser(BaseParser):
    def __init__(
        self,
        session_id: str,
        file_path: Path,
        stat_result: Any,
        max_events: int = 2000,
        include_lifecycle: bool = False,
        max_bytes: int = 32 * 1024 * 1024,
    ):
        super().__init__(session_id, file_path, stat_result, max_events, include_lifecycle, max_bytes)
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
            self.model = first_string(data, "model") or first_string(node, "model") or first_string(message, "model")
        if not self.cwd:
            self.cwd = first_string(ctx, "cwd") or first_string(node, "cwd")
        if not self.status:
            self.status = (
                first_string(data, "status")
                or first_string(node, "status", "state")
                or first_string(message, "stop_reason")
            )

    def _get_turn_idx(
        self, node: dict[str, Any], data: dict[str, Any] | None, type_val: str | None, ts: int | None
    ) -> int:
        turn_key = None
        if data:
            turn_key = first_string(data, "turnId", "turn_id")
            if not turn_key and type_val and type_val.startswith("assistant.turn"):
                turn_key = first_string(data, "id", "messageId")
        if not turn_key:
            turn_key = first_string(node, "uuid", "parentUuid", "parent_uuid") or "__session"

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
            self.authoritative_token_by_hour[hour_start(ts)] = [0, 0, in_tok, out_tok]

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
                rec = self.incremental_token_by_hour.setdefault(hour_start(ts), [0, 0, None, None])
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
        in_tok, out_tok, is_total = extract_tokens_from_dict(node, data, message)
        if in_tok is None and out_tok is None:
            return
        if is_total:
            self._apply_authoritative_tokens(in_tok, out_tok, ts)
        else:
            self._apply_incremental_tokens(in_tok, out_tok, ts, turn_idx)

    def _record_event_activity(self, ts_val: int | None, is_err: bool) -> None:
        if ts_val is not None:
            rec = self.activity_by_hour.setdefault(hour_start(ts_val), [0, 0, None, None])
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
        node_id = first_string(node, "id", "eventId", "messageId")
        for ev in line_events:
            self._append_single_event(ev, node_id, line_no)

    def _build_copilot_event(
        self,
        node: dict[str, Any],
        data: dict[str, Any] | None,
        type_val: str | None,
        ts: int | None,
        turn_idx: int,
        line_no: int,
    ) -> list[dict[str, Any]]:
        if is_sensitive_message_event(type_val):
            return []
        if not self.include_lifecycle and is_lifecycle_event(type_val):
            return []

        tool = extract_copilot_tool_name(data, node, self.tool_name_by_event_id)
        if not type_val and not tool:
            return []

        succ = extract_copilot_success(data, node)
        cat = categorize(type_val, tool)
        summ = sanitized_jsonl_summary(type_val, tool, cat, data, succ)
        eid = first_string(node, "id", "eventId", "messageId") or f"l{line_no}-t{turn_idx}-{tool or 'event'}"
        return [
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

    def feed_line(self, line_no: int, line: str) -> None:
        try:
            raw_node = json.loads(line)
        except Exception:
            self.schema_drift = True
            return
        node = as_dict(raw_node)
        if node is None:
            self.schema_drift = True
            return

        self.parsed_any_line = True
        data = as_dict(node.get("data"))
        message = as_dict(node.get("message"))
        type_val = first_string(node, "type", "kind", "event", "role")

        ts = self._extract_ts(node, data)
        self._record_timestamp(ts)

        self._update_context(node, data, message)
        turn_idx = self._get_turn_idx(node, data, type_val, ts)
        self._accumulate_tokens(node, data, message, ts, turn_idx)

        line_events = (
            parse_claude_content_blocks(message, line_no, turn_idx, ts, self.tool_name_by_event_id)
            if message and "content" in message
            else []
        )

        if not line_events:
            line_events = self._build_copilot_event(node, data, type_val, ts, turn_idx, line_no)

        self._append_events(line_events, node, line_no)

    def _sync_tokens_by_hour(self) -> None:
        tokens_by_hour = (
            self.authoritative_token_by_hour if self.authoritative_tokens else self.incremental_token_by_hour
        )
        for h, t_rec in tokens_by_hour.items():
            t_entry = self.activity_by_hour.setdefault(h, [0, 0, None, None])
            if t_rec[2] is not None:
                t_entry[2] = (t_entry[2] or 0) + t_rec[2]
            if t_rec[3] is not None:
                t_entry[3] = (t_entry[3] or 0) + t_rec[3]

    def _build_turns(self) -> list[dict[str, Any]]:
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
        return turns

    def parse(self) -> ParsedSession:
        raw_bytes = read_capped_file(self.file_path, self.max_bytes)
        if raw_bytes is None:
            self.schema_drift = True
        else:
            for line_no, raw_line in enumerate(raw_bytes.decode("utf-8", errors="replace").splitlines(), start=1):
                line = raw_line.strip()
                if line:
                    self.feed_line(line_no, line)

        if self.updated_at is None:
            self.updated_at = self.mtime
        if self.last_summary is None and self.events:
            self.last_summary = self.events[-1]["summary"]

        self._sync_tokens_by_hour()
        self.turns = self._build_turns()

        rel_name = (
            f"{self.file_path.parent.name}/{self.file_path.name}"
            if self.file_path.name == "events.jsonl"
            else self.file_path.name
        )
        return self.make_session(rel_name, self.schema_drift or not self.parsed_any_line)


_JsonlParser = JsonlParser
_extract_copilot_tool_name = extract_copilot_tool_name
_extract_copilot_success = extract_copilot_success
_parse_claude_content_blocks = parse_claude_content_blocks

__all__ = [
    "JsonlParser",
    "extract_copilot_success",
    "extract_copilot_tool_name",
    "parse_claude_content_blocks",
]
