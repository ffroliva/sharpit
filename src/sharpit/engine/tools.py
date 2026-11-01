"""Tool catalogue and dispatcher shared by the MCP server and the CLI endpoints.

Port of BootUI ``McpToolCatalog`` (the seven MVP rows), ``McpToolSchema`` rendered as in ``BootUiMcpService.schema``,
``McpToolDescriptions``, ``McpArguments.normalize``, ``McpDispatcher.callTool``, ``CliService`` and ``CliOutcomes``.
MCP never sees an action tool (``vulnerabilities_scan`` and ``rest_api_scan`` are CLI-only, spec §9). Each ``via``
has its own caps, slots and counters, as BootUI's MCP and CLI each own a dispatcher.

Timeout: Python threads cannot be interrupted (BootUI cancels the future), so the call's slot is released exactly
once, by whichever comes first of the worker finishing or the caller giving up; an abandoned worker runs on.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from sharpit.engine import sqla
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.capture import activity
from sharpit.engine.capture.exceptions import unknown_group
from sharpit.engine.capture.exchanges import unavailable_report
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.capture.sqltrace import unavailable_report as sql_trace_unavailable
from sharpit.engine.collectors.alembic import alembic_report
from sharpit.engine.collectors.beans import beans_report
from sharpit.engine.collectors.config import config_report
from sharpit.engine.collectors.health import health_service
from sharpit.engine.collectors.loggers import loggers_report
from sharpit.engine.collectors.mappings import mappings_flat
from sharpit.engine.collectors.overview import overview_dto
from sharpit.engine.collectors.pools import pools_report
from sharpit.engine.collectors.restapi.service import RestApiService
from sharpit.engine.collectors.threads import threads_report
from sharpit.engine.collectors.vulns.epss import EpssClient
from sharpit.engine.collectors.vulns.inventory import inventory
from sharpit.engine.collectors.vulns.osv import OsvClient
from sharpit.engine.collectors.vulns.service import VulnerabilityService
from sharpit.engine.context import SharpitContext
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.sources import sqlite
from sharpit.engine.spi import ApiModel

Via = Literal["mcp", "cli"]

# JSON-RPC codes (McpProtocol)
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SERVER_DISABLED = -32000
SERVER_AT_CAPACITY = -32001
TOOL_TIMEOUT = -32002
RESPONSE_TOO_LARGE = -32003
INTERNAL_ERROR_MESSAGE = "Internal error"
UNKNOWN_TOOL_PREFIX = "Unknown tool: "

SERVER_NAME = "sharpit"
CLI_DISABLED_MESSAGE = "sharpit CLI endpoint is disabled. Set SHARPIT_CLI_ENABLED=true to allow command-line access."


class RpcError(Exception):
    """A JSON-RPC protocol error (``McpDispatchOutcome.ProtocolError``)."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ToolCallError(Exception):
    """An in-band refusal (MCP ``isError:true``); ``status`` is the HTTP status the CLI answers with."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(frozen=True)
class CallContext:
    ctx: SharpitContext
    scope: Mapping[str, object]  # the HTTP request scope: get_overview reads serverPort/contextPath from it


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    panel: str
    action: bool
    handler: Callable[[CallContext, dict[str, Any]], dict[str, Any]]


# --- Schemas (BootUiMcpService.schema) ------------------------------------------------------------------------------

_LIMIT: dict[str, Any] = {
    "type": "integer",
    "minimum": 1,
    "description": "Optional maximum number of items to return. Capped by the SHARPIT_MCP_MAX_RESULTS server limit.",
}
_NONE: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}
_QUERY_LIMIT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional case-insensitive filter applied to the results."},
        "limit": _LIMIT,
    },
    "additionalProperties": False,
}
_LIMIT_ONLY: dict[str, Any] = {"type": "object", "properties": {"limit": _LIMIT}, "additionalProperties": False}
_ID: dict[str, Any] = {
    "type": "object",
    "properties": {"id": {"type": "string", "description": "Exact identifier of the resource to fetch."}},
    "required": ["id"],
    "additionalProperties": False,
}
_RULE_VIOLATIONS: dict[str, Any] = {  # BootUiMcpService.schema RULE_VIOLATIONS
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
_SCHEMA_NAMES = {
    (): "NONE",
    ("limit",): "LIMIT",
    ("query", "limit"): "QUERY_LIMIT",
    ("id",): "ID",
    ("id", "scanId", "offset", "limit"): "RULE_VIOLATIONS",
}


_ADVISOR_GUIDANCE = (  # McpToolDescriptions.advisorGuidance
    " sampleViolations are bounded previews (up to 10), not the full violationCount. Use violationDetails.scanId "
    "with get_rest_api_rule_violations to page cached retained details without scanning again. Check truncated for "
    "missing details, including retention overflow; a terminal page does not guarantee completeness when truncated. "
    "Verify each finding before changing code."
)


# --- Handlers (BootUiMcpTools) --------------------------------------------------------------------------------------


def vulnerability_service(ctx: SharpitContext) -> VulnerabilityService:
    """The per-install service, shared by the REST routes and the tools (seeded in tests under the same key)."""
    settings = ctx.settings
    timeout = settings.vulnerabilities_request_timeout
    return ctx.lazy(
        "vulnerabilities",
        lambda: VulnerabilityService(
            settings,
            OsvClient(settings.vulnerabilities_osv_base_uri, timeout),
            EpssClient(settings.vulnerabilities_epss_base_uri, timeout),
            inventory,
            dismissal_store(ctx),
            ctx.single_flight,
        ),
    )


def dismissal_store(ctx: SharpitContext) -> DismissalStore:
    """The one per-install store every advisor and the dismissed-rules routes share."""
    return ctx.lazy("dismissals", lambda: DismissalStore(Path(ctx.settings.state_dir)))


_NO_ROUTE_MODEL = ApiModel((), (), ("This framework adapter does not expose route details.",))


def rest_api_service(ctx: SharpitContext) -> RestApiService:
    """The per-install REST API advisor (seeded in tests under the same key); scans hold their own single-flight."""
    source: Any = getattr(ctx.introspector, "api_model", None)  # duck-typed: not part of the AppIntrospector SPI
    model = cast("Callable[[], ApiModel]", source) if callable(source) else (lambda: _NO_ROUTE_MODEL)
    return ctx.lazy(
        "rest-api",
        lambda: RestApiService(
            model,
            dismissal_store(ctx),
            ctx.masker,
            ctx.lazy("singleflight:rest-api-scan", SingleFlight),
            max_retained=ctx.settings.advisors_max_retained_violations,
        ),
    )


def _rest_api_violations(call: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    service = rest_api_service(call.ctx)
    try:
        return service.violations(args["id"], args["scanId"], args["offset"], args["pageLimit"], args["maxResults"])
    except AdvisorViolationError as exc:  # BootUI: the advisor's status and message, in band
        raise ToolCallError(exc.message, exc.status) from None


def exceptions_report(ctx: SharpitContext) -> dict[str, Any]:
    """``ExceptionsReport``; empty and unavailable when exception capture is not installed for this context."""
    store = ctx.capture.exceptions
    if store is None:
        return {
            "available": False,
            "unavailableReason": "Exception capture is not installed",
            "maxGroups": ctx.settings.exceptions_max_groups,
            "totalExceptions": 0,
            "groups": [],
        }
    return store.report()


def exception_detail(ctx: SharpitContext, gid: str) -> dict[str, Any]:
    store = ctx.capture.exceptions
    detail = store.detail(gid) if store is not None else None
    if detail is None:
        raise ToolCallError(unknown_group(gid), 404)
    return detail


def clear_exceptions(ctx: SharpitContext) -> dict[str, Any]:
    if ctx.capture.exceptions is not None:
        ctx.capture.exceptions.clear()
    return {"cleared": True}


def _sqlite3_traced(ctx: SharpitContext) -> bool:
    """The raw sqlite3 source feeds this context: its own switch is on and the patch is in (any holder's)."""
    return ctx.settings.sql_trace_sqlite3_enabled and sqlite.is_attached()


def sql_trace_unavailable_reason(ctx: SharpitContext) -> str | None:
    """Why SQL Trace shows nothing: tracing switched off, or SQLAlchemy 2.0+ not imported by the app."""
    if not ctx.settings.sql_trace_enabled:
        return sqla.TRACING_DISABLED
    return None if _sqlite3_traced(ctx) else sqla.unavailable_reason()


def sql_trace_report(ctx: SharpitContext) -> dict[str, Any]:
    """``SqlTraceReport``; unavailable while tracing is off or SQLAlchemy is not imported."""
    recorder = ctx.capture.sql_trace
    reason = sql_trace_unavailable_reason(ctx)
    if recorder is None or reason is not None:
        return sql_trace_unavailable(reason or sqla.TRACING_DISABLED)
    registry = ctx.capture.engine_registry
    sources = registry.names() if registry is not None else []
    traced = _sqlite3_traced(ctx)
    if traced:
        sources = [*sources, "sqlite3"]
    report = recorder.report(sources)
    report["warnings"] = [*report["warnings"], *(sqlite.limitations() if traced else [])]
    return report


def _sql_trace_action(ctx: SharpitContext, action: Callable[[SqlTraceRecorder], None]) -> dict[str, Any]:
    if ctx.capture.sql_trace is not None:
        action(ctx.capture.sql_trace)
    return sql_trace_report(ctx)


def http_exchanges_report(
    ctx: SharpitContext,
    q: str | None,
    method: str | None,
    status_class: str | None,
    offset: int | None,
    limit: int | None,
) -> dict[str, Any]:
    """``HttpExchangesReport``; unavailable when request capture is not installed for this context."""
    buffer = ctx.capture.exchanges
    if buffer is None:
        return unavailable_report("Request capture is not installed")
    return buffer.report(q, method, status_class, offset, limit)


def log_tail_lines(ctx: SharpitContext) -> list[dict[str, Any]]:
    """``LogLineDto[]``, oldest first; empty when the panel is disabled (no buffer)."""
    buffer = ctx.capture.log_tail
    return [] if buffer is None else buffer.recent()


_BASE_TOOLS: tuple[Tool, ...] = (
    Tool(
        "get_overview",
        "Return stable application identity and runtime context, including versions, active profiles, and "
        "sharpit status. Use this before interpreting other results.",
        _NONE,
        "overview",
        False,
        lambda c, _a: overview_dto(c.ctx, c.scope),
    ),
    Tool(
        "get_config",
        "Search effective configuration by name or displayed value and return a bounded result. Name "
        "search is relaxed-binding aware: it ignores case and treats `_` and `-` as `.`, so the "
        "dotted, kebab-case, and `UPPER_SNAKE_CASE` spellings of one property all find it — "
        "`sharpit.mcp.enabled` also finds a value supplied as the environment variable "
        "`SHARPIT_MCP_ENABLED`, which is enumerated under that literal name. Values are matched "
        "literally, and each row reports the exact name and source its property source published. "
        "In `page`, `total` counts every property before filtering while `matched` counts the "
        "query hits, so `matched: 0` means this query found nothing, not that the property is "
        "absent — retry with a shorter query before concluding it is unset. Secret-like "
        "configuration values are masked; prefer a narrow query.",
        _QUERY_LIMIT,
        "config",
        False,
        lambda c, a: config_report(c.ctx, a["query"], None, False, None, a["limit"]),
    ),
    Tool(
        "get_mappings",
        "Search request routes and handlers and return a bounded result. Use a path, HTTP concept, or handler "
        "name as the query when locating an endpoint.",
        _QUERY_LIMIT,
        "mappings",
        False,
        lambda c, a: mappings_flat(c.ctx, a["query"], None, a["limit"]),
    ),
    Tool(
        "get_loggers",
        "Search configured loggers by case-insensitive name and return their configured and effective "
        "levels, bounded by limit. Use to confirm actual logging levels before or after a code or "
        "configuration change.",
        _QUERY_LIMIT,
        "loggers",
        False,
        lambda _c, a: loggers_report(a["query"], None, a["limit"]),
    ),
    Tool(
        "get_beans",
        "Search FastAPI beans (dependency providers, middleware and the lifespan handler) by name or type and "
        "return a bounded result. Use this to verify runtime wiring, not as proof that a bean is exercised.",
        _QUERY_LIMIT,
        "beans",
        False,
        lambda c, a: beans_report(c.ctx, a["query"], None, None, a["limit"]),
    ),
    Tool(
        "get_http_exchanges",
        "Return a bounded, newest-first snapshot of the HTTP requests this application served: method, masked "
        "path and query, status, duration, response size and masked headers. sharpit's own requests are counted "
        "in `hiddenSelf`, not listed.",
        _LIMIT_ONLY,
        "http-exchanges",
        False,
        lambda c, a: http_exchanges_report(c.ctx, None, None, None, None, a["limit"]),
    ),
    Tool(
        "get_log_tail",
        "Return the latest buffered application log snapshot, oldest first. Messages are masked at capture, but logs "
        "are application-controlled and may contain sensitive data; use them only in the local diagnostic context.",
        _NONE,
        "log-tail",
        False,
        lambda c, _a: {"entries": log_tail_lines(c.ctx)},
    ),
    Tool(
        "get_exceptions",
        "List recent exception groups, newest first. Use a returned id with get_exception_detail for stack frames, "
        "causes, and individual occurrences.",
        _NONE,
        "exceptions",
        False,
        lambda c, _a: exceptions_report(c.ctx),
    ),
    Tool(
        "get_exception_detail",
        "Return stack frames, causes, and occurrences for one exact exception-group id obtained from get_exceptions "
        "or get_live_activity.",
        _ID,
        "exceptions",
        False,
        lambda c, a: exception_detail(c.ctx, a["id"]),
    ),
    Tool(
        "clear_exceptions",
        "Clear sharpit's bounded in-memory exception groups and occurrences. This does not suppress, handle, or "
        "change application exceptions.",
        _NONE,
        "exceptions",
        True,
        lambda c, _a: clear_exceptions(c.ctx),
    ),
    Tool(
        "get_sql_traces",
        "Return the current bounded SQL trace snapshot with statements and timings. Application SQL may contain "
        "sensitive values; correlate it locally with request or trace identifiers.",
        _NONE,
        "sql-trace",
        False,
        lambda c, _a: sql_trace_report(c.ctx),
    ),
    Tool(
        "clear_sql_traces",
        "Clear the bounded in-memory SQL trace buffer and return the resulting report. This does not execute SQL or "
        "change whether trace recording is enabled.",
        _NONE,
        "sql-trace",
        True,
        lambda c, _a: _sql_trace_action(c.ctx, SqlTraceRecorder.clear),
    ),
    Tool(
        "pause_sql_trace_recording",
        "Pause SQL trace recording and return the resulting report. Existing buffered traces remain available until "
        "explicitly cleared.",
        _NONE,
        "sql-trace",
        True,
        lambda c, _a: _sql_trace_action(c.ctx, lambda r: r.set_recording(False)),
    ),
    Tool(
        "resume_sql_trace_recording",
        "Resume SQL trace recording and return the resulting report. This only affects sharpit's bounded local "
        "capture and does not execute SQL.",
        _NONE,
        "sql-trace",
        True,
        lambda c, _a: _sql_trace_action(c.ctx, lambda r: r.set_recording(True)),
    ),
    Tool(
        "get_live_activity",
        "Return a bounded, newest-first activity snapshot that merges HTTP requests, SQL statements and exceptions, "
        "correlated by request id. Use first when diagnosing one request.",
        _LIMIT_ONLY,
        "activity",
        False,
        lambda c, a: activity.activity_report(c.ctx, None, None, None, a["limit"], None),
    ),
    Tool(
        "get_alembic_migrations",
        "Return the Alembic migration history read from the revision files, oldest first, with each database's "
        "version as last read by the Alembic panel. Never connects to a database, imports a migration or runs "
        "env.py; `checkedAt` null means the database was not read yet.",
        _NONE,
        "alembic",
        False,
        lambda c, _a: alembic_report(c.ctx),
    ),
    Tool(
        "get_health",
        "Return the cached health tree (database pings and the application's own checks) with each component's "
        "status and masked details. Never runs a check: an UNKNOWN status means the checks have not run yet.",
        _NONE,
        "health",
        False,
        lambda c, _a: health_service(c.ctx).report(for_mcp=True),
    ),
    Tool(
        "get_database_connection_pools",
        "Return each registered SQLAlchemy engine's connection pool: settings and live counters (checked out, idle, "
        "total). Reads counters only; never borrows a connection. A pool class that keeps no statistics is listed as "
        "unavailable.",
        _NONE,
        "database-connection-pools",
        False,
        lambda c, _a: pools_report(c.ctx),
    ),
    Tool(
        "get_threads",
        "Return this process's threads with inferred states (RUNNABLE or WAITING) and stacks, plus the event loop's "
        "asyncio tasks with their await chains and the request each one serves. `limit` caps both lists. Code "
        "names and line numbers only: no local variables or argument values.",
        _QUERY_LIMIT,
        "threads",
        False,
        lambda c, a: threads_report(c.ctx, a["query"], None, None, a["limit"]),
    ),
    Tool(
        "get_vulnerabilities_report",
        "Return the cached vulnerability report, or the local dependency inventory before the first scan, "
        "without contacting OSV.dev or any other network service. Inspect `scan.status`, `scan.message`, "
        "`coverage` and `scan.packagesSkipped` before interpreting absent findings. Partial results "
        "retain available evidence; UNKNOWN severity is not zero risk. Coverage describes the "
        "inventory provider's accounting, not shaded-library discovery or exploitability.",
        _NONE,
        "vulnerabilities",
        False,
        lambda c, _a: vulnerability_service(c.ctx).report(),
    ),
    Tool(
        "vulnerabilities_scan",
        "Actively query OSV.dev for known vulnerabilities in this application's dependencies and return "
        "severity-ranked findings. This sends package names/versions to OSV and, when enabled, CVE "
        "ids to FIRST for optional EPSS enrichment; run only with approval. Check `scan.status`, "
        "`scan.message`, `coverage` and `scan.packagesSkipped`: partial or unknown evidence is "
        "not a clean result, and inventory coverage does not prove reachability. Fixed versions are "
        "supported affected-interval candidates, not verified installable upgrades. Verify compatibility "
        "before changing a dependency. EPSS is the highest available per-CVE probability, not a combined "
        "probability or severity; optional enrichment failure retains OSV findings.",
        _NONE,
        "vulnerabilities",
        True,
        lambda c, _a: vulnerability_service(c.ctx).scan(),
    ),
    Tool(
        "get_rest_api_report",
        "Return the last completed REST API advisor report without starting a new endpoint scan. Use this cached "
        "evidence before deciding whether an active rest_api_scan is necessary." + _ADVISOR_GUIDANCE,
        _NONE,
        "rest-api",
        False,
        lambda c, _a: rest_api_service(c.ctx).report(),
    ),
    Tool(
        "get_rest_api_rule_violations",
        "Read one page of retained violations for the exact rule id and cached report's violationDetails.scanId. "
        "This never starts a scan. Default offset 0 and limit 100; limit is capped at min(1000, transport "
        "max-results). Advance by page.returned while page.hasMore; page.total and page.matched count retained "
        "entries, not violationCount. If truncated, retention overflow or unavailable upstream details prevent a "
        "complete list. Verify each finding before changing code. Unknown rule returns 404; stale or missing "
        "snapshot returns 409: reread the cached report, not a new scan. On MCP -32003 byte-budget refusal, retry "
        "the same scanId and offset with a smaller limit; a refusal is not an empty or completed page.",
        _RULE_VIOLATIONS,
        "rest-api",
        False,
        _rest_api_violations,
    ),
    Tool(
        "rest_api_scan",
        "Actively inspect this application's routes and API design for correctness and maintainability risks. "
        "Verify recommendations against the public API contract." + _ADVISOR_GUIDANCE,
        _NONE,
        "rest-api",
        True,
        lambda c, _a: rest_api_service(c.ctx).scan(),
    ),
)

_BASE_COMMANDS = {  # CliCommandPaths.BY_TOOL, MVP rows
    "get_overview": "overview",
    "get_config": "config",
    "get_mappings": "mappings",
    "get_loggers": "loggers",
    "get_beans": "beans",
    "get_http_exchanges": "http exchanges",
    "get_log_tail": "logs tail",
    "get_exceptions": "exceptions list",
    "get_exception_detail": "exceptions show",
    "clear_exceptions": "exceptions clear",
    "get_sql_traces": "sql traces",
    "clear_sql_traces": "sql clear",
    "pause_sql_trace_recording": "sql pause",
    "resume_sql_trace_recording": "sql resume",
    "get_live_activity": "activity",
    "get_alembic_migrations": "db alembic",
    "get_health": "health",
    "get_database_connection_pools": "db pools",
    "get_threads": "threads",
    "get_vulnerabilities_report": "vulnerabilities report",
    "vulnerabilities_scan": "vulnerabilities scan",
    "get_rest_api_report": "rest-api report",
    "get_rest_api_rule_violations": "rest-api violations",
    "rest_api_scan": "rest-api scan",
}

from sharpit.engine.panels04 import tool_definitions as _tool_definitions  # noqa: E402, I001

_PANEL_04_TOOLS, _PANEL_04_COMMANDS = _tool_definitions()
TOOLS: tuple[Tool, ...] = (*_BASE_TOOLS, *_PANEL_04_TOOLS)
COMMANDS = {**_BASE_COMMANDS, **_PANEL_04_COMMANDS}

from sharpit.engine.tool_dispatch import (  # noqa: E402, I001 - dispatcher imports the catalog built above
    ToolGate as ToolGate,
    call_tool as call_tool,
    cli_invoke as cli_invoke,
    cli_status as cli_status,
    tool_gate as tool_gate,
    tool_info as tool_info,
)
