"""Lane C-fastapi safety rows (spec §4.4, §5.6): the scan is POST/CLI-only; GETs serve the cached report."""

from __future__ import annotations

# safety-matrix rows (tests/safety/__init__.py): read by the shared route-table tests while the flag is true
PANEL = "fastapi"
GET_ROWS = ["/sharpit/api/fastapi", "/sharpit/api/fastapi/rules/{rule_id}/violations"]
WRITE_ROWS = [("POST", "/sharpit/api/fastapi/scan")]
PATH_PARAMS = {"rule_id": "FASTAPI-ASYNC-002"}
CLI_ACTIONS = ["fastapi_scan"]
