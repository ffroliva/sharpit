"""The ``security`` advisor's MCP read tools and CLI-only scan (WAVE-B §1, §2; ``security_scan`` is CLI-only, §14)."""

from __future__ import annotations

from typing import Any

from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.collectors.appsecurity import model_of
from sharpit.engine.collectors.security import Inputs
from sharpit.engine.collectors.security.report import SecurityService, build_inputs
from sharpit.engine.context import SharpitContext
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.spi import SecurityFacts, SecurityModel
from sharpit.engine.tools import (
    _NONE,  # pyright: ignore[reportPrivateUsage]
    _RULE_VIOLATIONS,  # pyright: ignore[reportPrivateUsage]
    CallContext,
    Tool,
    ToolCallError,
    dismissal_store,
)

_NO_ADAPTER = "This framework adapter does not expose security details."
_GUIDANCE = (  # McpToolDescriptions.advisorGuidance
    " sampleViolations are bounded previews (up to 10), not the full violationCount. Use violationDetails.scanId "
    "with get_security_rule_violations to page cached retained details without scanning again. Check truncated for "
    "missing details, including retention overflow; a terminal page does not guarantee completeness when truncated. "
    "Verify each finding before changing code."
)


def _facts(ctx: SharpitContext) -> SecurityFacts:
    read: Any = getattr(ctx.introspector, "security_facts", None)  # duck-typed: not on the AppIntrospector port
    if not callable(read):
        return SecurityFacts(False, None, (), (), (_NO_ADAPTER,))
    try:
        facts = read()
    except Exception as exc:  # noqa: BLE001 - introspection degrades; never crashes the host (safety 5)
        return SecurityFacts(False, None, (), (), (f"Middleware options could not be read ({type(exc).__name__}).",))
    return facts if isinstance(facts, SecurityFacts) else SecurityFacts(False, None, (), (), (_NO_ADAPTER,))


def _inputs(ctx: SharpitContext) -> Inputs:
    model = model_of(ctx) or SecurityModel(False, (), (), (), (_NO_ADAPTER,))
    return build_inputs(model, _facts(ctx), getattr(ctx.introspector, "app", None), ctx.settings)


def security_service(ctx: SharpitContext) -> SecurityService:
    """The per-install security advisor (seeded in tests under the same key); nothing is read before a scan."""
    return ctx.lazy(
        "security",
        lambda: SecurityService(
            lambda: _inputs(ctx),
            dismissal_store(ctx),
            ctx.masker,
            ctx.lazy("singleflight:security-scan", SingleFlight),
            max_retained=ctx.settings.advisors_max_retained_violations,
        ),
    )


def _violations(call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    service = security_service(call.ctx)
    try:
        return service.violations(args["id"], args["scanId"], args["offset"], args["pageLimit"], args["maxResults"])
    except AdvisorViolationError as exc:  # BootUI: the advisor's status and message, in band
        raise ToolCallError(exc.message, exc.status) from None


TOOLS = (
    Tool(
        "get_security_report",
        "Return the last completed Security advisor report without starting a new configuration scan. Use this "
        "cached evidence before deciding whether an active security_scan is necessary." + _GUIDANCE,
        _NONE,
        "security",
        False,
        lambda c, _a: security_service(c.ctx).report(),
    ),
    Tool(
        "get_security_rule_violations",
        "Read one page of retained violations for the exact rule id and cached report's violationDetails.scanId. "
        "This never starts a scan. Default offset 0 and limit 100; limit is capped at min(1000, transport "
        "max-results). Advance by page.returned while page.hasMore; page.total and page.matched count retained "
        "entries, not violationCount. If truncated, retention overflow or unavailable upstream details prevent a "
        "complete list. Verify each finding before changing code. Unknown rule returns 404; stale or missing "
        "snapshot returns 409: reread the cached report, not a new scan.",
        _RULE_VIOLATIONS,
        "security",
        False,
        _violations,
    ),
    Tool(
        "security_scan",
        "Actively review application security configuration and return prioritized findings. Treat results as "
        "review evidence and verify exploitability before proposing a fix." + _GUIDANCE,
        _NONE,
        "security",
        True,
        lambda c, _a: security_service(c.ctx).scan(),
    ),
)
COMMANDS = {
    "get_security_report": "security report",
    "get_security_rule_violations": "security violations",
    "security_scan": "security scan",
}
