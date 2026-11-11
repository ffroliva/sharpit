from __future__ import annotations

PANEL = "claude-code"
GET_ROWS = [
    "/sharpit/api/claude-code/sessions",
    "/sharpit/api/claude-code/dashboard",
    "/sharpit/api/claude-code/sessions/{id}",
    "/sharpit/api/claude-code/sessions/{id}/events",
    "/sharpit/api/claude-code/sessions/{id}/events/{eventId}/raw",
    "/sharpit/api/claude-code/stream",
]
WRITE_ROWS: list[tuple[str, str]] = []
PATH_PARAMS = {"id": "s1", "eventId": "e1"}
