"""Stub (red): the report service."""

from __future__ import annotations

from sharpit.engine.collectors.insights.registry import KINDS

DISABLED = ""


def id_of(kind: str, key: str) -> str:
    return kind + key


class InsightsService:
    def __init__(self, journal: object, observations: object = None) -> None:
        self.journal = journal
        self.observations = observations

    def report(self) -> dict[str, object]:
        window = dict.fromkeys(("runId", "firstEventAt", "lastEventAt", "retainedEvents", "requests", "evictedEvents", "droppedEvents"))
        checks = [
            dict.fromkeys(("status", "eligibleRequests", "findings", "reason"), "X") | {"kind": k.kind, "title": k.title}
            for k in KINDS
        ]
        check = dict.fromkeys(("kind", "title", "status", "eligibleRequests", "findings", "reason"))
        coverage = dict.fromkeys(("source", "events", "byRequestId", "byExecutionId", "byTraceId", "unlinked", "dropped"))
        row = dict.fromkeys(("id", "kind", "subject", "status", "sentence", "eligible", "affected", "minimumTier", "whatToCheck", "exemplarRequestIds", "evidenceRows", "limitations", "listed", "unlistedReason"))
        return {
            "available": False, "unavailableReason": None, "window": window, "coverage": [coverage],
            "checks": checks, "observations": [row], "limitations": [], "notExercised": [], "notExercisedOmitted": 0,
        }
