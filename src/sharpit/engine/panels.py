"""Panel registry and ``GET /api/panels`` report (port of BootUI ``BootUiPanels`` and ``PanelDto``)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Panel:
    id: str
    title: str
    action_capable: bool | None
    api_prefix: str | None


# overview and cli register no API prefix, as in BootUI: GET {api}/overview is the shell's chrome data source and the
# CLI endpoints are gated by SHARPIT_CLI_ENABLED, so their panel flags drive only the sidebar entry
PANELS: tuple[Panel, ...] = (
    Panel("overview", "Overview", None, None),
    Panel("config", "Configuration", False, "/config"),
    Panel("mappings", "Mappings", False, "/mappings"),
    Panel("loggers", "Loggers", True, "/loggers"),
    Panel("beans", "Beans", False, "/beans"),
    Panel("vulnerabilities", "Vulnerabilities", True, "/vulnerabilities"),
    Panel("mcp-server", "MCP Server", True, "/mcp-server"),
    Panel("cli", "CLI", None, None),
)


def _env_id(panel_id: str) -> str:
    return panel_id.upper().replace("-", "_")


def disabled_reason(panel_id: str) -> str:
    return f"Panel is disabled via SHARPIT_PANELS_{_env_id(panel_id)}_ENABLED=false"


def read_only_reason(panel_id: str, global_read_only: bool) -> str:
    if global_read_only:
        return "sharpit is read-only via SHARPIT_READ_ONLY=true"
    return f"Panel is read-only via SHARPIT_PANELS_{_env_id(panel_id)}_READ_ONLY=true"


def panel_for_api_path(sub_path: str) -> Panel | None:
    """Panel owning an API path (relative to the API base); ``/mcp`` is deliberately not ``/mcp-server``."""
    for p in PANELS:
        if p.api_prefix and (sub_path == p.api_prefix or sub_path.startswith(p.api_prefix + "/")):
            return p
    return None


def panels_report(
    global_read_only: bool,
    panel_flags: Mapping[str, tuple[bool, bool]],
    available: Mapping[str, str | None],
) -> dict[str, Any]:
    """``panel_flags[id]`` is ``(enabled, read_only)``; ``available[id]`` None = available."""
    panels: list[dict[str, Any]] = []
    for p in PANELS:
        enabled, panel_ro = panel_flags.get(p.id, (True, False))
        read_only = bool(p.action_capable) and (global_read_only or panel_ro)
        reason = available.get(p.id)
        panels.append(
            {
                "id": p.id,
                "title": p.title,
                "available": reason is None,
                "unavailableReason": reason,
                "enabled": enabled,
                "readOnly": read_only,
                "readOnlyReason": read_only_reason(p.id, global_read_only) if read_only else None,
            }
        )
    return {"platform": "fastapi", "panels": panels}
