"""Run tool coroutines on the host application's event loop."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from sharpit.engine.spi import HostLoopProvider
from sharpit.engine.tools import ToolCallError


def running_host_loop(provider: HostLoopProvider | None) -> asyncio.AbstractEventLoop | None:
    loop = provider.current_loop() if provider is not None else None
    return loop if loop is not None and loop.is_running() and not loop.is_closed() else None


def wait_on_host_loop[T](
    loop: asyncio.AbstractEventLoop,
    coro: Coroutine[Any, Any, T],
    timeout: float,
    timed_out: str,
    unavailable: str,
) -> T:
    try:
        future = asyncio.run_coroutine_threadsafe(coro, loop)
    except RuntimeError:
        coro.close()
        raise ToolCallError(unavailable, 503) from None
    try:
        return future.result(timeout)
    except FutureTimeoutError:
        if future.done():
            return future.result(0)
        future.cancel()
        raise ToolCallError(timed_out, 504) from None
