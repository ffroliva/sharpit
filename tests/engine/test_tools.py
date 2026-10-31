"""Tool catalogue and ``call_tool`` (port of BootUI ``McpToolCatalog``, ``McpToolSchema``/``BootUiMcpService.schema``,
``McpArguments`` and ``McpDispatcher.callTool``).

Ported: the ``McpDispatcher.callTool`` gates that ``BootUiMcpServiceTests`` exercises through the codec (they are cited
here where the engine owns the behaviour, and again in ``test_mcp.py`` where the codec renders it).
Dropped, with reason:
- ``advisor*`` cases (``RULE_VIOLATIONS`` schema, ``scanId``/``offset`` paging, stale snapshots): no advisor tools in
  the MVP catalogue.
- ``McpDispatcher`` interrupt bookkeeping (``invocationState``): Python threads cannot be interrupted; the slot is
  released only when the worker finishes, so abandoned workers count against the cap
  (``test_timeout_releases_semaphore``).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from conftest import SideEffectGuard
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.engine.collectors.restapi.service import RestApiService
from sharpit.engine.context import SharpitContext
from sharpit.engine.paging import BadRequest
from sharpit.engine.singleflight import ActionBusy, SingleFlight
from sharpit.engine.spi import ApiModel, ApiRouteInfo, AppInfo, ProviderInfo, RouteInfo
from sharpit.engine.tools import (
    COMMANDS,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    SERVER_AT_CAPACITY,
    TOOL_TIMEOUT,
    TOOLS,
    CallContext,
    RpcError,
    Tool,
    ToolCallError,
    call_tool,
    tool_gate,
)
from sharpit.settings import PanelSettings, SharpitSettings, load_settings

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
NONE_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}
LIMIT_DESCRIPTION = "Optional maximum number of items to return. Capped by the SHARPIT_MCP_MAX_RESULTS server limit."
QUERY_LIMIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Optional case-insensitive filter applied to the results."},
        "limit": {"type": "integer", "minimum": 1, "description": LIMIT_DESCRIPTION},
    },
    "additionalProperties": False,
}

LIMIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"limit": QUERY_LIMIT_SCHEMA["properties"]["limit"]},
    "additionalProperties": False,
}
ID_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"id": {"type": "string", "description": "Exact identifier of the resource to fetch."}},
    "required": ["id"],
    "additionalProperties": False,
}
RULE_VIOLATIONS_SCHEMA: dict[str, Any] = {
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
BOOTUI_TOOLS = json.loads((Path(__file__).parents[1] / "fixtures" / "bootui_tools_0_2_0.json").read_text("utf-8"))
RELEASE_TOOLS = (
    "get_http_exchanges",
    "get_log_tail",
    "get_exceptions",
    "get_exception_detail",
    "get_sql_traces",
    "get_live_activity",
    "get_alembic_migrations",
    "get_health",
    "get_database_connection_pools",
    "get_threads",
    "get_rest_api_report",
    "get_rest_api_rule_violations",
)  # each 0.2.0 task adds the tools it builds


class FakeIntrospector:
    def app_info(self) -> AppInfo:
        return AppInfo("demo", "FastAPI", "0.115.0", None)

    def routes(self) -> list[RouteInfo]:
        return [RouteInfo(("GET",), "/pets", "app:pets", None, "application/json", None, "pets")]

    def providers(self) -> list[ProviderInfo]:
        return []


def _ctx(**options: Any) -> SharpitContext:
    settings = load_settings({"config_scan": False, **options}, {})
    return SharpitContext(settings, ACTIVATION, FakeIntrospector())


def _call(ctx: SharpitContext, scope: dict[str, Any] | None = None) -> CallContext:
    return CallContext(ctx, scope or {})


def _tool(name: str, handler: Callable[[CallContext, dict[str, Any]], dict[str, Any]], **kw: Any) -> Tool:
    fields: dict[str, Any] = {"input_schema": NONE_SCHEMA, "panel": "overview", "action": False, **kw}
    return Tool(name, f"{name} description", fields["input_schema"], fields["panel"], fields["action"], handler)


def test_catalogue_names_panels_actions_and_schemas():
    # ported: McpToolCatalog ENTRIES (the 24 0.2.0 rows, panel and action names)
    rows = [(t.name, t.panel, t.action, t.input_schema) for t in TOOLS]
    assert rows == [
        ("get_overview", "overview", False, NONE_SCHEMA),
        ("get_config", "config", False, QUERY_LIMIT_SCHEMA),
        ("get_mappings", "mappings", False, QUERY_LIMIT_SCHEMA),
        ("get_loggers", "loggers", False, QUERY_LIMIT_SCHEMA),
        ("get_beans", "beans", False, QUERY_LIMIT_SCHEMA),
        ("get_http_exchanges", "http-exchanges", False, LIMIT_SCHEMA),
        ("get_log_tail", "log-tail", False, NONE_SCHEMA),
        ("get_exceptions", "exceptions", False, NONE_SCHEMA),
        ("get_exception_detail", "exceptions", False, ID_SCHEMA),
        ("clear_exceptions", "exceptions", True, NONE_SCHEMA),
        ("get_sql_traces", "sql-trace", False, NONE_SCHEMA),
        ("clear_sql_traces", "sql-trace", True, NONE_SCHEMA),
        ("pause_sql_trace_recording", "sql-trace", True, NONE_SCHEMA),
        ("resume_sql_trace_recording", "sql-trace", True, NONE_SCHEMA),
        ("get_live_activity", "activity", False, LIMIT_SCHEMA),
        ("get_alembic_migrations", "alembic", False, NONE_SCHEMA),
        ("get_health", "health", False, NONE_SCHEMA),
        ("get_database_connection_pools", "database-connection-pools", False, NONE_SCHEMA),
        ("get_threads", "threads", False, QUERY_LIMIT_SCHEMA),
        ("get_vulnerabilities_report", "vulnerabilities", False, NONE_SCHEMA),
        ("vulnerabilities_scan", "vulnerabilities", True, NONE_SCHEMA),
        ("get_rest_api_report", "rest-api", False, NONE_SCHEMA),
        ("get_rest_api_rule_violations", "rest-api", False, RULE_VIOLATIONS_SCHEMA),
        ("rest_api_scan", "rest-api", True, NONE_SCHEMA),
    ]


def test_descriptions_ported_with_names_substituted():
    # ported: McpToolDescriptions.COMMON / springDescription (BootUI -> sharpit; get_beans, get_config adapted)
    by_name = {t.name: t.description for t in TOOLS}
    assert by_name["get_overview"] == (
        "Return stable application identity and runtime context, including versions, active profiles, and "
        "sharpit status. Use this before interpreting other results."
    )
    assert by_name["get_loggers"].startswith("Search configured loggers by case-insensitive name")
    assert by_name["get_vulnerabilities_report"].startswith("Return the cached vulnerability report")
    assert by_name["vulnerabilities_scan"].startswith("Actively query OSV.dev for known vulnerabilities")
    assert by_name["get_rest_api_report"].startswith("Return the last completed REST API advisor report")
    assert by_name["get_rest_api_rule_violations"].startswith("Read one page of retained violations")
    assert by_name["rest_api_scan"].startswith("Actively inspect this application's routes")
    assert "SHARPIT_MCP_ENABLED" in by_name["get_config"]
    assert all("BootUI" not in d and "bootui" not in d and "Spring" not in d for d in by_name.values())


@pytest.mark.parametrize("name", RELEASE_TOOLS)
def test_mcp_schema_matches_bootui(name: str):
    # BootUI bootui-tools.json names, commands, panels and schema kinds; BootUiMcpService.schema renders inputSchema
    entry = next(t for t in BOOTUI_TOOLS["tools"] if t.get("sharpitName", t["name"]) == name)
    tool = next(t for t in TOOLS if t.name == name)
    expected = json.loads(json.dumps(entry["inputSchema"]).replace("bootui.mcp.max-results", "SHARPIT_MCP_MAX_RESULTS"))
    assert tool.input_schema == expected
    assert (tool.panel, tool.action) == (entry.get("sharpitPanel", entry["panel"]), entry["action"])
    assert COMMANDS[name] == entry.get("sharpitCommand", entry["command"])
    assert "Spring" not in tool.description and "JVM" not in tool.description


def test_bootui_tools_fixture_holds_the_release():
    assert len(BOOTUI_TOOLS["tools"]) == 12 and len(BOOTUI_TOOLS["bootuiToolsCommit"]) == 40


def test_every_action_tool_references_an_action_capable_panel():
    # ported: McpToolCatalog.Entry constructor ("MCP action tool ... must reference an action-capable panel")
    from sharpit.engine.panels import PANELS

    capable = {p.id for p in PANELS if p.action_capable}
    assert all(t.panel in capable for t in TOOLS if t.action)


def test_mcp_call_action_tool_unknown_32602():
    # new: brief ruling (MCP never sees an action tool, spec §9)
    with pytest.raises(RpcError) as exc:
        call_tool(_call(_ctx()), "vulnerabilities_scan", {}, via="mcp")
    assert (exc.value.code, exc.value.message) == (INVALID_PARAMS, "Unknown tool: vulnerabilities_scan")


@pytest.mark.parametrize(
    ("name", "args", "message"),
    [
        (None, {}, "Missing tool name"),  # ported: McpDispatcher.callTool missing name
        ("", {}, "Missing tool name"),
        ("does_not_exist", {}, "Unknown tool: does_not_exist"),  # ported: BootUiMcpServiceTests.unknownTool...
        ("get_overview", "invalid", "Tool arguments must be an object"),  # ported: toolCallRejectsNonObject...
        ("get_overview", None, "Tool arguments must be an object"),
        ("get_overview", {"extra": True}, "Unexpected tool argument: extra"),  # ported: ...UnexpectedArguments
        ("get_overview", {"b": 1, "a": 2}, "Unexpected tool arguments: a, b"),
        ("get_config", {"query": 1}, "Argument 'query' must be a string"),
        ("get_config", {"query": None}, "Argument 'query' must be a string"),
        ("get_config", {"id": "x"}, "Unexpected tool argument: id"),  # get_config takes no id (Task 4 ruling)
        ("get_exception_detail", {"id": 1}, "Argument 'id' must be a string"),  # id is type-checked first
        ("get_config", {"scanId": "x"}, "Unexpected tool argument: scanId"),  # only the violations tool takes scanId
        ("get_config", {"limit": "5"}, "Argument 'limit' must be an integer"),
        ("get_config", {"limit": True}, "Argument 'limit' must be an integer"),
        ("get_config", {"limit": 1.5}, "Argument 'limit' must be an integer"),
        ("get_config", {"limit": 2**31}, "Argument 'limit' must be an integer"),
        ("get_config", {"limit": 0}, "Argument 'limit' must be at least 1"),  # ported: rejectsNonPositiveLimit
        ("get_config", {"scanId": 1}, "Unexpected tool argument: scanId"),
        ("get_config", {"offset": -1}, "Unexpected tool argument: offset"),
        ("get_rest_api_rule_violations", {"scanId": "x"}, "Missing required argument: id"),
        ("get_rest_api_rule_violations", {"id": "RAPI-MAP-001"}, "Missing required argument: scanId"),
        ("get_rest_api_rule_violations", {"id": "RAPI-MAP-001", "scanId": " "}, "Missing required argument: scanId"),
        ("get_rest_api_rule_violations", {"id": "RAPI-MAP-001", "scanId": 1}, "Argument 'scanId' must be a string"),
        (
            "get_rest_api_rule_violations",
            {"id": "R", "scanId": "x", "offset": -1},
            "Argument 'offset' must be at least 0",
        ),
        (
            "get_rest_api_rule_violations",
            {"id": "R", "scanId": "x", "offset": "1"},
            "Argument 'offset' must be an integer",
        ),
        ("get_rest_api_rule_violations", {"id": "R", "scanId": "x", "limit": 0}, "Argument 'limit' must be at least 1"),
    ],
)
def test_invalid_params(name: Any, args: Any, message: str):
    with pytest.raises(RpcError) as exc:
        call_tool(_call(_ctx()), name, args, via="mcp")
    assert (exc.value.code, exc.value.message) == (INVALID_PARAMS, message)


def test_disabled_panel_is_an_in_band_refusal():
    # ported: BootUiMcpServiceTests.toolsCallOnDisabledPanelReturnsInBandError
    ctx = _ctx(panels={"overview": PanelSettings(enabled=False)})
    with pytest.raises(ToolCallError) as exc:
        call_tool(_call(ctx), "get_overview", {}, via="mcp")
    assert (exc.value.message, exc.value.status) == ("Panel is disabled via SHARPIT_PANELS_OVERVIEW_ENABLED=false", 403)


def test_action_tool_on_read_only_panel_is_refused():
    # ported: BootUiMcpServiceTests.actionToolOnReadOnlyPanelIsRefused
    ctx = _ctx(panels={"vulnerabilities": PanelSettings(read_only=True)})
    with pytest.raises(ToolCallError) as exc:
        call_tool(_call(ctx), "vulnerabilities_scan", {}, via="cli")
    assert exc.value.message == "Panel is read-only via SHARPIT_PANELS_VULNERABILITIES_READ_ONLY=true"
    assert exc.value.status == 403


def test_action_tool_refused_under_global_read_only():
    # adapted: BootUiMcpServiceTests.actionToolOnReadOnlyPanelIsRefused (global SHARPIT_READ_ONLY)
    with pytest.raises(ToolCallError) as exc:
        call_tool(_call(_ctx(read_only=True)), "vulnerabilities_scan", {}, via="cli")
    assert exc.value.message == "sharpit is read-only via SHARPIT_READ_ONLY=true"


def test_read_tool_on_read_only_panel_still_succeeds():
    # ported: BootUiMcpServiceTests.readToolOnReadOnlyPanelStillSucceeds
    ctx = _ctx(read_only=True, panels={"overview": PanelSettings(read_only=True)})
    assert call_tool(_call(ctx), "get_overview", {}, via="mcp")["applicationName"] == "demo"


def test_limit_defaults_to_and_is_capped_by_max_results_per_via():
    # ported: McpArguments.normalize (limit default and cap; query trimmed, blank -> null)
    seen: list[dict[str, Any]] = []
    tool = _tool("get_x", lambda _c, a: seen.append(a) or {}, input_schema=QUERY_LIMIT_SCHEMA)
    ctx = _ctx(mcp_max_results=5, cli_max_results=7)
    call_tool(_call(ctx), "get_x", {}, via="mcp", tools=(tool,))
    call_tool(_call(ctx), "get_x", {"limit": 50, "query": "  "}, via="mcp", tools=(tool,))
    call_tool(_call(ctx), "get_x", {"limit": 3, "query": " pets "}, via="cli", tools=(tool,))
    call_tool(_call(ctx), "get_x", {"limit": 50}, via="cli", tools=(tool,))
    assert seen == [
        {"query": None, "limit": 5},
        {"query": None, "limit": 5},
        {"query": "pets", "limit": 3},
        {"query": None, "limit": 7},
    ]


def test_handlers_return_the_rest_dtos():
    # adapted: BootUiMcpTools (each tool returns the panel's REST DTO)
    ctx = _ctx()
    mappings = call_tool(_call(ctx), "get_mappings", {"query": "pets"}, via="mcp")
    assert [m["pattern"] for m in mappings["mappings"]] == ["/pets"]
    assert mappings["page"]["limit"] == 200
    assert "loggers" in call_tool(_call(ctx), "get_loggers", {"limit": 1}, via="mcp")
    assert "beans" in call_tool(_call(ctx), "get_beans", {}, via="mcp")


def test_overview_tool_uses_request_scope():
    # adapted: BootUiMcpTools.overview (request port and context path, from the ASGI scope)
    scope = {"server": ("127.0.0.1", 8123), "app_root_path": "/host", "root_path": "/host/sharpit"}
    dto = call_tool(_call(_ctx(), scope), "get_overview", {}, via="mcp")
    assert (dto["serverPort"], dto["contextPath"]) == (8123, "/host")


def test_action_busy_is_an_in_band_conflict():
    # ported: McpDispatcher.callTool ActionBusyException -> ToolCallError(ACTION_BUSY)
    def busy(_c: CallContext, _a: dict[str, Any]) -> dict[str, Any]:
        raise ActionBusy("vulnerabilities-scan", "vulnerabilities-scan")

    tool = _tool("scan_x", busy, panel="vulnerabilities", action=True)
    with pytest.raises(ToolCallError) as exc:
        call_tool(_call(_ctx()), "scan_x", {}, via="cli", tools=(tool,))
    assert exc.value.status == 409
    assert exc.value.message == str(ActionBusy("vulnerabilities-scan", "vulnerabilities-scan"))


def test_tool_client_error_is_in_band():
    # ported: BootUiMcpServiceTests.toolClientErrorIsRenderedInBandInsteadOfAnInternalError (BadRequest is the
    # sharpit client error, as McpToolClientException is BootUI's)
    def bad(_c: CallContext, _a: dict[str, Any]) -> dict[str, Any]:
        raise BadRequest("exception does-not-exist not found")

    with pytest.raises(ToolCallError) as exc:
        call_tool(_call(_ctx()), "get_x", {}, via="mcp", tools=(_tool("get_x", bad),))
    assert (exc.value.message, exc.value.status) == ("exception does-not-exist not found", 400)


def test_unexpected_failure_is_internal_error_without_details(caplog: pytest.LogCaptureFixture):
    # ported: BootUiMcpServiceTests.toolHandlerExceptionReturnsCanonicalInternalErrorWithoutSensitiveDetails
    failure = RuntimeError("token=ghp_secret jdbc:mysql://localhost/private")

    def boom(_c: CallContext, _a: dict[str, Any]) -> dict[str, Any]:
        raise failure

    with pytest.raises(RpcError) as exc:
        call_tool(_call(_ctx()), "get_x", {}, via="mcp", tools=(_tool("get_x", boom),))
    assert (exc.value.code, exc.value.message) == (INTERNAL_ERROR, "Internal error")
    reported = [r for r in caplog.records if r.exc_info and r.exc_info[1] is failure]
    assert len(reported) == 1


def _blocking_tool(release: threading.Event, workers: list[threading.Thread]) -> Tool:
    def block(_c: CallContext, _a: dict[str, Any]) -> dict[str, Any]:
        workers.append(threading.current_thread())
        release.wait(5)
        return {"slow": True}

    return _tool("get_slow", block)


def test_capacity_refusal_32001():
    # ported: McpDispatcher.callTool semaphore tryAcquire -> SERVER_AT_CAPACITY
    release, workers = threading.Event(), list[threading.Thread]()
    tools = (_blocking_tool(release, workers), _tool("get_fast", lambda _c, _a: {"fast": True}))
    ctx = _ctx(mcp_max_concurrent_calls=1)
    first = threading.Thread(target=lambda: call_tool(_call(ctx), "get_slow", {}, via="mcp", tools=tools))
    first.start()
    try:
        while not workers:
            threading.Event().wait(0.01)
        with pytest.raises(RpcError) as exc:
            call_tool(_call(ctx), "get_fast", {}, via="mcp", tools=tools)
        assert (exc.value.code, exc.value.message) == (
            SERVER_AT_CAPACITY,
            "MCP server is at capacity; try again shortly.",
        )
        assert tool_gate(ctx, "mcp").snapshot()["capacityRefusals"] == 1
        assert tool_gate(ctx, "cli").snapshot()["capacityRefusals"] == 0  # CLI has its own slots and counters
    finally:
        release.set()
        first.join(5)
        for worker in workers:
            worker.join(5)
    assert not first.is_alive() and not any(w.is_alive() for w in workers)


def test_timeout_releases_semaphore():
    # new: brief ruling (Python cannot cancel the worker); the abandoned worker keeps its slot until it finishes
    release, workers = threading.Event(), list[threading.Thread]()
    tools = (_blocking_tool(release, workers), _tool("get_fast", lambda _c, _a: {"fast": True}))
    ctx = _ctx(mcp_max_concurrent_calls=2, mcp_execution_timeout="50ms")
    try:
        with pytest.raises(RpcError) as exc:
            call_tool(_call(ctx), "get_slow", {}, via="mcp", tools=tools)
        assert (exc.value.code, exc.value.message) == (TOOL_TIMEOUT, "MCP tool execution timed out")
        assert workers[0].is_alive()  # the abandoned worker still runs and holds one of the two slots
        assert call_tool(_call(ctx), "get_fast", {}, via="mcp", tools=tools) == {"fast": True}
        assert tool_gate(ctx, "mcp").snapshot()["timeouts"] == 1
    finally:
        release.set()
        for worker in workers:
            worker.join(5)
    assert not any(w.is_alive() for w in workers)
    assert tool_gate(ctx, "mcp")._slots._value == 2  # pyright: ignore[reportPrivateUsage]  # late finish: no 2nd release


def test_abandoned_workers_bound_capacity():
    # new: review ruling (timed-out workers still count against max_concurrent until they finish)
    release, workers = threading.Event(), list[threading.Thread]()
    tools = (_blocking_tool(release, workers), _tool("get_fast", lambda _c, _a: {"fast": True}))
    ctx = _ctx(mcp_max_concurrent_calls=2, mcp_execution_timeout="50ms")
    try:
        for _ in range(2):
            with pytest.raises(RpcError) as timed_out:
                call_tool(_call(ctx), "get_slow", {}, via="mcp", tools=tools)
            assert timed_out.value.code == TOOL_TIMEOUT
        with pytest.raises(RpcError) as refused:
            call_tool(_call(ctx), "get_fast", {}, via="mcp", tools=tools)
        assert (refused.value.code, refused.value.message) == (
            SERVER_AT_CAPACITY,
            "MCP server is at capacity; try again shortly.",
        )
        assert tool_gate(ctx, "mcp").snapshot()["capacityRefusals"] == 1
    finally:
        release.set()
        for worker in workers:
            worker.join(5)
    assert not any(w.is_alive() for w in workers)
    assert call_tool(_call(ctx), "get_fast", {}, via="mcp", tools=tools) == {"fast": True}  # finished: not abandoned


def test_cap_counts_running_and_abandoned_together():
    # code review #5: one abandoned worker plus one running call fill a cap of 2, so a third call is refused
    release, workers = threading.Event(), list[threading.Thread]()
    tools = (_blocking_tool(release, workers), _tool("get_fast", lambda _c, _a: {"fast": True}))
    ctx = _ctx(mcp_max_concurrent_calls=2, mcp_execution_timeout="300ms")
    running = threading.Thread(target=lambda: call_tool(_call(ctx), "get_slow", {}, via="mcp", tools=tools))
    try:
        with pytest.raises(RpcError):
            call_tool(_call(ctx), "get_slow", {}, via="mcp", tools=tools)  # times out: abandoned
        running.start()
        while len(workers) < 2:
            threading.Event().wait(0.01)
        with pytest.raises(RpcError) as refused:
            call_tool(_call(ctx), "get_fast", {}, via="mcp", tools=tools)
        assert refused.value.code == SERVER_AT_CAPACITY
    finally:
        release.set()
        running.join(5)
        for worker in workers:
            worker.join(5)
    assert tool_gate(ctx, "mcp")._slots._value == 2  # pyright: ignore[reportPrivateUsage]  # every slot came back


@pytest.mark.parametrize("name", [t.name for t in TOOLS if not t.action])
def test_mcp_tools_no_side_effects(name: str, no_side_effects: SideEffectGuard, tmp_state_dir: Path):
    # new: brief ruling (no socket, file, logger level or os.environ change)
    ctx = _ctx(state_dir=str(tmp_state_dir))
    arguments: dict[str, Any] = {}
    if name == "get_exception_detail":  # the one tool with a required argument: the id of a recorded exception
        store = ctx.capture.exceptions = ExceptionStore(10, 5, 20, ctx.masker)
        try:
            raise RuntimeError("for the detail")
        except RuntimeError as exc:
            store.record(exc, "log", None, "test")
        arguments = {"id": store.report()["groups"][0]["id"]}
    if name == "get_rest_api_rule_violations":  # needs a cached scan: seeded with one violating route
        route = ApiRouteInfo(("GET",), "/getPets", "app:read_pets", summary="s", tags=("t",))
        model = ApiModel((route,), ("app:on_error",), ())
        service = ctx.lazy("rest-api", lambda: RestApiService(lambda: model, DismissalStore(tmp_state_dir), ctx.masker,
                                                             SingleFlight(), max_retained=100))  # fmt: skip
        arguments = {"id": "RAPI-NAME-001", "scanId": service.scan()["violationDetails"]["scanId"]}
    no_side_effects.rebaseline()
    result = call_tool(_call(ctx, {"server": ("127.0.0.1", 8000)}), name, arguments, via="mcp")
    assert isinstance(result, dict)


def test_settings_default_mcp_off():
    # new: brief ruling (MCP is OFF by default)
    assert SharpitSettings().mcp_enabled == "OFF"
