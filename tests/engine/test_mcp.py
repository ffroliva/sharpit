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
from sharpit.engine.mcp import DISABLED_MESSAGE, INSTRUCTIONS, PROMPTS, PROTOCOL_VERSION, McpServer
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.engine.tools import COMMANDS, TOOLS, CallContext, Tool, tool_gate
from sharpit.settings import PanelSettings, load_settings
from surface import BASE_MCP_TOOL_NAMES, expected_mcp_tool_names

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
    assert status == 200
    assert body is not None
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
    assert body is not None
    assert body["result"]["protocolVersion"] == PROTOCOL_VERSION


def test_ping():
    # ported: AbstractMcpConformanceTest.testMcpPingWhenEnabled
    assert _post(_server(), PING) == (200, {"jsonrpc": "2.0", "id": 1, "result": {}})


def test_tools_list_has_no_action_tool():
    # ported: BootUiMcpServiceTests.toolsListAdvertisesEveryTool, AbstractMcpConformanceTest.testMcpToolsListWhenEnabled
    body = _post(_server(), _rpc("tools/list", 2))[1]
    assert body is not None
    tools = body["result"]["tools"]
    names = [t["name"] for t in tools]
    assert names[: len(BASE_MCP_TOOL_NAMES)] == BASE_MCP_TOOL_NAMES
    assert names == expected_mcp_tool_names()  # plus each implemented 0.4 panel's read tools
    assert "rest_api_scan" not in {t["name"] for t in tools}
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
    assert body is not None
    assert body["result"]["isError"] is False


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


def test_prompts_list_and_get(no_side_effects):
    # ported: McpDispatcherTests.promptsListAdvertisesEveryPrompt,
    # McpDispatcherTests.promptsGetReturnsPrompt, AbstractMcpConformanceTest.testMcpPromptsWhenEnabled
    server = _server()
    body = _post(server, _rpc("prompts/list", 3))[1]
    assert body is not None
    prompts = body["result"]["prompts"]
    assert [p["name"] for p in prompts] == [
        "diagnose_runtime_issue",
        "verify_after_change",
        "review_application",
        "assess_application",
    ]
    expected_arguments = {
        "diagnose_runtime_issue": ["symptom", "route"],
        "verify_after_change": ["change", "route"],
        "review_application": ["focus"],
        "assess_application": ["goal"],
    }
    for prompt in prompts:
        assert [arg["name"] for arg in prompt["arguments"]] == expected_arguments[prompt["name"]]
        assert all(arg["description"] and arg["required"] is False for arg in prompt["arguments"])
        assert isinstance(prompt["description"], str)
    for prompt in prompts:
        got = _post(server, _rpc("prompts/get", 4, {"name": prompt["name"]}))[1]
        assert got is not None
        result = got["result"]
        assert result["description"] == prompt["description"]
        assert len(result["messages"]) == 1
        message = result["messages"][0]
        assert message["role"] == "user"
        assert message["content"]["type"] == "text"
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
    contextual = _post(
        server,
        _rpc(
            "prompts/get",
            6,
            {
                "name": "diagnose_runtime_issue",
                "arguments": {"symptom": "sk_live_12345678901234567890", "route": "  GET /orders  "},
            },
        ),
    )[1]
    assert contextual is not None
    rendered = contextual["result"]["messages"][0]["content"]["text"]
    assert (
        "Context the user supplied; use it to focus the steps above, and verify it against sharpit "
        "evidence rather than assume it:" in rendered
    )
    assert "- The symptom the user reports: ******" in rendered
    assert "- The route, job, or listener involved: GET /orders" in rendered
    assert "sk_live_12345678901234567890" not in rendered
    assert "..." not in rendered


SHARPIT_TOOLS = {t.name for t in TOOLS}


def _guidance_texts() -> list[str]:
    server = _server()
    texts = [INSTRUCTIONS]
    for prompt in PROMPTS:
        got = _post(server, _rpc("prompts/get", 9, {"name": prompt.name}))[1]
        assert got is not None
        texts.append(got["result"]["messages"][0]["content"]["text"])
    return texts


def test_guidance_names_only_sharpit_tools(no_side_effects):
    # new: review ruling (every cited tool exists in the sharpit catalogue)
    for text in _guidance_texts():
        named = set(
            re.findall(
                r"\b(?:get|clear|pause|resume|enable|disable|vulnerabilities|rest_api|security|database_advisor|"
                r"architecture|fastapi|postgresql|mysql)_[a-z0-9_]+\b",
                text,
            )
        )
        assert named <= SHARPIT_TOOLS, named - SHARPIT_TOOLS
    assert "vulnerabilities_scan" in INSTRUCTIONS
    assert "CLI" in INSTRUCTIONS
    assert "OSV" in INSTRUCTIONS


def test_guidance_is_python_not_jvm(no_side_effects):
    # new: review ruling (FastAPI wording, no JVM vocabulary)
    for text in _guidance_texts():
        assert not re.search(r"\b(Spring|JVM|GC|Quarkus|BootUI)\b", text), text


def test_prompt_text_has_no_internal_plan_jargon():
    # ported: UserFacingPlanJargonTests.everyMcpDescriptionInstructionAndPromptIsPlain
    forbidden = re.compile(
        r"PLAN(-v2)?\.md|PLAN-v2|V2-VALIDATION|\bM[0-9]+-[0-9]+\b|\bD[0-9]{2}\b|"
        r"§\s?[0-9]|(?i:validat\w* (on|against) real applications|external(ly)? validat|"
        r"validation (application|run)|not (yet )?validated|reviewers?\b|adjudicat|per-kind gate|seeded case|"
        r"counterexample|judged by|not judged yet|too few facts)"
    )
    texts = [INSTRUCTIONS, *(tool.description for tool in TOOLS)]
    texts.extend(prompt.description + " " + prompt.text for prompt in PROMPTS)
    for text in texts:
        assert forbidden.search(text) is None


def test_prompts_get_unknown(no_side_effects):
    # ported: McpDispatcherTests.promptsGetValidatesName
    server = _server()
    assert _post(server, _rpc("prompts/get", 6, {"name": "nope"}))[1] == _err(6, -32602, "Unknown prompt: nope")
    assert _post(server, _rpc("prompts/get", 6, {}))[1] == _err(6, -32602, "Missing prompt name")


def test_prompts_get_renders_declared_arguments_and_refuses_undeclared_ones(no_side_effects):
    # ported: McpDispatcherTests.promptsGetRendersDeclaredArgumentsAndRefusesUndeclaredOnes
    server = _server()
    blank = _post(server, _rpc("prompts/get", 7, {"name": "diagnose_runtime_issue", "arguments": {"route": "  "}}))[1]
    assert blank is not None
    blank_text = blank["result"]["messages"][0]["content"]["text"]
    assert "Context the user supplied" not in blank_text
    rendered = _post(
        server,
        _rpc("prompts/get", 8, {"name": "diagnose_runtime_issue", "arguments": {"symptom": "x" * 501}}),
    )[1]
    assert rendered is not None
    rendered_text = rendered["result"]["messages"][0]["content"]["text"]
    assert rendered_text.endswith("- The symptom the user reports: " + "x" * 500 + "...")
    unknown = _post(
        server,
        _rpc("prompts/get", 9, {"name": "diagnose_runtime_issue", "arguments": {"sympton": "typo"}}),
    )[1]
    assert unknown == _err(
        9, -32602, "Unknown argument for prompt diagnose_runtime_issue: sympton. It takes route, symptom."
    )
    malformed = _post(server, _rpc("prompts/get", 11, {"name": "diagnose_runtime_issue", "arguments": []}))[1]
    assert malformed == _err(11, -32602, "Prompt arguments must be an object")
    wrong_type = _post(
        server,
        _rpc("prompts/get", 12, {"name": "diagnose_runtime_issue", "arguments": {"symptom": 5}}),
    )[1]
    assert wrong_type == _err(12, -32602, "Argument 'symptom' must be a string")


def test_prompt_argument_truncation_keeps_a_unicode_character_whole(no_side_effects):
    # ported: McpDispatcherTests.aBoundedPromptArgumentNeverSplitsASurrogatePair
    value = "x" * 499 + "😀tail"
    response = _post(
        _server(),
        _rpc("prompts/get", 10, {"name": "diagnose_runtime_issue", "arguments": {"symptom": value}}),
    )[1]
    assert response is not None
    rendered = response["result"]["messages"][0]["content"]["text"]
    assert rendered.endswith("- The symptom the user reports: " + "x" * 499 + "...")


def test_prompt_errors_mask_prompt_and_argument_names(no_side_effects):
    # new: sharpit safety model masks MCP error text, including caller-supplied names
    secret_name = "sk_live_12345678901234567890"
    unknown_prompt = _post(_server(), _rpc("prompts/get", 13, {"name": secret_name}))[1]
    unknown_argument = _post(
        _server(),
        _rpc("prompts/get", 14, {"name": "diagnose_runtime_issue", "arguments": {secret_name: "x"}}),
    )[1]
    assert "sk_live_12345678901234567890" not in json.dumps([unknown_prompt, unknown_argument])
    assert "******" in json.dumps([unknown_prompt, unknown_argument])


def test_prompt_arguments_match_java_whitespace_and_mask_after_strip(no_side_effects):
    # ported: McpDispatcherTests.promptsGetRendersDeclaredArgumentsAndRefusesUndeclaredOnes
    server = _server()
    for blank in ("\u00a0", "\u2007", "\u202f"):
        response = _post(
            server,
            _rpc("prompts/get", 15, {"name": "diagnose_runtime_issue", "arguments": {"route": blank}}),
        )[1]
        assert "Context the user supplied" in response["result"]["messages"][0]["content"]["text"]
    response = _post(
        server,
        _rpc("prompts/get", 16, {"name": "diagnose_runtime_issue", "arguments": {"symptom": "  sk_live_12345678901234567890  "}}),
    )[1]
    rendered = response["result"]["messages"][0]["content"]["text"]
    assert "- The symptom the user reports: ******" in rendered
    assert "  ******  " not in rendered


def test_prompt_named_action_tools_are_cli_only_with_commands(no_side_effects):
    # new: sharpit MCP actions remain CLI-only and prompt guidance names their command
    action_commands = {tool.name: COMMANDS[tool.name] for tool in TOOLS if tool.action}
    for prompt in PROMPTS:
        for name, command in action_commands.items():
            if name in prompt.text:
                assert "CLI" in prompt.text
                assert f"sharpit {command}" in prompt.text


def test_verify_after_change_uses_available_repeat_insights_without_prior_run_claim(no_side_effects):
    # review fix: sharpit runtime insights expose both queries but no previous-run comparison
    prompt = next(p for p in PROMPTS if p.name == "verify_after_change")
    assert "repeated-selects" in prompt.text
    assert "lazy-sql-after-handler" in prompt.text
    assert "previous run" not in prompt.description.lower()
    assert "previous one" not in prompt.description.lower()
    assert "route or test the change should affect" not in next(a for a in prompt.arguments if a.name == "route").description


# --- lane D4: BootUI 2.2.0 protocol revisions and status counters ---------------------------------------------------


def test_initialize_negotiates_only_the_known_revision():
    # ported: McpEraResolverTests.initializeIsAlwaysLegacyEvenWithModernMeta
    body = _post(_server(), _rpc("initialize", 1, {"protocolVersion": "2026-07-28"}))[1]
    assert body is not None
    assert body["result"]["protocolVersion"] == "2025-06-18"


def test_a_modern_header_on_initialize_is_refused():
    status, body = _post(
        _server(),
        _rpc("initialize", 1, {"protocolVersion": "2026-07-28"}),
        {**JSON, "MCP-Protocol-Version": "2026-07-28"},
    )
    assert status == 400
    assert body == _err(None, -32600, "Unsupported MCP-Protocol-Version")


def test_a_modern_header_without_meta_is_malformed():
    # ported: McpEraResolverTests.aModernHeaderWithoutModernMetaIsAMalformedModernRequest
    status, body = _post(_server(), _rpc("tools/list", 2), {**JSON, "MCP-Protocol-Version": "2026-07-28"})
    assert status == 400
    assert body == _err(2, -32602, "Missing required _meta field: io.modelcontextprotocol/protocolVersion")


def test_a_modern_header_on_a_batch_gets_the_batch_refusal():
    status, body = _post(
        _server(),
        [_rpc("tools/list", 1)],
        {**JSON, "MCP-Protocol-Version": "2026-07-28"},
    )
    assert status == 400
    assert body == _err(None, -32600, "JSON-RPC batch requests are not supported by MCP Streamable HTTP transport")


def test_a_modern_header_on_a_scalar_gets_missing_meta_refusal():
    status, body = _post(_server(), 42, {**JSON, "MCP-Protocol-Version": "2026-07-28"})
    assert status == 400
    assert body == _err(None, -32602, "Missing required _meta field: io.modelcontextprotocol/protocolVersion")


def test_disabled_server_refuses_modern_request_before_disabled_check():
    status, body = _post(_server(enabled=False), _rpc("tools/list", 1), {**JSON, "MCP-Protocol-Version": "2026-07-28"})
    assert status == 400
    assert body == _err(1, -32602, "Missing required _meta field: io.modelcontextprotocol/protocolVersion")


def test_disabled_server_accepts_modern_notification():
    status, body = _post(
        _server(enabled=False),
        _rpc("notifications/initialized", None),
        {**JSON, "MCP-Protocol-Version": "2026-07-28"},
    )
    assert (status, body) == (202, None)


def test_a_modern_header_on_a_notification_is_accepted():
    status, body = _post(
        _server(), _rpc("notifications/initialized", None), {**JSON, "MCP-Protocol-Version": "2026-07-28"}
    )
    assert (status, body) == (202, None)


def test_a_modern_request_with_meta_is_refused_until_built():
    status, body = _post(
        _server(),
        _rpc("tools/list", 3, {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}),
        {**JSON, "MCP-Protocol-Version": "2026-07-28"},
    )
    assert status == 400
    assert body == _err(None, -32600, "Unsupported MCP-Protocol-Version")


def test_status_keeps_bootuis_supported_list():
    assert _server().status()["supportedProtocolVersions"] == ["2026-07-28", "2025-06-18"]


def test_cancellations_and_progress_dropped_status():
    server = _server()
    cancel = _rpc("notifications/cancelled", None, {"requestId": 7, "reason": "user"})
    assert _post(server, cancel) == (202, None)
    status = server.status()
    assert status["cancellations"] == 1
    assert status["progressDropped"] == 0


def test_mcp_progress_token_in_meta_is_accepted():
    # ported: McpProtocolTests.acceptsProgressTokenMeta (no streaming: the call answers in one JSON response)
    server = _server(tools=(_overview_tool({"ok": True}),))
    request = _rpc("tools/call", 3, {"name": "get_overview", "arguments": {}, "_meta": {"progressToken": "p-1"}})
    body = _post(server, request)[1] or {}
    assert body.get("result", {}).get("structuredContent") == {"ok": True}
    assert server.status().get("progressDropped") == 0
