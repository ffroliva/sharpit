"""Tool catalogue and dispatcher shared by the MCP server and the CLI endpoints.

Port of BootUI ``McpToolCatalog`` (the seven MVP rows), ``McpToolSchema`` rendered as in ``BootUiMcpService.schema``,
``McpToolDescriptions``, ``McpArguments.normalize``, ``McpDispatcher.callTool``, ``CliService`` and ``CliOutcomes``.
MCP never sees an action tool (``vulnerabilities_scan`` is CLI-only, spec §9). Each ``via`` has its own caps, slots
and counters, as BootUI's MCP and CLI each own a dispatcher.

Timeout: Python threads cannot be interrupted (BootUI cancels the future), so the call's slot is released exactly
once, by whichever comes first of the worker finishing or the caller giving up; an abandoned worker runs on.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from sharpit.engine.collectors.beans import beans_report
from sharpit.engine.collectors.config import config_report
from sharpit.engine.collectors.loggers import loggers_report
from sharpit.engine.collectors.mappings import mappings_flat
from sharpit.engine.collectors.overview import overview_dto
from sharpit.engine.collectors.vulns.dismissals import DismissalStore
from sharpit.engine.collectors.vulns.epss import EpssClient
from sharpit.engine.collectors.vulns.inventory import inventory
from sharpit.engine.collectors.vulns.osv import OsvClient
from sharpit.engine.collectors.vulns.service import VulnerabilityService
from sharpit.engine.context import SharpitContext
from sharpit.engine.paging import BadRequest
from sharpit.engine.panels import disabled_reason, read_only_reason
from sharpit.engine.singleflight import ActionBusy
from sharpit.settings import PanelSettings

logger = logging.getLogger("sharpit")

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

_LIMIT = {
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
_SCHEMA_NAMES = {(): "NONE", ("limit",): "LIMIT", ("query", "limit"): "QUERY_LIMIT"}


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
            DismissalStore(Path(settings.state_dir)),
            ctx.single_flight,
        ),
    )


TOOLS: tuple[Tool, ...] = (
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
)

COMMANDS = {  # CliCommandPaths.BY_TOOL, MVP rows
    "get_overview": "overview",
    "get_config": "config",
    "get_mappings": "mappings",
    "get_loggers": "loggers",
    "get_beans": "beans",
    "get_vulnerabilities_report": "vulnerabilities report",
    "vulnerabilities_scan": "vulnerabilities scan",
}


# --- Dispatcher (McpDispatcher.callTool) ----------------------------------------------------------------------------


class ToolGate:
    """Caps, concurrency slots and counters (``McpRuntimeStats``) of one ``via``."""

    def __init__(self, max_results: int, max_concurrent: int, timeout: float) -> None:
        self.max_results = max_results
        self.timeout = timeout
        # one slot per worker thread, released only when it finishes: timed-out workers still running count too
        self._slots = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()
        self.stats = {
            "callCount": 0,
            "totalLatencyMillis": 0,
            "capacityRefusals": 0,
            "timeouts": 0,
            "responseLimitRefusals": 0,
        }

    def count(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self.stats[key] += amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self.stats)

    def run(self, name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        if not self._slots.acquire(blocking=False):
            self.count("capacityRefusals")
            raise RpcError(SERVER_AT_CAPACITY, "MCP server is at capacity; try again shortly.")
        started = time.monotonic()
        done = threading.Event()
        outcome: dict[str, Any] = {}

        def worker() -> None:
            try:
                outcome["value"] = fn()
            except BaseException as exc:  # noqa: BLE001 - re-raised or mapped in the caller
                outcome["error"] = exc
            finally:
                with self._lock:
                    self.stats["callCount"] += 1
                    self.stats["totalLatencyMillis"] += round((time.monotonic() - started) * 1000)
                self._slots.release()
                done.set()

        try:
            threading.Thread(target=worker, name=f"sharpit-tool-{name}", daemon=True).start()
        except BaseException:
            self._slots.release()
            raise
        if not done.wait(self.timeout):
            self.count("timeouts")
            raise RpcError(TOOL_TIMEOUT, "MCP tool execution timed out")
        error = outcome.get("error")
        if error is None:
            return outcome["value"]
        if isinstance(error, ActionBusy):
            raise ToolCallError(str(error), 409)
        if isinstance(error, BadRequest):
            raise ToolCallError(str(error), 400)
        if not isinstance(error, Exception):
            raise error
        logger.error("sharpit MCP failure while dispatching a request", exc_info=error)
        raise RpcError(INTERNAL_ERROR, INTERNAL_ERROR_MESSAGE)


def tool_gate(ctx: SharpitContext, via: Via) -> ToolGate:
    s = ctx.settings
    if via == "mcp":
        return ctx.lazy(
            "tools.mcp", lambda: ToolGate(s.mcp_max_results, s.mcp_max_concurrent_calls, s.mcp_execution_timeout)
        )
    return ctx.lazy(
        "tools.cli", lambda: ToolGate(s.cli_max_results, s.cli_max_concurrent_calls, s.cli_execution_timeout)
    )


def _is_int32(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and -(2**31) <= value < 2**31


def _check_arguments(args: object) -> dict[str, Any]:
    """Type checks of ``BootUiMcpService.parseArguments`` / ``CliService.parseArguments``; null is a type error."""
    if not isinstance(args, dict):
        raise RpcError(INVALID_PARAMS, "Tool arguments must be an object")
    checked = cast("dict[str, Any]", args)
    for key, minimum in (("query", None), ("id", None), ("limit", 1), ("scanId", None), ("offset", 0)):
        if key not in checked:
            continue
        value = checked[key]
        if minimum is None:
            if not isinstance(value, str):
                raise RpcError(INVALID_PARAMS, f"Argument '{key}' must be a string")
        elif not _is_int32(value):
            raise RpcError(INVALID_PARAMS, f"Argument '{key}' must be an integer")
        elif value < minimum:
            raise RpcError(INVALID_PARAMS, f"Argument '{key}' must be at least {minimum}")
    return checked


def call_tool(
    call: CallContext, name: object, args: object, *, via: Via, tools: Sequence[Tool] | None = None
) -> dict[str, Any]:
    """The tool's payload, or ``RpcError`` (protocol error) / ``ToolCallError`` (in-band refusal)."""
    catalogue = TOOLS if tools is None else tools
    if not isinstance(name, str) or not name:
        raise RpcError(INVALID_PARAMS, "Missing tool name")
    tool = next((t for t in catalogue if t.name == name and (via == "cli" or not t.action)), None)
    if tool is None:
        raise RpcError(INVALID_PARAMS, UNKNOWN_TOOL_PREFIX + name)
    checked = _check_arguments(args)
    unexpected = sorted(set(checked) - set(tool.input_schema["properties"]))
    if unexpected:
        plural = "" if len(unexpected) == 1 else "s"
        raise RpcError(INVALID_PARAMS, f"Unexpected tool argument{plural}: {', '.join(unexpected)}")
    settings = call.ctx.settings
    flags = settings.panels.get(tool.panel, PanelSettings())
    if not flags.enabled:
        raise ToolCallError(disabled_reason(tool.panel), 403)
    if tool.action and (settings.read_only or flags.read_only):
        raise ToolCallError(read_only_reason(tool.panel, settings.read_only), 403)
    gate = tool_gate(call.ctx, via)
    query = checked.get("query")
    query = query.strip() or None if isinstance(query, str) else None
    raw_limit = checked.get("limit")
    limit = min(raw_limit, gate.max_results) if isinstance(raw_limit, int) else gate.max_results
    normalized = {"query": query, "limit": limit}
    return gate.run(tool.name, lambda: tool.handler(call, normalized))


# --- CLI (CliService, CliOutcomes) ----------------------------------------------------------------------------------

_CLI_STATUS = {SERVER_AT_CAPACITY: 429, TOOL_TIMEOUT: 504, SERVER_DISABLED: 503}


def _panel_read_only(ctx: SharpitContext, panel: str) -> bool:
    return ctx.settings.read_only or ctx.settings.panels.get(panel, PanelSettings()).read_only


def tool_info(ctx: SharpitContext, tool: Tool) -> dict[str, Any]:
    """``McpToolInfo``: one tool as the MCP Server panel lists it."""
    return {
        "name": tool.name,
        "description": tool.description,
        "panel": tool.panel,
        "action": tool.action,
        "panelEnabled": ctx.settings.panels.get(tool.panel, PanelSettings()).enabled,
        "panelReadOnly": _panel_read_only(ctx, tool.panel),
    }


def cli_status(ctx: SharpitContext, api_path: str | None = None) -> dict[str, Any]:
    """``CliServerStatus``; answered while disabled too, with no tools (nothing is invocable)."""
    from sharpit import __version__  # deferred: sharpit/__init__ imports the adapter, which imports this module

    settings = ctx.settings
    infos: list[dict[str, Any]] = []
    for tool in TOOLS if settings.cli_enabled else ():
        arguments = list(tool.input_schema["properties"])
        info = tool_info(ctx, tool)
        infos.append(
            {
                "name": tool.name,
                "command": COMMANDS[tool.name],
                "description": tool.description,
                "panel": tool.panel,
                "action": tool.action,
                "schema": _SCHEMA_NAMES[tuple(arguments)],
                "arguments": arguments,
                "panelEnabled": info["panelEnabled"],
                "panelReadOnly": info["panelReadOnly"],
            }
        )
    stats = tool_gate(ctx, "cli").snapshot()
    del stats["responseLimitRefusals"]  # not part of CliServerStatus
    return {
        "enabled": settings.cli_enabled,
        "serverName": SERVER_NAME,
        "serverVersion": __version__,
        "endpoint": (api_path or settings.api_path) + "/cli",
        "maxResults": settings.cli_max_results,
        **stats,
        "toolCount": len(infos),
        "tools": infos,
    }


def cli_invoke(call: CallContext, name: str, args: object) -> tuple[int, dict[str, Any]]:
    """``(status, body)``: the bare payload on 200, else ``{"error": message}`` with the ``CliOutcomes`` status."""
    if not call.ctx.settings.cli_enabled:
        return 503, {"error": CLI_DISABLED_MESSAGE}
    try:
        return 200, call_tool(call, name, args, via="cli")
    except ToolCallError as exc:
        return exc.status, {"error": exc.message}
    except RpcError as exc:
        if exc.code == INVALID_PARAMS:
            status = 404 if exc.message.startswith(UNKNOWN_TOOL_PREFIX) else 400
        else:
            status = _CLI_STATUS.get(exc.code, 500)
        return status, {"error": exc.message}
