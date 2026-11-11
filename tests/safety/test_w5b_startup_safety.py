from __future__ import annotations

PANEL = "startup"
GET_ROWS = ["/sharpit/api/startup"]
WRITE_ROWS: list[tuple[str, str]] = []
TOOL_SEEDS = {"get_startup_timeline": lambda _ctx: {}}
