from __future__ import annotations

from importlib import import_module
from typing import Any

from . import (
    ai,
    architecture,
    cache,
    claude_code,
    code_inventory,
    code_paths,
    copilot,
    data,
    database_advisor,
    dev_services,
    fastapi,
    fastapi_security,
    github,
    java_agent,
    metrics,
    mysql,
    postgresql,
    profile_diff,
    runtime_insights,
    scheduled,
    security,
    security_logs,
    side_effects,
    sqlalchemy_statistics,
    startup,
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
    "metrics": metrics.IMPLEMENTED,
    "startup": startup.IMPLEMENTED,
    "profile-diff": profile_diff.IMPLEMENTED,
    "scheduled": scheduled.IMPLEMENTED,
    "copilot": copilot.IMPLEMENTED,
    "claude-code": claude_code.IMPLEMENTED,
    "github": github.IMPLEMENTED,
    "ai": ai.IMPLEMENTED,
    "java-agent": java_agent.IMPLEMENTED,
    "code-inventory": code_inventory.IMPLEMENTED,
    "code-paths": code_paths.IMPLEMENTED,
    "side-effects": side_effects.IMPLEMENTED,
    "cache": cache.IMPLEMENTED,
    "dev-services": dev_services.IMPLEMENTED,
    "runtime-insights": runtime_insights.IMPLEMENTED,
}
PANEL_04_IDS = tuple(IMPLEMENTED)
# panels with per-panel route/tool modules (fastapi/routes/<id>.py, engine/tools04/<id>.py): every 0.4 id plus the
# existing sql-trace panel, which A-sqltrace-insights extends without editing shared files
MODULE_PANEL_IDS = (*PANEL_04_IDS, "sql-trace")


def module_implemented(panel_id: str) -> bool:
    """A 0.4 panel's own flag; the existing ``sql-trace`` panel is always implemented."""
    return IMPLEMENTED.get(panel_id, True)


def tool_definitions() -> tuple[tuple[Any, ...], dict[str, str]]:
    tools: list[Any] = []
    commands: dict[str, str] = {}
    for panel_id in MODULE_PANEL_IDS:
        if not module_implemented(panel_id):
            continue
        module = import_module(f"sharpit.engine.tools04.{panel_id.replace('-', '_')}")
        tools.extend(module.TOOLS)
        commands.update(getattr(module, "COMMANDS", {}))
    return tuple(tools), commands
