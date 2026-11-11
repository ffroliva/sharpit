from __future__ import annotations

import json
from typing import Any, cast

from sharpit.engine.collectors.agentsessions._common import (
    BaseParser,
    ParsedSession,
    add_optional,
    as_dict,
    categorize,
    default_summary,
    extract_tokens_from_dict,
    first_int,
    first_list,
    first_string,
    legacy_event_success,
    parse_timestamp,
    read_capped_file,
    record_activity,
    sanitized_summary,
    truncate,
)


class LegacyParser(BaseParser):
    def add_event(self, node: dict[str, Any], turn_idx: int, idx_in_turn: int) -> None:
        type_val = first_string(node, "type", "kind", "event", "role")
        tool_val = first_string(node, "tool", "name", "tool_name", "toolName", "function")
        if not type_val and not tool_val:
            return
        ts = parse_timestamp(node.get("timestamp") or node.get("ts") or node.get("created_at") or node.get("createdAt"))
        self._record_timestamp(ts)

        succ = legacy_event_success(node)
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
            self.raw_by_id[eid] = (self.file_path, 1)
        if succ is False and len(self.failure_events) < self.max_events:
            self.failure_events.append(event_dict)
        self.by_category[category] = self.by_category.get(category, 0) + 1
        if tool_val:
            self.tool_counts[tool_val] = self.tool_counts.get(tool_val, 0) + 1
        in_t, out_t, _ = extract_tokens_from_dict(node, None, None)
        record_activity(self.activity_by_hour, ts, succ, in_t, out_t)

    def _add_session_tokens(self, in_tok: int | None, out_tok: int | None) -> None:
        self.session_in_tokens = add_optional(self.session_in_tokens, in_tok)
        self.session_out_tokens = add_optional(self.session_out_tokens, out_tok)

    def _process_turn(self, t_idx: int, turn_obj: dict[str, Any]) -> None:
        turn_start = parse_timestamp(
            turn_obj.get("started_at")
            or turn_obj.get("startedAt")
            or turn_obj.get("timestamp")
            or turn_obj.get("created_at")
        )
        duration_ms = first_int(turn_obj, "duration_ms", "durationMs", "duration")
        turn_summary = first_string(turn_obj, "summary", "title", "intent")
        before_cnt = len(self.events)

        sub_events = first_list(turn_obj, "events", "activity", "tool_calls", "toolCalls") or []
        for i_idx, ev in enumerate(sub_events):
            ev_dict = as_dict(ev)
            if ev_dict and len(self.events) < self.max_events:
                self.add_event(ev_dict, t_idx, i_idx)

        t_in, t_out, _ = extract_tokens_from_dict(turn_obj, None, None)
        self._add_session_tokens(t_in, t_out)

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

    def process_turns(self, turns_raw: list[Any]) -> None:
        for t_idx, turn_raw in enumerate(turns_raw):
            turn_obj = as_dict(turn_raw)
            if turn_obj:
                self._process_turn(t_idx, turn_obj)

    def process_events(self, events_raw: list[Any]) -> None:
        for i_idx, ev in enumerate(events_raw):
            ev_dict = as_dict(ev)
            if ev_dict and len(self.events) < self.max_events:
                self.add_event(ev_dict, 0, i_idx)
                in_t, out_t, _ = extract_tokens_from_dict(ev_dict, None, None)
                self._add_session_tokens(in_t, out_t)

    def process_messages(self, messages_raw: list[Any]) -> None:
        valid: list[Any] = []
        for m in messages_raw:
            m_dict = as_dict(m)
            if m_dict and (str(m_dict.get("role") or m_dict.get("type")).lower() != "user"):
                valid.append(m_dict)
        self.process_events(valid)

    def _extract_root_info(self, root: dict[str, Any]) -> tuple[list[Any] | None, list[Any] | None, list[Any] | None]:
        self.model = first_string(root, "model", "active_model", "activeModel")
        self.cwd = first_string(root, "cwd", "working_dir", "workingDirectory", "workdir")
        self.status = first_string(root, "status", "state")
        self.started_at = parse_timestamp(root.get("created_at") or root.get("started_at") or root.get("startedAt"))
        self.updated_at = parse_timestamp(root.get("updated_at") or root.get("updatedAt"))
        events_raw = first_list(root, "events", "activity", "tool_calls", "toolCalls")
        turns_raw = root.get("turns") if isinstance(root.get("turns"), list) else None
        messages_raw = first_list(root, "messages", "history")
        return events_raw, turns_raw, messages_raw

    def _empty_drift_session(self) -> ParsedSession:
        summary = default_summary()
        summary["id"] = self.session_id
        summary["filename"] = self.file_path.name
        summary["schemaDrift"] = True
        summary["updatedAtEpochMillis"] = self.mtime
        counts: dict[str, Any] = {"total": 0, "byCategory": {}, "errors": 0, "lastActivityEpochMillis": None}
        return ParsedSession(summary=summary, counts=counts, file_size=self.file_size, file_mtime=self.mtime)

    def _dispatch_content(
        self,
        turns_raw: list[Any] | None,
        events_raw: list[Any] | None,
        messages_raw: list[Any] | None,
    ) -> None:
        if turns_raw is not None:
            self.process_turns(turns_raw)
        elif events_raw is not None:
            self.process_events(events_raw)
        elif messages_raw is not None:
            self.process_messages(messages_raw)

    def parse(self) -> ParsedSession:
        raw_bytes = read_capped_file(self.file_path, self.max_bytes)
        if raw_bytes is None:
            return self._empty_drift_session()
        try:
            root = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            return self._empty_drift_session()

        events_raw, turns_raw, messages_raw = (None, None, None)
        root_dict = as_dict(root)
        if root_dict is not None:
            events_raw, turns_raw, messages_raw = self._extract_root_info(root_dict)
        elif isinstance(root, list):
            events_raw = cast(list[Any], root)

        if self.updated_at is None:
            self.updated_at = self.mtime

        self._dispatch_content(turns_raw, events_raw, messages_raw)

        if self.session_in_tokens is None and self.session_out_tokens is None and root_dict is not None:
            self.session_in_tokens, self.session_out_tokens, _ = extract_tokens_from_dict(root_dict, None, None)

        if self.events:
            self.last_summary = self.events[-1]["summary"]
            ts = self.events[-1].get("timestampEpochMillis")
            self.last_activity = ts if ts is not None else self.updated_at
        else:
            self.last_activity = self.updated_at

        schema_drift = len(self.events) == 0 and events_raw is None and turns_raw is None
        return self.make_session(self.file_path.name, schema_drift)


_LegacyParser = LegacyParser

__all__ = ["LegacyParser"]
