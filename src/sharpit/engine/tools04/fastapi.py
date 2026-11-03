"""The ``fastapi`` advisor's MCP/CLI tools (BootUI ``McpToolCatalog`` spring rows, 2.2.0; WAVE-B §1, §7).

``get_fastapi_report`` and ``get_fastapi_rule_violations`` are reads (MCP and CLI); ``fastapi_scan`` is an action,
so it is CLI-only (spec §14) and refused when the panel or sharpit is read-only.
"""

from __future__ import annotations

from typing import Any

from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.collectors.fastapi_advisor.report import FastapiAdvisor, scan_app
from sharpit.engine.context import SharpitContext
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.tools import CallContext, Tool, ToolCallError, dismissal_store

_NONE: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}
_RULE_VIOLATIONS: dict[str, Any] = {  # BootUiMcpService.schema RULE_VIOLATIONS (as engine/tools.py)
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Exact identifier of the resource to fetch.", "minLength": 1},
        "scanId": {
            "type": "string",
            "minLength": 1,
            "description": "The cached report's violationDetails.scanId. Never starts a scan.",
        },
        "offset": {"type": "integer", "minimum": 0, "default": 0},
        "limit": {
            "type": "integer",
            "minimum": 1,
            "description": "Page size, default 100, capped at min(1000, SHARPIT_MCP_MAX_RESULTS).",
            "default": 100,
        },
    },
    "required": ["id", "scanId"],
    "additionalProperties": False,
}
_GUIDANCE = (  # McpToolDescriptions.advisorGuidance
    " sampleViolations are bounded previews (up to 10), not the full violationCount. Use violationDetails.scanId "
    "with get_fastapi_rule_violations to page cached retained details without scanning again. Check truncated for "
    "missing details, including retention overflow; a terminal page does not guarantee completeness when truncated. "
    "Verify each finding before changing code."
)


def fastapi_service(ctx: SharpitContext) -> FastapiAdvisor:
    """The per-install FastAPI advisor; a scan reads the app's source, a report never does."""
    return ctx.lazy(
        "fastapi-advisor",
        lambda: FastapiAdvisor(
            lambda _request: scan_app(ctx.introspector, ctx.settings),
            dismissal_store(ctx),
            ctx.masker,
            ctx.lazy("singleflight:fastapi-scan", SingleFlight),
            max_retained=ctx.settings.advisors_max_retained_violations,
        ),
    )


def _violations(call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return fastapi_service(call.ctx).violations(
            args["id"], args["scanId"], args["offset"], args["pageLimit"], args["maxResults"]
        )
    except AdvisorViolationError as exc:  # BootUI: the advisor's status and message, in band
        raise ToolCallError(exc.message, exc.status) from None


TOOLS = (
    Tool(
        "get_fastapi_report",
        "Return the last completed FastAPI advisor report without starting a new scan. Use this cached evidence "
        "before deciding whether an active fastapi_scan is necessary." + _GUIDANCE,
        _NONE,
        "fastapi",
        False,
        lambda call, _args: fastapi_service(call.ctx).report(),
    ),
    Tool(
        "get_fastapi_rule_violations",
        "Read one page of retained violations for the exact rule id and cached report's violationDetails.scanId. "
        "This never starts a scan. Default offset 0 and limit 100; limit is capped at min(1000, transport "
        "max-results). Advance by page.returned while page.hasMore; page.total and page.matched count retained "
        "entries, not violationCount. If truncated, retention overflow or unavailable upstream details prevent a "
        "complete list. Verify each finding before changing code. Unknown rule returns 404; stale or missing "
        "snapshot returns 409: reread the cached report, not a new scan.",
        _RULE_VIOLATIONS,
        "fastapi",
        False,
        _violations,
    ),
    Tool(
        "fastapi_scan",
        "Actively inspect this application's route handlers and source for FastAPI correctness and performance "
        "risks. Verify each finding against the application's requirements before changing code." + _GUIDANCE,
        _NONE,
        "fastapi",
        True,
        lambda call, _args: fastapi_service(call.ctx).scan(),
    ),
)
COMMANDS = {
    "get_fastapi_report": "fastapi report",
    "get_fastapi_rule_violations": "fastapi violations",
    "fastapi_scan": "fastapi scan",
}
