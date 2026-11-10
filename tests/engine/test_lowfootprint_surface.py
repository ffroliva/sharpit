from __future__ import annotations

import gc

from sharpit.engine.context import SharpitContext
from sharpit.engine.lowfootprint import LowFootprintService
from sharpit.engine.tools import COMMANDS, TOOLS
from sharpit.settings import load_settings


def test_low_footprint_catalog_matches_bootui_without_arguments() -> None:
    tools = [
        tool for tool in TOOLS if tool.name in {"get_low_footprint", "enable_low_footprint", "disable_low_footprint"}
    ]
    assert [tool.name for tool in tools] == ["get_low_footprint", "enable_low_footprint", "disable_low_footprint"]
    assert {name: COMMANDS[name] for name in (tool.name for tool in tools)} == {
        "get_low_footprint": "low-footprint status",
        "enable_low_footprint": "low-footprint enable",
        "disable_low_footprint": "low-footprint disable",
    }
    assert all(
        tool.input_schema == {"type": "object", "properties": {}, "additionalProperties": False} for tool in tools
    )
    assert [tool.action for tool in tools] == [False, True, True]
    assert [tool.description for tool in tools] == [
        "Read low-footprint mode without changing recording: active, sinceEpochMillis, agentAttached, components "
        "with suspension outcomes, and warnings. The Java agent is not paused.",
        "Enable low-footprint mode: pause sharpit recording, irreversibly discard buffered diagnostics, and request "
        "GC (which may not reclaim every buffer). Ask for approval first. Idempotent: enabling again does not clear "
        "or request GC again. Returns a compact acknowledgement with offload totals and failures; get_low_footprint "
        "lists component outcomes. The Java agent keeps running.",
        "Disable low-footprint mode and release its recording hold. Cleared data cannot be recovered; individually "
        "paused recorders stay paused. Ask for approval first. Idempotent. Returns a compact acknowledgement with "
        "state and warnings; get_low_footprint lists component outcomes.",
    ]


def test_low_footprint_actions_are_cli_only() -> None:
    from sharpit.engine.mcp import McpServer

    settings = load_settings({"enabled": "ON", "show_banner": False, "config_scan": False}, {})
    ctx = SharpitContext(settings=settings, activation=None, introspector=None)  # type: ignore[arg-type]
    listed = McpServer(ctx)._dispatch("tools/list", {}, {})["tools"]  # pyright: ignore[reportPrivateUsage]
    assert "get_low_footprint" in {tool["name"] for tool in listed}
    assert "enable_low_footprint" not in {tool["name"] for tool in listed}
    assert "disable_low_footprint" not in {tool["name"] for tool in listed}


def test_free_on_idle_settings_use_bootui_defaults_and_fail_safe() -> None:
    defaults = load_settings({}, {})
    assert defaults.free_on_idle_enabled is True
    assert defaults.free_on_idle_timeout == 300
    invalid = load_settings({}, {"SHARPIT_FREE_ON_IDLE_ENABLED": "invalid", "SHARPIT_FREE_ON_IDLE_TIMEOUT": "0"})
    assert invalid.free_on_idle_enabled is True
    assert invalid.free_on_idle_timeout == 300
    assert len(invalid.warnings) == 2


def test_low_footprint_tool_reads_and_toggles_registry() -> None:
    settings = load_settings({"enabled": "ON", "show_banner": False, "config_scan": False}, {})
    ctx = SharpitContext(settings=settings, activation=None, introspector=None)  # type: ignore[arg-type]
    hook = type(
        "Hook",
        (),
        {
            "name": "capture",
            "suspend": lambda self: setattr(self, "running", False),
            "resume": lambda self: setattr(self, "running", True),
        },
    )()
    hook.running = True
    ctx.capture.hooks.register(hook)
    ctx.lazy("low-footprint", lambda: LowFootprintService(ctx.capture.hooks))
    from sharpit.engine.tools import CallContext, call_tool

    call = CallContext(ctx, {})
    assert call_tool(call, "get_low_footprint", {}, via="mcp")["active"] is False
    assert call_tool(call, "enable_low_footprint", {}, via="cli")["active"] is True
    assert hook.running is False
    assert call_tool(call, "disable_low_footprint", {}, via="cli")["active"] is False
    assert hook.running is True


def test_resume_recording_actions_refuse_while_low_footprint_is_active() -> None:
    from sharpit.engine.tools import CallContext, ToolCallError, call_tool
    from sharpit.engine.tools_lowfootprint import _service

    settings = load_settings({"enabled": "ON", "show_banner": False, "config_scan": False}, {})
    ctx = SharpitContext(settings=settings, activation=None, introspector=None)  # type: ignore[arg-type]
    call = CallContext(ctx, {})
    _service(call).suspend()
    for name in ("resume_sql_trace_recording", "resume_transaction_recording"):
        try:
            call_tool(call, name, {}, via="cli")
        except ToolCallError as exc:
            assert exc.status == 409
        else:
            raise AssertionError(f"{name} resumed while low-footprint was active")


def test_enable_low_footprint_requests_gc_once(monkeypatch) -> None:
    settings = load_settings({"enabled": "ON", "show_banner": False, "config_scan": False}, {})
    ctx = SharpitContext(settings=settings, activation=None, introspector=None)  # type: ignore[arg-type]
    requests: list[None] = []
    monkeypatch.setattr(gc, "collect", lambda: requests.append(None))
    from sharpit.engine.tools import CallContext, call_tool

    call = CallContext(ctx, {})
    call_tool(call, "enable_low_footprint", {}, via="cli")
    call_tool(call, "enable_low_footprint", {}, via="cli")
    assert requests == [None]


def test_low_footprint_status_masks_registry_failures() -> None:
    settings = load_settings({"enabled": "ON", "show_banner": False, "config_scan": False}, {})
    ctx = SharpitContext(settings=settings, activation=None, introspector=None)  # type: ignore[arg-type]

    class FailingHook:
        name = "capture"

        def suspend(self) -> None:
            raise RuntimeError("password=low-footprint-secret")

        def resume(self) -> None:
            return None

    ctx.capture.hooks.register(FailingHook())
    ctx.lazy("low-footprint", lambda: LowFootprintService(ctx.capture.hooks))
    from sharpit.engine.tools import CallContext, call_tool

    status = call_tool(CallContext(ctx, {}), "enable_low_footprint", {}, via="cli")
    assert "low-footprint-secret" not in str(status)
    assert status["warnings"] == ["Could not pause capture: RuntimeError: password=******"]


def test_resume_recording_refusal_matches_bootui_hint() -> None:
    # ported: McpLowFootprintTests.resumesAndNewProbesAreRefusedBeforeTheirHandlerButRunAfterTheHoldIsReleased
    from sharpit.engine.context import SharpitContext
    from sharpit.engine.lowfootprint import LowFootprintService
    from sharpit.engine.tools import CallContext, ToolCallError, call_tool

    settings = load_settings({"enabled": "ON", "show_banner": False, "config_scan": False}, {})
    ctx = SharpitContext(settings=settings, activation=None, introspector=None)  # type: ignore[arg-type]
    ctx.lazy("low-footprint", lambda: LowFootprintService(ctx.capture.hooks)).suspend()
    for name in ("resume_sql_trace_recording", "resume_transaction_recording"):
        try:
            call_tool(CallContext(ctx, {}), name, {}, via="cli")
        except ToolCallError as exc:
            assert exc.status == 409
            assert exc.message == (
                f"Cannot run {name}. "
                "Recording is held by low-footprint mode, not a quiet application. "
                "Call disable_low_footprint (bootui low-footprint disable) to resume; cleared data is gone. "
                "Native statistics and Java-agent instrumentation may still run."
            )
        else:
            raise AssertionError(f"{name} ran while low-footprint was active")
