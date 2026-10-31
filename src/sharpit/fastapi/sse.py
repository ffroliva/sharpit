"""Server-sent event responses (spec §10): one global slot per open stream and a short lifetime.

Each stream ends after ``stream_max_seconds`` with a ``retry: 1000`` hint; the browser's ``EventSource`` reconnects.
uvicorn sends ``lifespan.shutdown`` only after open responses drain, so the lifetime is what bounds a ``--reload``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from typing import TYPE_CHECKING

from starlette.responses import Response, StreamingResponse
from starlette.types import Receive, Scope, Send

from sharpit.engine.capture.streams import SSE_TASK, StreamSlots
from sharpit.engine.headers import security_headers
from sharpit.fastapi.http import error

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

TOO_MANY_STREAMS = "Too many concurrent sharpit streams"
Events = AsyncIterator[tuple[str, str | None, str]]  # (event name, id or None, data)


def _frame(event: str, event_id: str | None, data: str) -> bytes:
    lines = [f"event: {event}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.extend(f"data: {part}" for part in data.split("\n"))
    return ("\n".join(lines) + "\n\n").encode()


async def _frames(events: Events, max_seconds: float) -> AsyncGenerator[bytes]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_seconds
    try:
        while (remaining := deadline - loop.time()) > 0:
            try:  # the wait, not the yield, is timed: a cancel must never land in the server's send()
                event, event_id, data = await asyncio.wait_for(anext(events), remaining)
            except (TimeoutError, StopAsyncIteration):
                break
            yield _frame(event, event_id, data)
        yield b"retry: 1000\n\n"
    finally:
        aclose = getattr(events, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()


class _SseResponse(StreamingResponse):
    def __init__(self, slots: StreamSlots, events: Events, max_seconds: float) -> None:
        headers = {**dict(security_headers("api")), "X-Accel-Buffering": "no"}
        self._frames = _frames(events, max_seconds)
        super().__init__(self._frames, headers=headers, media_type="text/event-stream")
        self._slots = slots

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = SSE_TASK.set(True)
        try:
            await super().__call__(scope, receive, send)
        finally:  # a client disconnect arrives as CancelledError: the slot and the subscription are freed anyway
            SSE_TASK.reset(token)
            self._slots.release()
            with contextlib.suppress(Exception):
                await self._frames.aclose()


def sse_response(ctx: SharpitContext, events: Events) -> Response:
    """A stream holding one of the global slots, or 503 when all are taken (``events`` is then never started)."""
    slots = ctx.capture.stream_slots
    if slots is None or not slots.acquire():
        return error(503, TOO_MANY_STREAMS)
    return _SseResponse(slots, events, ctx.settings.stream_max_seconds)
