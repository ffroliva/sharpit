from __future__ import annotations

PANEL = "copilot"
GET_ROWS = [
    "/sharpit/api/copilot/sessions",
    "/sharpit/api/copilot/dashboard",
    "/sharpit/api/copilot/sessions/{id}",
    "/sharpit/api/copilot/sessions/{id}/events",
    "/sharpit/api/copilot/sessions/{id}/events/{eventId}/raw",
]
WRITE_ROWS: list[tuple[str, str]] = []
PATH_PARAMS = {"id": "s1", "eventId": "e1"}
