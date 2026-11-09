"""The ``database-advisor`` panel's MCP/CLI tools (BootUI ``McpToolDescriptions`` rows, 2.2.0).

``get_database_advisor_report`` and ``get_database_advisor_rule_violations`` are reads (MCP and CLI);
``database_advisor_scan`` is an action, so it is CLI-only (spec §14) and refused when the panel or sharpit is
read-only.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.collectors.database_advisor.catalog import SCAN_BUDGET, WALL_MARGIN
from sharpit.engine.collectors.database_advisor.report import DatabaseAdvisorService, run_scan
from sharpit.engine.tools import (
    _ADVISOR_GUIDANCE,  # pyright: ignore[reportPrivateUsage]
    _NONE,  # pyright: ignore[reportPrivateUsage]
    _RULE_VIOLATIONS,  # pyright: ignore[reportPrivateUsage]
    CallContext,
    Tool,
    ToolCallError,
    dismissal_store,
)

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

ASYNC_FROM_CLI = (
    "Scans of async engines run from the panel only: the CLI cannot reach the application's event loop, and an async "
    "engine's pool must not be driven from a second loop."
)


def database_advisor_service(ctx: SharpitContext) -> DatabaseAdvisorService:
    """The per-install advisor, shared by the routes and the tools."""
    return ctx.lazy(
        "database-advisor",
        lambda: DatabaseAdvisorService(
            dismissal_store(ctx), ctx.masker, max_retained=ctx.settings.advisors_max_retained_violations
        ),
    )


def _has_async_engine(ctx: SharpitContext) -> bool:
    registry = ctx.capture.engine_registry
    engines = registry.engines() if registry is not None else []
    return any(getattr(getattr(engine, "dialect", None), "is_async", False) for _name, engine in engines)


def _scan(call: CallContext, _args: dict[str, Any]) -> dict[str, Any]:
    """Tool handlers run on a worker thread: the scan goes to the app's loop when it is running, else a fresh one."""
    ctx = call.ctx
    service = database_advisor_service(ctx)
    loop = ctx.capture.loop
    if loop is not None and loop.is_running() and not loop.is_closed():
        future = asyncio.run_coroutine_threadsafe(run_scan(ctx, service), loop)
        return future.result(SCAN_BUDGET + 2 * WALL_MARGIN + 5)
    if _has_async_engine(ctx):
        return service.scan(ASYNC_FROM_CLI)
    return asyncio.run(run_scan(ctx, service))


def _violations(call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    service = database_advisor_service(call.ctx)
    try:
        return service.violations(args["id"], args["scanId"], args["offset"], args["pageLimit"], args["maxResults"])
    except AdvisorViolationError as exc:  # BootUI: the advisor's status and message, in band
        raise ToolCallError(exc.message, exc.status) from None


_GUIDANCE = _ADVISOR_GUIDANCE.replace("get_rest_api_rule_violations", "get_database_advisor_rule_violations")

TOOLS = (
    Tool(
        "get_database_advisor_report",
        "Return the last completed Database advisor report without querying schema metadata again. Use this cached "
        "evidence before deciding whether an active database_advisor_scan is necessary." + _GUIDANCE,
        _NONE,
        "database-advisor",
        False,
        lambda call, _args: database_advisor_service(call.ctx).report(),
    ),
    Tool(
        "get_database_advisor_rule_violations",
        "Read one page of retained violations for the exact rule id and cached report's violationDetails.scanId. "
        "This never starts a scan or queries the database. Default offset 0 and limit 100; limit is capped at "
        "min(1000, transport max-results). Advance by page.returned while page.hasMore. Unknown rule returns 404; "
        "stale or missing snapshot returns 409: reread the cached report, not a new scan.",
        _RULE_VIOLATIONS,
        "database-advisor",
        False,
        _violations,
    ),
    Tool(
        "database_advisor_scan",
        "Actively introspect the physical database schema (tables, columns, keys, indexes) of every registered "
        "SQLAlchemy engine through a verified read-only connection, plus the engines' pool and driver configuration "
        "against PostgreSQL/MySQL/MariaDB server limits. The scan is bounded; anything it could not read is reported "
        "as a diagnostic rather than as a passing check. Verify findings against the live schema before changing it."
        + _GUIDANCE,
        _NONE,
        "database-advisor",
        True,
        _scan,
    ),
)
COMMANDS = {  # BootUI CliCommandPaths
    "database_advisor_scan": "db scan",
    "get_database_advisor_report": "db report",
    "get_database_advisor_rule_violations": "db violations",
}
