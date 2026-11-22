from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.context import SharpitContext
from sharpit.engine.tools import CallContext, ToolCallError, call_tool
from sharpit.engine.tools04 import database_advisor, mysql, pentesting, postgresql
from sharpit.settings import load_settings


class _Introspector:
    def app_info(self) -> None:
        return None

    def routes(self) -> list[Any]:
        return []

    def providers(self) -> list[Any]:
        return []


class _LoopProvider:
    def __init__(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self.loop = loop

    def current_loop(self) -> asyncio.AbstractEventLoop | None:
        return self.loop


def _call(ctx: SharpitContext, loop: asyncio.AbstractEventLoop | None) -> CallContext:
    call = CallContext(ctx, {})
    object.__setattr__(call, "host_loop_provider", _LoopProvider(loop))
    return call


def _context() -> SharpitContext:
    return SharpitContext(
        load_settings({"enabled": "ON", "mcp_enabled": "ON", "cli_enabled": True}, {}),
        ActivationStatus(True, True, "Enabled", ()),
        _Introspector(),
    )


class _LiveLoop:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run)
        self.thread.start()
        assert self.ready.wait(1)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        self.loop.run_forever()

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(1)
        self.loop.close()


def _install_spies(monkeypatch: pytest.MonkeyPatch, ctx: SharpitContext) -> dict[str, list[asyncio.AbstractEventLoop]]:
    seen: dict[str, list[asyncio.AbstractEventLoop]] = {
        name: [] for name in ("pentest", "mysql_read", "postgresql", "advisor")
    }

    def coroutine(name: str, value: dict[str, Any]):
        async def run(*_args: object) -> dict[str, Any]:
            seen[name].append(asyncio.get_running_loop())
            return value

        return run

    monkeypatch.setattr(pentesting, "TOOL_WAIT_TIMEOUT", 1)
    monkeypatch.setattr(mysql, "TOOL_WAIT_TIMEOUT", 1)
    monkeypatch.setattr(postgresql, "TOOL_WAIT_TIMEOUT", 1)
    monkeypatch.setattr(database_advisor, "TOOL_WAIT_TIMEOUT", 1)
    monkeypatch.setattr(mysql, "refresh_mysql", coroutine("mysql_read", {}))
    monkeypatch.setattr(mysql, "summary", lambda value: value)
    monkeypatch.setattr(postgresql, "refresh_postgresql", coroutine("postgresql", {}))
    monkeypatch.setattr(postgresql, "summary", lambda value: value)
    monkeypatch.setattr(database_advisor, "run_scan", coroutine("advisor", {}))
    monkeypatch.setattr(database_advisor, "database_advisor_service", lambda _ctx: object())
    monkeypatch.setattr(database_advisor, "_has_async_engine", lambda _ctx: False)
    ctx.lazy(
        "pentesting_action",
        lambda: coroutine(
            "pentest", {"findings": [], "scan": {}, "findingsFound": 0, "severityCounts": {}, "evidence": {}}
        ),
    )
    return seen


def test_each_tool_uses_the_loop_serving_its_request(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _context()
    first, second = _LiveLoop(), _LiveLoop()
    ctx.capture.loop = first.loop  # shared capture state is deliberately stale on the second invocation
    seen = _install_spies(monkeypatch, ctx)
    try:
        for loop in (second.loop, first.loop):
            for name in ("pentest_scan", "mysql_read", "postgresql_read", "database_advisor_scan"):
                call_tool(_call(ctx, loop), name, {}, via="cli")
        for loops in seen.values():
            assert loops == [second.loop, first.loop]
    finally:
        first.close()
        second.close()


def test_closed_request_loop_does_not_fall_back_to_another_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _context()
    stale = _LiveLoop()
    closed = asyncio.new_event_loop()
    closed.close()
    _install_spies(monkeypatch, ctx)
    ctx.capture.loop = stale.loop
    try:
        with pytest.raises(ToolCallError) as caught:
            call_tool(_call(ctx, closed), "pentest_scan", {}, via="cli")
        assert caught.value.status == 503
        assert str(caught.value) == "Pentesting scan is unavailable: the application's event loop is not running."
    finally:
        stale.close()


def test_wsgi_without_request_loop_returns_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _context()
    _install_spies(monkeypatch, ctx)
    with pytest.raises(ToolCallError) as caught:
        call_tool(_call(ctx, None), "pentest_scan", {}, via="cli")
    assert caught.value.status == 503
    assert str(caught.value) == "Pentesting scan is unavailable: the application's event loop is not running."


def test_cli_database_actions_use_cli_request_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _context()
    host = _LiveLoop()
    ctx.capture.loop = asyncio.new_event_loop()  # an unrelated, non-running loop must not be selected
    seen = _install_spies(monkeypatch, ctx)
    try:
        for name in ("mysql_read", "postgresql_read", "database_advisor_scan"):
            call_tool(_call(ctx, host.loop), name, {}, via="cli")
        assert seen["mysql_read"] == [host.loop]
        assert seen["postgresql"] == [host.loop]
        assert seen["advisor"] == [host.loop]
    finally:
        host.close()
