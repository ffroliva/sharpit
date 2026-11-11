from __future__ import annotations

from typing import Any


def build_dashboard(
    sessions: list[Any],
    available: bool,
    unavailable_reason: str | None,
    session_state_dir: str,
    warnings: list[str] | None = None,
    clock_millis: int | None = None,
) -> dict[str, Any]:
    return {
        "available": available,
        "unavailableReason": unavailable_reason,
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
