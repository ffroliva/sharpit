from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sharpit.engine.collectors.agentsessions.parser import ParsedSession

HOUR_MILLIS = 3600_000
DAY_MILLIS = 86400_000
DASHBOARD_BUCKET_COUNT = 24
DASHBOARD_DAILY_BUCKET_COUNT = 7
DASHBOARD_TOP_LIMIT = 10
DASHBOARD_RECENT_SESSION_LIMIT = 8


def hour_start(ts: int) -> int:
    return ts - (ts % HOUR_MILLIS)


def day_start(ts: int) -> int:
    return ts - (ts % DAY_MILLIS)


def _metric_counts(counts: dict[str, int]) -> list[dict[str, Any]]:
    sorted_items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"label": k, "count": v} for k, v in sorted_items]


def _unavailable_dashboard(reason: str | None, session_state_dir: str, warnings: list[str] | None) -> dict[str, Any]:
    return {
        "available": False,
        "unavailableReason": reason,
        "sessionStateDir": session_state_dir,
        "sessionCount": 0,
        "eventCount": 0,
        "turnCount": 0,
        "totalInputTokens": None,
        "totalOutputTokens": None,
        "errorCount": 0,
        "activeLast24Hours": 0,
        "activeLast7Days": 0,
        "sessionsWithSchemaDrift": 0,
        "lastActivityEpochMillis": None,
        "categoryCounts": [],
        "modelCounts": [],
        "topTools": [],
        "otherToolEventCount": 0,
        "activityBuckets": [],
        "dailyActivityBuckets": [],
        "recentSessions": [],
        "warnings": warnings or [],
    }


def _update_bucket(acc: list[Any], b_ev: int, b_err: int, b_in: int | None, b_out: int | None) -> None:
    acc[0] += b_ev
    acc[1] += b_err
    if b_in is not None:
        acc[2] = (acc[2] or 0) + b_in
    if b_out is not None:
        acc[3] = (acc[3] or 0) + b_out


def _format_buckets(buckets: dict[int, list[Any]], step: int) -> list[dict[str, Any]]:
    return [
        {
            "startEpochMillis": start,
            "endEpochMillis": start + step,
            "eventCount": acc[0],
            "errorCount": acc[1],
            "inputTokens": acc[2],
            "outputTokens": acc[3],
        }
        for start, acc in buckets.items()
    ]


def _recent_sessions(sessions: list[ParsedSession]) -> list[dict[str, Any]]:
    sorted_sessions = sorted(
        sessions,
        key=lambda s: (
            s.summary.get("updatedAtEpochMillis") or 0,
            s.summary.get("startedAtEpochMillis") or 0,
            s.summary.get("id") or "",
        ),
        reverse=True,
    )
    return [s.summary for s in sorted_sessions[:DASHBOARD_RECENT_SESSION_LIMIT]]


def _aggregate_session_stats(
    sessions: list[ParsedSession], cut_day: int, cut_week: int
) -> tuple[int | None, int | None, int, int, int | None]:
    in_tokens = [int(s.summary["inputTokens"]) for s in sessions if s.summary.get("inputTokens") is not None]
    out_tokens = [int(s.summary["outputTokens"]) for s in sessions if s.summary.get("outputTokens") is not None]
    total_in = sum(in_tokens) if in_tokens else None
    total_out = sum(out_tokens) if out_tokens else None

    activities: list[int] = []
    for s in sessions:
        act = s.counts.get("lastActivityEpochMillis") or s.summary.get("updatedAtEpochMillis")
        if isinstance(act, int):
            activities.append(act)
    act_day = sum(1 for a in activities if a >= cut_day)
    act_week = sum(1 for a in activities if a >= cut_week)
    last_act = max(activities) if activities else None
    return total_in, total_out, act_day, act_week, last_act


def build_dashboard(
    sessions: list[ParsedSession],
    available: bool,
    unavailable_reason: str | None,
    session_state_dir: str,
    warnings: list[str] | None = None,
    clock_millis: int | None = None,
    panel_title: str = "Copilot",
) -> dict[str, Any]:
    if not available:
        return _unavailable_dashboard(unavailable_reason, session_state_dir, warnings)

    now = clock_millis if clock_millis is not None else int(time.time() * 1000)
    cut_day = now - DAY_MILLIS
    cut_week = now - (7 * DAY_MILLIS)
    b_hour = hour_start(now) - ((DASHBOARD_BUCKET_COUNT - 1) * HOUR_MILLIS)
    b_day = day_start(now) - ((DASHBOARD_DAILY_BUCKET_COUNT - 1) * DAY_MILLIS)

    buckets: dict[int, list[Any]] = {
        b_hour + (i * HOUR_MILLIS): [0, 0, None, None] for i in range(DASHBOARD_BUCKET_COUNT)
    }
    daily_buckets: dict[int, list[Any]] = {
        b_day + (i * DAY_MILLIS): [0, 0, None, None] for i in range(DASHBOARD_DAILY_BUCKET_COUNT)
    }

    event_count = sum(s.summary.get("eventCount", 0) for s in sessions)
    turn_count = sum(s.summary.get("turnCount", 0) for s in sessions)
    error_count = sum(s.summary.get("errorCount", 0) for s in sessions)
    drift = sum(1 for s in sessions if s.summary.get("schemaDrift"))

    total_in, total_out, act_day, act_week, last_act = _aggregate_session_stats(sessions, cut_day, cut_week)

    cat_counts: dict[str, int] = {}
    mod_counts: dict[str, int] = {}
    tool_counts: dict[str, int] = {}

    for s in sessions:
        for cat, cnt in s.counts.get("byCategory", {}).items():
            cat_counts[cat] = cat_counts.get(cat, 0) + cnt
        m = s.summary.get("model") or "Unknown"
        mod_counts[m] = mod_counts.get(m, 0) + 1
        for tool, cnt in s.tool_counts.items():
            tool_counts[tool] = tool_counts.get(tool, 0) + cnt
        for b_start, (b_ev, b_err, b_in, b_out) in s.activity_by_hour.items():
            if b_start in buckets:
                _update_bucket(buckets[b_start], b_ev, b_err, b_in, b_out)
            d_start = day_start(b_start)
            if d_start in daily_buckets:
                _update_bucket(daily_buckets[d_start], b_ev, b_err, b_in, b_out)

    top_tools = _metric_counts(tool_counts)[:DASHBOARD_TOP_LIMIT]
    visible_tool_events = sum(t["count"] for t in top_tools)
    all_tool_events = sum(tool_counts.values())

    all_warnings = list(warnings or [])
    if drift > 0:
        all_warnings.append(
            f"{drift} {panel_title} sessions did not match the expected schema; some metrics may be incomplete."
        )

    return {
        "available": True,
        "unavailableReason": None,
        "sessionStateDir": session_state_dir,
        "sessionCount": len(sessions),
        "eventCount": event_count,
        "turnCount": turn_count,
        "totalInputTokens": total_in,
        "totalOutputTokens": total_out,
        "errorCount": error_count,
        "activeLast24Hours": act_day,
        "activeLast7Days": act_week,
        "sessionsWithSchemaDrift": drift,
        "lastActivityEpochMillis": last_act,
        "categoryCounts": _metric_counts(cat_counts),
        "modelCounts": _metric_counts(mod_counts),
        "topTools": top_tools,
        "otherToolEventCount": all_tool_events - visible_tool_events,
        "activityBuckets": _format_buckets(buckets, HOUR_MILLIS),
        "dailyActivityBuckets": _format_buckets(daily_buckets, DAY_MILLIS),
        "recentSessions": _recent_sessions(sessions),
        "warnings": all_warnings,
    }
