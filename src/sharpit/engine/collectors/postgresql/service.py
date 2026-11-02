"""The ``postgresql`` panel's report (red stub)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

OPERATION = "postgresql-read"
_clock = time.monotonic

Dto = dict[str, Any]


@dataclass
class PostgresState:
    report: Dto | None = None
    previous: dict[str, Any] = field(default_factory=lambda: {})


def postgresql_report(ctx: SharpitContext) -> Dto:
    del ctx
    return {"status": "", "readAt": 0, "databases": [{}], "diagnostics": [], "limitations": []}


async def refresh_postgresql(ctx: SharpitContext) -> Dto:
    del ctx
    sections = [{"id": i, "status": "", "reason": ""} for i in ("statements", "sessions", "indexes", "tables")]
    database = {
        "status": "",
        "monitoringRole": True,
        "sections": sections,
        "changes": [None],
        "statements": [],
        "message": "",
    }
    return {"status": "", "message": "", "readAt": 0, "databasesRead": 0, "databases": [database], "diagnostics": [],
            "limitations": []}  # fmt: skip
