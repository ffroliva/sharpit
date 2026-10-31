"""``McpServer.handle`` (port of BootUI ``BootUiMcpController.rpc`` and ``BootUiMcpService``).

Every row of contract §9 "HTTP-level responses" is one case of ``test_http_level_responses``.
Ported from ``BootUiMcpServiceTests`` (cited per test), adapted: ``serverInfo.name`` is ``"sharpit"``, the version is
sharpit's, the framework in the guidance is ``FastAPI``.
Dropped, with reason:
- ``advisorSchemaAndCodec*``, ``advisorCodecRejects*``, ``advisorByteBudget*``, ``advisorStaleSnapshot*``: no advisor
  tools in the MVP catalogue.
- ``toolResultSerializationFailure...``: kept as ``test_unserialisable_payload_is_internal_error`` (a Python payload
  that ``json`` cannot encode stands in for the throwing Jackson getter).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import pytest

from sharpit import __version__
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.context import SharpitContext
from sharpit.engine.mcp import DISABLED_MESSAGE, INSTRUCTIONS, PROTOCOL_VERSION, McpServer
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.engine.tools import TOOLS, CallContext, Tool, tool_gate
from sharpit.settings import PanelSettings, load_settings

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
JSON = {"content-type": "application/json"}
NONE_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


class FakeIntrospector:
    def app_info(self) -> AppInfo:
        return AppInfo("demo", "FastAPI", "0.115.0", None)

    def routes(self) -> list[RouteInfo]:
        return []

    def providers(self) -> list[ProviderInfo]:
        return []


def _ctx(**options: Any) -> SharpitContext:
    settings = load_settings({"config_scan": False, **options}, {})
    return SharpitContext(settings, ACTIVATION, FakeIntrospector())


def _server(*, enabled: bool = True, tools: tuple[Tool, ...] | None = None, **options: Any) -> McpServer:
    server = McpServer(_ctx(**options), tools=tools)
    server.enabled = enabled
    return server


def _post(server: McpServer, body: Any, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any] | None]:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    status, payload, _headers = server.handle(raw, headers or JSON, {"server": ("127.0.0.1", 8000)})
    return status, payload


def _rpc(method: str, rid: Any = 1, params: Any = None) -> dict[str, Any]:
    request: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if rid is not None:
        request["id"] = rid
    if params is not None:
        request["params"] = params
    return request


def _call(name: str, rid: Any = 1, arguments: Any = None) -> dict[str, Any]:
    return _rpc("tools/call", rid, {"name": name, "arguments": arguments if arguments is not None else {}})


def _err(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _overview_tool(payload: Any) -> Tool:
    return Tool("get_overview", "Read the overview.", NONE_SCHEMA, "overview", False, lambda _c, _a: payload)


PING = _rpc("ping")


@pytest.mark.parametrize(
    ("body", "headers", "status", "expected"),
    [
        # ported: AbstractMcpConformanceTest.testMcpNotificationReturns202 / testRecognizedMcpNotificationReturns202
        (_rpc("notifications/initialized", None), JSON, 202, None),
        (_rpc("ping", None), JSON, 202, None),
        ({"jsonrpc": "2.0", "id": None, "method": "ping"}, JSON, 202, None),
        # ported: testMcpRejectsOversizedRequestBeforeParsing (cap 64 bytes here; not even valid JSON)
        (b"{" + b"x" * 100, JSON, 413, _err(None, -32700, "Request payload exceeds limit")),
        (b"{not json", JSON, 400, _err(None, -32700, "Invalid JSON-RPC request")),
        (b"", JSON, 400, _err(None, -32700, "Invalid JSON-RPC request")),
        # ported: testMcpRejectsBatchRequests
        (
            [PING],
            JSON,
            400,
            _err(None, -32600, "JSON-RPC batch requests are not supported by MCP Streamable HTTP transport"),
        ),
        # ported: testMcpRejectsUnsupportedProtocolVersionHeader
        (
            PING,
            {**JSON, "mcp-protocol-version": "2099-01-01"},
            400,
            _err(None, -32600, "Unsupported MCP-Protocol-Version"),
        ),
        (PING, {**JSON, "MCP-Protocol-Version": PROTOCOL_VERSION}, 200, {"jsonrpc": "2.0", "id": 1, "result": {}}),
        # ported: testMcpRequiresJsonContentType (BootUI: framework 415)
        (PING, {"content-type": "text/plain"}, 415, {"error": "Unsupported Media Type"}),
        (PING, {"content-type": "application/json; charset=utf-8"}, 200, {"jsonrpc": "2.0", "id": 1, "result": {}}),
        ("ping", JSON, 200, _err(None, -32600, "Request must be a JSON-RPC object")),
        # ported: testMcpValidatesJsonrpc
        ({"id": 1, "method": "ping"}, JSON, 200, _err(1, -32600, 'Request must include jsonrpc: "2.0"')),
        (
            {"jsonrpc": "1.0", "id": 1, "method": "ping"},
            JSON,
            200,
            _err(1, -32600, 'Request must include jsonrpc: "2.0"'),
        ),
        # ported: BootUiMcpServiceTests.rejectsInvalidIdAndParamsTypes
        (
            {"jsonrpc": "2.0", "id": True, "method": "ping"},
            JSON,
            200,
            _err(None, -32600, "Request id must be a string, number, or null"),
        ),
        (
            {"jsonrpc": "2.0", "id": [1], "method": "ping"},
            JSON,
            200,
            _err(None, -32600, "Request id must be a string, number, or null"),
        ),
        (
            {"jsonrpc": "2.0", "id": 74, "method": "ping", "params": 1},
            JSON,
            200,
            _err(74, -32602, "Request params must be an object"),
        ),
        ({"jsonrpc": "2.0", "id": "a"}, JSON, 200, _err("a", -32602, "Missing 'method'")),
        # code review #15: a notification never gets a response body, even with invalid params
        ({"jsonrpc": "2.0", "method": "ping", "params": 1}, JSON, 202, None),
        ({"jsonrpc": "2.0", "id": None, "method": "x", "params": []}, JSON, 202, None),
    ],
)
def test_http_level_responses(body: Any, headers: dict[str, str], status: int, expected: dict[str, Any] | None):
    # ported: rows cited individually above (AbstractMcpConformanceTest, BootUiMcpServiceTests)
    assert _post(_server(mcp_max_payload_bytes=64), body, headers) == (status, expected)


def test_response_cap_counts_utf8_bytes():
    # ported: BootUiMcpServiceTests.rejectsOversizedRenderedResponse (cap 128 there; bytes, not characters, here)
    tools = (_overview_tool({"value": "é" * 100}),)  # each "é" is 1 character but 2 UTF-8 bytes
    rendered = _post(_server(tools=tools), _call("get_overview", 76))[1]
    text = json.dumps(rendered, ensure_ascii=False, separators=(",", ":"))  # what JSONResponse puts on the wire
    wire = len(text.encode())
    assert wire >= len(text) + 200
    capped = _server(tools=tools, mcp_max_response_bytes=wire - 1)  # still far above the character count
    message = "MCP response exceeds configured byte limit"
    assert _post(capped, _call("get_overview", 76)) == (200, _err(76, -32003, message))
    assert tool_gate(capped.ctx, "mcp").snapshot()["responseLimitRefusals"] == 1
    assert _post(_server(tools=tools, mcp_max_response_bytes=wire), _call("get_overview", 76))[1] == rendered


def test_mcp_disabled_by_default():
    # ported: AbstractMcpConformanceTest.testMcpDisabledShortCircuit / testDisabledMcpNotificationReturns202
    server = McpServer(_ctx())
    assert server.enabled is False
    assert _post(server, PING) == (200, _err(1, -32000, DISABLED_MESSAGE))
    assert DISABLED_MESSAGE == (
        "sharpit MCP server is disabled. Enable it from the MCP Server panel or set SHARPIT_MCP_ENABLED=ON."
    )
    assert _post(server, _rpc("ping", None)) == (202, None)
    assert _post(server, {"id": 9, "method": "ping"}) == (200, _err(9, -32000, DISABLED_MESSAGE))


@pytest.mark.parametrize(("mode", "enabled"), [("ON", True), ("AUTO", False), ("OFF", False)])
def test_only_on_enables(mode: str, enabled: bool):
    # ported: McpServerState (AUTO is off so the server is never silently exposed)
    assert McpServer(_ctx(mcp_enabled=mode)).enabled is enabled


def test_initialize_returns_server_info_and_echoes_protocol_version():
    # ported: BootUiMcpServiceTests.initializeReturnsServerInfoAndEchoesProtocolVersion,
    # AbstractMcpConformanceTest.testMcpInitializeWhenEnabled
    status, body = _post(_server(), _rpc("initialize", 1, {"protocolVersion": PROTOCOL_VERSION}))
    assert status == 200 and body is not None
    result = body["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"] == {"name": "sharpit", "version": __version__}
    assert result["capabilities"] == {"tools": {"listChanged": False}, "prompts": {"listChanged": False}}
    assert result["instructions"].startswith("sharpit exposes a running FastAPI application for local diagnosis.")
    for fragment in ("get_overview", "do not modify code blindly", "may still contain sensitive data"):
        assert fragment in result["instructions"]


@pytest.mark.parametrize("params", [{}, {"protocolVersion": "2099-01-01"}])
def test_initialize_falls_back_to_default_protocol_version(params: dict[str, Any]):
    # ported: BootUiMcpServiceTests.initializeFallsBackToDefaultProtocolVersion,
    # AbstractMcpConformanceTest.testMcpInitiateVersionNegotiation
    body = _post(_server(), _rpc("initialize", 1, params))[1]
    assert body is not None and body["result"]["protocolVersion"] == PROTOCOL_VERSION


def test_ping():
    # ported: AbstractMcpConformanceTest.testMcpPingWhenEnabled
    assert _post(_server(), PING) == (200, {"jsonrpc": "2.0", "id": 1, "result": {}})


def test_tools_list_has_no_action_tool():
    # ported: BootUiMcpServiceTests.toolsListAdvertisesEveryTool, AbstractMcpConformanceTest.testMcpToolsListWhenEnabled
    body = _post(_server(), _rpc("tools/list", 2))[1]
    assert body is not None
    tools = body["result"]["tools"]
    assert [t["name"] for t in tools] == [
        "get_overview",
        "get_config",
        "get_mappings",
        "get_loggers",
        "get_beans",
        "get_http_exchanges",
        "get_log_tail",
        "get_exceptions",
        "get_exception_detail",
        "get_sql_traces",
        "get_vulnerabilities_report",
    ]
    first = tools[0]
    assert set(first) == {"name", "description", "inputSchema", "outputSchema"}
    assert first["inputSchema"]["type"] == "object"
    assert first["outputSchema"] == {
        "type": "object",
        "description": "Structured sharpit result for get_overview. Fields may evolve with the panel DTO contract.",
    }


def test_mcp_call_action_tool_unknown_32602():
    # new: brief ruling (action tools are unknown over MCP)
    assert _post(_server(), _call("vulnerabilities_scan", 7)) == (
        200,
        _err(7, -32602, "Unknown tool: vulnerabilities_scan"),
    )


def test_unknown_tool_retains_safe_actionable_error():
    # ported: AbstractMcpConformanceTest.testMcpUnknownToolRetainsSafeActionableError,
    # BootUiMcpServiceTests.unknownToolReturnsInvalidParamsError
    request = _rpc("tools/call", 7, {"name": "does_not_exist"})
    assert _post(_server(), request) == (200, _err(7, -32602, "Unknown tool: does_not_exist"))


def test_unknown_method_32601():
    # ported: BootUiMcpServiceTests.unknownMethodReturnsJsonRpcMethodNotFound
    assert _post(_server(), _rpc("tools/unknown", 8)) == (200, _err(8, -32601, "Unknown method: tools/unknown"))


def test_tools_call_returns_serialized_dto_content():
    # ported: BootUiMcpServiceTests.toolsCallReturnsSerializedDtoContent
    body = _post(_server(tools=(_overview_tool({"name": "demo"}),)), _call("get_overview", 3))[1]
    assert body == {
        "jsonrpc": "2.0",
        "id": 3,
        "result": {
            "content": [{"type": "text", "text": '{"name":"demo"}'}],
            "structuredContent": {"name": "demo"},
            "isError": False,
        },
    }


def test_tool_call_arguments_null_and_non_object():
    # ported: BootUiMcpServiceTests.toolCallRejectsNonObjectAndUnexpectedArguments
    server = _server()
    bad = _rpc("tools/call", 71, {"name": "get_overview", "arguments": "invalid"})
    assert _post(server, bad)[1] == _err(71, -32602, "Tool arguments must be an object")
    null = _rpc("tools/call", 72, {"name": "get_overview", "arguments": None})
    assert _post(server, null)[1] == _err(72, -32602, "Tool arguments must be an object")
    absent = _rpc("tools/call", 73, {"name": "get_overview"})
    body = _post(server, absent)[1]
    assert body is not None and body["result"]["isError"] is False


def test_disabled_panel_is_in_band_error():
    # ported: BootUiMcpServiceTests.toolsCallOnDisabledPanelReturnsInBandError
    server = _server(panels={"overview": PanelSettings(enabled=False)})
    assert _post(server, _call("get_overview", 4))[1] == {
        "jsonrpc": "2.0",
        "id": 4,
        "result": {
            "content": [{"type": "text", "text": "Panel is disabled via SHARPIT_PANELS_OVERVIEW_ENABLED=false"}],
            "isError": True,
        },
    }


def test_handler_exception_is_canonical_internal_error(caplog: pytest.LogCaptureFixture):
    # ported: BootUiMcpServiceTests.toolHandlerExceptionReturnsCanonicalInternalErrorWithoutSensitiveDetails
    def boom(_c: CallContext, _a: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("token=ghp_secret jdbc:mysql://localhost/private /home/admin/key.pem")

    tool = Tool("get_overview", "Read the overview.", NONE_SCHEMA, "overview", False, boom)
    status, body = _post(_server(tools=(tool,)), _call("get_overview", 9))
    assert (status, json.dumps(body, separators=(",", ":"))) == (
        200,
        '{"jsonrpc":"2.0","id":9,"error":{"code":-32603,"message":"Internal error"}}',
    )
    assert sum(1 for r in caplog.records if r.levelno == logging.ERROR) == 1


def test_handler_exception_for_notification_produces_no_body(caplog: pytest.LogCaptureFixture):
    # ported: BootUiMcpServiceTests.toolHandlerExceptionForNotificationProducesNoBodyAndIsReportedOnce
    def boom(_c: CallContext, _a: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("SENSITIVE_NOTIFICATION_SENTINEL")

    tool = Tool("get_overview", "Read the overview.", NONE_SCHEMA, "overview", False, boom)
    assert _post(_server(tools=(tool,)), _call("get_overview", None)) == (202, None)
    assert sum(1 for r in caplog.records if r.levelno == logging.ERROR) == 1


def test_unserialisable_payload_is_internal_error(caplog: pytest.LogCaptureFixture):
    # ported: BootUiMcpServiceTests.toolResultSerializationFailureReturnsCanonicalInternalErrorAndIsReportedOnce
    status, body = _post(_server(tools=(_overview_tool({"value": object()}),)), _call("get_overview", 10))
    assert (status, body) == (200, _err(10, -32603, "Internal error"))
    assert sum(1 for r in caplog.records if r.levelno == logging.ERROR) == 1


def test_prompts_list_and_get():
    # ported: BootUiMcpServiceTests.promptsListAndGetExposeDiagnosticWorkflows,
    # AbstractMcpConformanceTest.testMcpPromptsWhenEnabled
    server = _server()
    body = _post(server, _rpc("prompts/list", 3))[1]
    assert body is not None
    prompts = body["result"]["prompts"]
    assert [p["name"] for p in prompts] == ["diagnose_runtime_issue", "review_application", "assess_application"]
    assert all(p["arguments"] == [] and isinstance(p["description"], str) for p in prompts)
    for prompt in prompts:
        got = _post(server, _rpc("prompts/get", 4, {"name": prompt["name"]}))[1]
        assert got is not None
        result = got["result"]
        assert result["description"] == prompt["description"]
        assert len(result["messages"]) == 1
        message = result["messages"][0]
        assert message["role"] == "user" and message["content"]["type"] == "text"
        assert message["content"]["text"].strip()
        assert "BootUI" not in message["content"]["text"]
    diagnose = _post(server, _rpc("prompts/get", 4, {"name": "diagnose_runtime_issue"}))[1]
    assert diagnose is not None
    text = diagnose["result"]["messages"][0]["content"]["text"]
    assert "Separate observed evidence from hypotheses" in text
    assert "this FastAPI application" in text
    assess = _post(server, _rpc("prompts/get", 5, {"name": "assess_application"}))[1]
    assert assess is not None
    text = assess["result"]["messages"][0]["content"]["text"]
    for fragment in (
        "Start with existing evidence only",
        "STOP after presenting the plan",
        "specific plan version",
        "external agent host's permissions",
        "rule AND affected target",
        "using sharpit and its source repository",
    ):
        assert fragment in text


SHARPIT_TOOLS = {t.name for t in TOOLS}


def _guidance_texts() -> list[str]:
    server = _server()
    texts = [INSTRUCTIONS]
    for name in ("diagnose_runtime_issue", "review_application", "assess_application"):
        got = _post(server, _rpc("prompts/get", 9, {"name": name}))[1]
        assert got is not None
        texts.append(got["result"]["messages"][0]["content"]["text"])
    return texts


def test_guidance_names_only_sharpit_tools():
    # new: review ruling (prompts and instructions name only the seven sharpit tools)
    for text in _guidance_texts():
        named = set(re.findall(r"\bget_\w+|\b\w+_scan\b", text))
        assert named <= SHARPIT_TOOLS, named - SHARPIT_TOOLS
    assert "vulnerabilities_scan" in INSTRUCTIONS and "CLI" in INSTRUCTIONS and "OSV" in INSTRUCTIONS


def test_guidance_is_python_not_jvm():
    # new: review ruling (FastAPI wording, no JVM vocabulary)
    for text in _guidance_texts():
        assert not re.search(r"\b(Spring|JVM|GC|Quarkus|BootUI)\b", text), text


def test_prompts_get_unknown():
    # adapted: BootUiMcpService.getPrompt (unknown and missing prompt name)
    server = _server()
    assert _post(server, _rpc("prompts/get", 6, {"name": "nope"}))[1] == _err(6, -32602, "Unknown prompt: nope")
    assert _post(server, _rpc("prompts/get", 6, {}))[1] == _err(6, -32602, "Missing prompt name")
