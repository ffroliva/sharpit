"""Tool execution, MCP listing and CLI status/dispatch."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, NoReturn, cast

from sharpit import __version__
from sharpit.engine.context import SharpitContext
from sharpit.engine.paging import BadRequest
from sharpit.engine.panels import disabled_reason, read_only_reason
from sharpit.engine.singleflight import ActionBusy
from sharpit.settings import PanelSettings

logger = logging.getLogger("sharpit")


def _contracts() -> Any:
    """Resolve facade names after import so the compatibility module remains monkeypatchable."""
    from sharpit.engine import tools

    return tools


def _raise_tool_error(error: BaseException, contracts: Any) -> NoReturn:
    if isinstance(error, ActionBusy):
        raise contracts.ToolCallError(str(error), 409)
    if isinstance(error, BadRequest):
        raise contracts.ToolCallError(str(error), 400)
    if isinstance(error, contracts.ToolCallError):  # a handler's own in-band refusal (an unknown id)
        raise error
    if not isinstance(error, Exception):
        raise error
    logger.error("sharpit MCP failure while dispatching a request", exc_info=error)
    raise contracts.RpcError(contracts.INTERNAL_ERROR, contracts.INTERNAL_ERROR_MESSAGE)


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
        contracts = _contracts()
        if not self._slots.acquire(blocking=False):
            self.count("capacityRefusals")
            raise contracts.RpcError(contracts.SERVER_AT_CAPACITY, "MCP server is at capacity; try again shortly.")
        started = time.monotonic()
        done = threading.Event()
        outcome: dict[str, Any] = {}

        def worker() -> None:
            try:
                outcome["value"] = fn()
            except BaseException as exc:  # noqa: BLE001 # NOSONAR - worker thread: re-raised or mapped by _raise_tool_error
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
            raise contracts.RpcError(contracts.TOOL_TIMEOUT, "MCP tool execution timed out")
        error = outcome.get("error")
        if error is None:
            return outcome["value"]
        _raise_tool_error(error, contracts)


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
    contracts = _contracts()
    if not isinstance(args, dict):
        raise contracts.RpcError(contracts.INVALID_PARAMS, "Tool arguments must be an object")
    checked = cast("dict[str, Any]", args)
    for key, minimum in (("query", None), ("id", None), ("limit", 1)):  # the only arguments any sharpit tool takes
        if key not in checked:
            continue
        value = checked[key]
        if minimum is None:
            if not isinstance(value, str):
                raise contracts.RpcError(contracts.INVALID_PARAMS, f"Argument '{key}' must be a string")
        elif not _is_int32(value):
            raise contracts.RpcError(contracts.INVALID_PARAMS, f"Argument '{key}' must be an integer")
        elif value < minimum:
            raise contracts.RpcError(contracts.INVALID_PARAMS, f"Argument '{key}' must be at least {minimum}")
    return checked


def _rule_violation_arguments(checked: dict[str, Any], raw_limit: object, max_results: int) -> dict[str, Any]:
    """``scanId``/``offset`` of the RULE_VIOLATIONS schema; the raw limit (None: 100) is capped by the page itself."""
    contracts = _contracts()
    scan_id, offset = checked.get("scanId"), checked.get("offset")
    if scan_id is not None and not isinstance(scan_id, str):
        raise contracts.RpcError(contracts.INVALID_PARAMS, "Argument 'scanId' must be a string")
    if offset is not None and not _is_int32(offset):
        raise contracts.RpcError(contracts.INVALID_PARAMS, "Argument 'offset' must be an integer")
    if isinstance(offset, int) and offset < 0:
        raise contracts.RpcError(contracts.INVALID_PARAMS, "Argument 'offset' must be at least 0")
    if not (scan_id or "").strip():
        raise contracts.RpcError(contracts.INVALID_PARAMS, "Missing required argument: scanId")
    return {"scanId": (scan_id or "").strip(), "offset": offset, "pageLimit": raw_limit, "maxResults": max_results}


def _find_tool(catalogue: Sequence[Tool], name: object, via: Via, contracts: Any) -> Tool:
    if not isinstance(name, str) or not name:
        raise contracts.RpcError(contracts.INVALID_PARAMS, "Missing tool name")
    tool = next((t for t in catalogue if t.name == name and (via == "cli" or not t.action)), None)
    if tool is None:
        raise contracts.RpcError(contracts.INVALID_PARAMS, contracts.UNKNOWN_TOOL_PREFIX + name)
    return tool


def _checked_tool_arguments(tool: Tool, args: object, contracts: Any) -> dict[str, Any]:
    checked = _check_arguments(args)
    unexpected = sorted(set(checked) - set(tool.input_schema["properties"]))
    if unexpected:
        plural = "" if len(unexpected) == 1 else "s"
        raise contracts.RpcError(contracts.INVALID_PARAMS, f"Unexpected tool argument{plural}: {', '.join(unexpected)}")
    return checked


def _normalized_arguments(tool: Tool, checked: dict[str, Any], max_results: int, contracts: Any) -> dict[str, Any]:
    query = checked.get("query")
    query = query.strip() or None if isinstance(query, str) else None
    raw_limit = checked.get("limit")
    limit = min(raw_limit, max_results) if isinstance(raw_limit, int) else max_results
    raw_id = checked.get("id")
    gid = raw_id.strip() if isinstance(raw_id, str) else ""
    if "id" in tool.input_schema["properties"] and not gid:  # BootUI: after the panel gates
        raise contracts.RpcError(contracts.INVALID_PARAMS, "Missing required argument: id")
    normalized = {"query": query, "limit": limit, **({"id": gid} if "id" in tool.input_schema["properties"] else {})}
    if "scanId" in tool.input_schema["properties"]:  # RULE_VIOLATIONS: checked only on the tool that declares them
        normalized.update(_rule_violation_arguments(checked, raw_limit, max_results))
    return normalized


def call_tool(
    call: CallContext, name: object, args: object, *, via: Via, tools: Sequence[Tool] | None = None
) -> dict[str, Any]:
    """The tool's payload, or ``RpcError`` (protocol error) / ``ToolCallError`` (in-band refusal)."""
    contracts = _contracts()
    catalogue = contracts.TOOLS if tools is None else tools
    tool = _find_tool(catalogue, name, via, contracts)
    checked = _checked_tool_arguments(tool, args, contracts)
    settings = call.ctx.settings
    flags = settings.panels.get(tool.panel, PanelSettings())
    if not flags.enabled:
        raise contracts.ToolCallError(disabled_reason(tool.panel), 403)
    if tool.action and (settings.read_only or flags.read_only):
        raise contracts.ToolCallError(read_only_reason(tool.panel, settings.read_only), 403)
    gate = contracts.tool_gate(call.ctx, via)
    normalized = _normalized_arguments(tool, checked, gate.max_results, contracts)
    return gate.run(tool.name, lambda: tool.handler(call, normalized))


# --- CLI (CliService, CliOutcomes) ----------------------------------------------------------------------------------


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
    contracts = _contracts()
    settings = ctx.settings
    infos: list[dict[str, Any]] = []
    for tool in contracts.TOOLS if settings.cli_enabled else ():
        arguments = list(tool.input_schema["properties"])
        info = tool_info(ctx, tool)
        infos.append(  # field by field: BootUI's CliToolInfo key order, which test_cli_status_shape pins
            {
                "name": tool.name,
                "command": contracts.COMMANDS[tool.name],
                "description": tool.description,
                "panel": tool.panel,
                "action": tool.action,
                "schema": contracts._SCHEMA_NAMES[tuple(arguments)],
                "arguments": arguments,
                "panelEnabled": info["panelEnabled"],
                "panelReadOnly": info["panelReadOnly"],
            }
        )
    stats = contracts.tool_gate(ctx, "cli").snapshot()
    del stats["responseLimitRefusals"]  # not part of CliServerStatus
    return {
        "enabled": settings.cli_enabled,
        "serverName": contracts.SERVER_NAME,
        "serverVersion": __version__,
        "endpoint": (api_path or settings.api_path) + "/cli",
        "maxResults": settings.cli_max_results,
        **stats,
        "toolCount": len(infos),
        "tools": infos,
    }


def cli_invoke(call: CallContext, name: str, args: object) -> tuple[int, dict[str, Any]]:
    """``(status, body)``: the bare payload on 200, else ``{"error": message}`` with the ``CliOutcomes`` status."""
    contracts = _contracts()
    if not call.ctx.settings.cli_enabled:
        return 503, {"error": contracts.CLI_DISABLED_MESSAGE}
    try:
        return 200, call_tool(call, name, args, via="cli")
    except contracts.ToolCallError as exc:
        return exc.status, {"error": exc.message}
    except contracts.RpcError as exc:
        if exc.code == contracts.INVALID_PARAMS:
            status = 404 if exc.message.startswith(contracts.UNKNOWN_TOOL_PREFIX) else 400
        else:
            status = {contracts.SERVER_AT_CAPACITY: 429, contracts.TOOL_TIMEOUT: 504}.get(exc.code, 500)
        return status, {"error": exc.message}


from sharpit.engine.tools import (  # noqa: E402, I001 - resolve facade types after definitions
    CallContext as CallContext,
    Tool as Tool,
    Via as Via,
)
