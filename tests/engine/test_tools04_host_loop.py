from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

import pytest

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.context import SharpitContext
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.tools import CallContext, ToolCallError, call_tool
from sharpit.engine.tools04 import database_advisor, mysql, postgresql
from sharpit.settings import load_settings

_CASES = [
    (mysql, "mysql_read", "refresh_mysql", "mysql-read", "MySQL read timed out."),
    (postgresql, "postgresql_read", "refresh_postgresql", "postgresql-read", "PostgreSQL read timed out."),
    (
        database_advisor,
        "database_advisor_scan",
        "run_scan",
        "database-advisor-scan",
        "Database advisor scan timed out.",
    ),
]


class _Introspector:
    def app_info(self):
        return None

    def routes(self):
        return []

    def providers(self):
        return []


@pytest.fixture
def ctx() -> SharpitContext:
    return SharpitContext(
        load_settings({"enabled": "ON", "mcp_enabled": "ON", "cli_enabled": True}, {}),
        ActivationStatus(True, True, "Enabled", ()),
        _Introspector(),
    )


@pytest.fixture
def host_loop(ctx: SharpitContext):
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def run() -> None:
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run)
    thread.start()
    assert ready.wait(1)
    ctx.capture.loop = loop
    try:
        yield loop
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(1)
        loop.close()


def _released_within(single: SingleFlight, operation: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        release = single.try_acquire(operation)
        if release is not None:
            release()
            return True
        time.sleep(0.01)
    return False


@pytest.mark.parametrize(("module", "tool", "refresh", "operation", "message"), _CASES)
def test_timed_out_read_is_cancelled_and_releases_its_lock(
    ctx: SharpitContext,
    host_loop: asyncio.AbstractEventLoop,
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    tool: str,
    refresh: str,
    operation: str,
    message: str,
) -> None:
    started = threading.Event()
    never = asyncio.Event()

    async def blocking(*_args: object) -> dict[str, Any]:
        release = ctx.single_flight.try_acquire(operation)
        assert release is not None
        try:
            started.set()
            await never.wait()
            return {}
        finally:
            release()

    monkeypatch.setattr(module, refresh, blocking)
    monkeypatch.setattr(module, "TOOL_WAIT_TIMEOUT", 0.02, raising=False)
    with pytest.raises(Exception) as caught:
        call_tool(CallContext(ctx, {}), tool, {}, via="cli")
    assert started.wait(1)
    assert isinstance(caught.value, ToolCallError)
    assert caught.value.status == 504
    assert str(caught.value) == message
    assert _released_within(ctx.single_flight, operation, 1.0)


def test_read_finished_at_the_deadline_returns_its_result(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = asyncio.new_event_loop()

    async def completed() -> str:
        return "done"

    class _Future:
        def done(self) -> bool:
            return True

        def result(self, timeout: float | None = None) -> str:
            if timeout:
                raise FutureTimeoutError
            return "done"

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", lambda _coro, _loop: _Future())
    try:
        from sharpit.engine.tools04 import hostloop

        assert hostloop.wait_on_host_loop(loop, completed(), 0.01, "timed out", "unavailable") == "done"
    finally:
        loop.close()


def test_loop_closed_during_submit_answers_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = asyncio.new_event_loop()

    async def pending() -> str:
        return "done"

    def close_then_submit(coro, _loop):
        loop.close()
        raise RuntimeError("loop closed")

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", close_then_submit)
    from sharpit.engine.tools04 import hostloop

    with pytest.raises(ToolCallError) as caught:
        hostloop.wait_on_host_loop(loop, pending(), 0.01, "timed out", "loop unavailable")
    assert caught.value.status == 503
    assert str(caught.value) == "loop unavailable"
