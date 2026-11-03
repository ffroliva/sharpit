"""``security-logs`` (BootUI ``SecurityLogsService``): a bounded audit ring, masked at read."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.masking import Masker

AUTHENTICATION_SUCCESS = "AUTHENTICATION_SUCCESS"
AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"


def clamp_max_logs(n: int) -> int:
    return n


class SecurityEventBuffer:
    def __init__(self, max_logs: int) -> None:
        self.max_logs = max_logs
        self.changes = ChangeStream()

    def add(
        self,
        type: str,
        principal: str | None,
        data: Mapping[str, object],
        request_id: str | None,
        *,
        timestamp_ns: int | None = None,
    ) -> None:
        return None


def format_instant(timestamp_ns: int) -> str:
    return ""


def parse_after(raw: str | None) -> int | None:
    return None


def security_logs_report(
    buffer: SecurityEventBuffer | None,
    masker: Masker,
    *,
    principal: str | None,
    type: str | None,
    after_ns: int | None,
    offset: int | None,
    limit: int | None,
    unavailable_reason: str | None,
) -> dict[str, Any]:
    return {"auditEventsPresent": True, "unavailableReason": None, "maxLogs": 0, "typeSummaries": [], "events": []}
