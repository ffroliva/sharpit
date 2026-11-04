"""Lane D4: the compacted MCP vulnerability view masks secrets in its free text (AGENTS.md safety model 3).

An OSV failure message can carry a proxy URL with credentials; advisory text is external input.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.engine.tools import CallContext, call_tool
from sharpit.settings import load_settings

SECRET = "hunter2sharpitd4"


class _Introspector:
    def app_info(self) -> AppInfo:
        return AppInfo("demo", "FastAPI", "0.115.0", None)

    def routes(self) -> list[RouteInfo]:
        return []

    def providers(self) -> list[ProviderInfo]:
        return []


class _Service:
    def report(self) -> dict[str, Any]:
        vuln = {
            "id": "GHSA-1",
            "summary": f"password={SECRET}",
            "details": f"token={SECRET}",
            "aliases": [],
            "references": [],
            "fixedVersions": [],
        }
        return {
            "scan": {"status": "ERROR", "message": f"OSV scan failed: proxy password={SECRET}"},
            "dependencies": [{"packageName": "jinja2", "vulnerabilityCount": 1, "vulnerabilities": [vuln]}],
        }


def test_mcp_compaction_masks(monkeypatch: pytest.MonkeyPatch):
    from sharpit.engine import tools

    monkeypatch.setattr(tools, "vulnerability_service", lambda _ctx: _Service())
    settings = load_settings({"config_scan": False}, {})
    ctx = SharpitContext(settings, ActivationStatus(True, True, "on", ()), _Introspector())
    out = call_tool(CallContext(ctx, {}), "get_vulnerabilities_report", {}, via="mcp")
    assert SECRET not in json.dumps(out)
