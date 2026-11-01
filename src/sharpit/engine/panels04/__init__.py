from __future__ import annotations

from importlib import import_module
from typing import Any

from . import (
    architecture,
    data,
    database_advisor,
    fastapi,
    fastapi_security,
    mysql,
    postgresql,
    security,
    security_logs,
    sqlalchemy_statistics,
    traces,
    transactions,
)

IMPLEMENTED = {
    "data": data.IMPLEMENTED,
    "transactions": transactions.IMPLEMENTED,
    "postgresql": postgresql.IMPLEMENTED,
    "mysql": mysql.IMPLEMENTED,
    "traces": traces.IMPLEMENTED,
    "security": security.IMPLEMENTED,
    "security-logs": security_logs.IMPLEMENTED,
    "database-advisor": database_advisor.IMPLEMENTED,
    "architecture": architecture.IMPLEMENTED,
    "sqlalchemy-statistics": sqlalchemy_statistics.IMPLEMENTED,
    "fastapi-security": fastapi_security.IMPLEMENTED,
    "fastapi": fastapi.IMPLEMENTED,
}
PANEL_04_IDS = tuple(IMPLEMENTED)


def tool_definitions() -> tuple[tuple[Any, ...], dict[str, str]]:
    tools: list[Any] = []
    commands: dict[str, str] = {}
    for panel_id, implemented in IMPLEMENTED.items():
        if not implemented:
            continue
        module = import_module(f"sharpit.engine.tools04.{panel_id.replace('-', '_')}")
        tools.extend(module.TOOLS)
        commands.update(getattr(module, "COMMANDS", {}))
    return tuple(tools), commands
