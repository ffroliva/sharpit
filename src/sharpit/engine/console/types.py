from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from sharpit.engine.capture.streams import StreamSlots
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import HostLoopProvider

RawHeaders = tuple[tuple[bytes, bytes], ...]
BodyReader = Callable[[int], bytes | None]
ResponseHeaders = tuple[tuple[str, str], ...]
Events = AsyncIterator[tuple[str, str | None, str]]


@dataclass(frozen=True, slots=True)
class ConsoleRequest:
    method: str
    path: str
    root_path: str
    raw_query: bytes
    raw_headers: RawHeaders
    read_body: BodyReader
    scheme: str
    peer_addr: str | None
    server: tuple[str, int | None] | None
    is_probe: bool


@dataclass(frozen=True, slots=True)
class ConsoleFile:
    path: Path


@dataclass(slots=True)
class ConsoleStream:
    events: Events
    slots: StreamSlots
    max_seconds: float
    on_close: Callable[[], None] | None = None
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.slots.release()
        if self.on_close is not None:
            self.on_close()


@dataclass(frozen=True, slots=True)
class ConsoleResponse:
    status: int
    headers: ResponseHeaders
    body: bytes | None = None
    file: ConsoleFile | None = None
    stream: ConsoleStream | None = None


RouteKind = Literal["read", "action"]
ResponseClass = Literal["api", "shell", "asset"]
AuditChannel = Literal["console", "mcp", "cli"]


@dataclass(frozen=True, slots=True)
class ActionAuditEvent:
    action_id: str
    channel: AuditChannel
    panel: str | None
    timestamp_ms: int
    status: int
    ok: bool


class ActionAuditHook(Protocol):
    def on_action(self, event: ActionAuditEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class ConsoleCall:
    ctx: SharpitContext
    request: ConsoleRequest
    headers: Mapping[str, str]
    path_params: Mapping[str, str]
    query_params: Mapping[str, str]
    trusted: bool
    host_loop_provider: HostLoopProvider | None = None

    def page(self) -> tuple[int | None, int | None]:
        from sharpit.engine.paging import parse_int_param

        return parse_int_param(self.query_params.get("offset"), "offset"), parse_int_param(
            self.query_params.get("limit"), "limit"
        )


RouteHandler = Callable[[ConsoleCall], ConsoleResponse | Awaitable[ConsoleResponse]]


@dataclass(frozen=True, slots=True)
class RouteSpec:
    id: str
    method: Literal["GET", "POST", "DELETE"]
    template: str
    handler: RouteHandler
    panel: str | None
    kind: RouteKind
    response_class: ResponseClass = "api"
    on_loop: bool = False
    stream: bool = False


def frame_sse(event: str, event_id: str | None, data: str) -> bytes:
    lines = [f"event: {event}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.extend(f"data: {line}" for line in data.split("\n"))
    return ("\n".join(lines) + "\n\n").encode()


async def stream_frames(events: Events, max_seconds: float) -> AsyncGenerator[bytes]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_seconds
    try:
        while (remaining := deadline - loop.time()) > 0:
            try:
                event, event_id, data = await asyncio.wait_for(anext(events), remaining)
            except (TimeoutError, StopAsyncIteration):
                break
            yield frame_sse(event, event_id, data)
        yield b"retry: 1000\n\n"
    finally:
        close = getattr(events, "aclose", None)
        if close is not None:
            with contextlib.suppress(Exception):
                await close()
