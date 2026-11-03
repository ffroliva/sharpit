from __future__ import annotations

from typing import Any

from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.collectors.architecture.report import architecture_service
from sharpit.engine.tools import CallContext, Tool, ToolCallError

_NONE: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}
_RULE_VIOLATIONS = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "The exact rule id, e.g. ARCH-PKG-001."},
        "scanId": {
            "type": "string",
            "description": "The cached report's violationDetails.scanId; stale or missing returns 409.",
        },
        "offset": {"type": "integer", "minimum": 0, "default": 0, "description": "0-based start index."},
        "pageLimit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000,
            "default": 100,
            "description": "Page size, capped by transport max-results.",
        },
        "maxResults": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000,
            "default": 1000,
            "description": "Transport budget cap.",
        },
    },
    "required": ["id"],
    "additionalProperties": False,
}
_ADVISOR_GUIDANCE = (
    " Inspect scan.status, scan.message and evidence before changing code or deciding whether an active "
    "architecture_scan is necessary."
)


def _architecture_violations(call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    service = architecture_service(call.ctx)
    try:
        return service.violations(
            args["id"],
            args.get("scanId"),
            args.get("offset"),
            args.get("pageLimit"),
            args.get("maxResults", 1000),
        )
    except AdvisorViolationError as exc:
        raise ToolCallError(exc.message, exc.status) from None


TOOLS = (
    Tool(
        "get_architecture_report",
        "Return the last completed Architecture advisor report without starting a new scan. Use this cached evidence "
        "before deciding whether an active architecture_scan is necessary." + _ADVISOR_GUIDANCE,
        _NONE,
        "architecture",
        False,
        lambda c, _a: architecture_service(c.ctx).report(),
    ),
    Tool(
        "get_architecture_rule_violations",
        "Read one page of retained violations for the exact rule id and cached report's violationDetails.scanId. "
        "This never starts a scan. Default offset 0 and limit 100; limit is capped at min(1000, transport "
        "max-results). Advance by page.returned while page.hasMore; page.total and page.matched count retained "
        "entries, not violationCount. If truncated, retention overflow or unavailable upstream details prevent a "
        "complete list. Verify each finding before changing code. Unknown rule returns 404; stale or missing "
        "snapshot returns 409: reread the cached report, not a new scan. On MCP -32003 byte-budget refusal, retry "
        "the same scanId and offset with a smaller limit; a refusal is not an empty or completed page.",
        _RULE_VIOLATIONS,
        "architecture",
        False,
        _architecture_violations,
    ),
    Tool(
        "architecture_scan",
        "Actively inspect this application's import graph and package structure for architecture rule violations and "
        "contract failures." + _ADVISOR_GUIDANCE,
        _NONE,
        "architecture",
        True,
        lambda c, _a: architecture_service(c.ctx).scan(),
    ),
)

COMMANDS = {
    "get_architecture_report": "architecture report",
    "get_architecture_rule_violations": "architecture violations",
    "architecture_scan": "architecture scan",
}
