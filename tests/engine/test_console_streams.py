from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from sharpit.engine.capture.streams import StreamSlots
from sharpit.engine.console import ConsoleStream, frame_sse, stream_frames


@pytest.mark.asyncio
async def test_stream_releases_slot_on_close() -> None:
    slots = StreamSlots()
    acquired = slots.acquire()
    assert acquired is True
    stream = ConsoleStream(_events(), slots, 1)

    stream.close()

    assert slots.count == 0
    stream.close()
    assert slots.count == 0


@pytest.mark.asyncio
async def test_stream_exception_closes_events_and_releases_slot() -> None:
    slots = StreamSlots()
    acquired = slots.acquire()
    assert acquired is True
    closed = False

    async def events() -> AsyncIterator[tuple[str, str | None, str]]:
        nonlocal closed
        try:
            raise RuntimeError("stream failure")
            yield "unused", None, ""
        finally:
            closed = True

    stream = ConsoleStream(events(), slots, 1)
    frames = stream_frames(stream.events, stream.max_seconds)
    with pytest.raises(RuntimeError, match="stream failure"):
        await anext(frames)
    stream.close()

    assert closed is True
    assert slots.count == 0


async def _events() -> AsyncIterator[tuple[str, str | None, str]]:
    yield "unused", None, ""


@pytest.mark.asyncio
async def test_exhausted_stream_sends_retry_frame() -> None:
    failure = None
    frames = []
    try:
        frames = [frame async for frame in stream_frames(_events(), 1)]
    except RuntimeError as exc:
        failure = exc

    assert failure is None
    assert frames == [b"event: unused\ndata: \n\n", b"retry: 1000\n\n"]


@pytest.mark.asyncio
async def test_stream_suppresses_source_close_error_after_timeout() -> None:
    closed = False

    class Events:
        def __aiter__(self) -> Events:
            return self

        async def __anext__(self) -> tuple[str, str | None, str]:
            await asyncio.Event().wait()
            raise StopAsyncIteration

        async def aclose(self) -> None:
            nonlocal closed
            closed = True
            raise RuntimeError("source close failed")

    failure = None
    frames = []
    try:
        frames = [frame async for frame in stream_frames(Events(), 0.01)]
    except RuntimeError as exc:
        failure = exc

    assert failure is None
    assert frames == [b"retry: 1000\n\n"]
    assert closed is True


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param("a\n", b"event: update\nid: 42\ndata: a\ndata: \n\n", id="trailing-newline"),
        pytest.param("a\vb", b"event: update\nid: 42\ndata: a\vb\n\n", id="vertical-tab"),
    ],
)
def test_frame_sse_splits_data_on_line_feed_only(data: str, expected: bytes) -> None:
    assert frame_sse("update", "42", data) == expected


@pytest.mark.asyncio
async def test_steady_stream_ends_at_its_overall_deadline() -> None:
    async def steady() -> AsyncIterator[tuple[str, str | None, str]]:
        while True:
            await asyncio.sleep(0.01)
            yield "update", None, ""

    frames = []
    async for frame in stream_frames(steady(), 0.1):
        frames.append(frame)
        if len(frames) > 50:
            break

    assert frames[-1] == b"retry: 1000\n\n"


@pytest.mark.asyncio
async def test_stream_timeout_counts_time_spent_on_earlier_events(monkeypatch: pytest.MonkeyPatch) -> None:
    timeouts: list[float] = []
    wait_for = asyncio.wait_for

    async def recording_wait_for(awaitable, timeout: float):
        timeouts.append(timeout)
        return await wait_for(awaitable, timeout)

    async def slow_event() -> AsyncIterator[tuple[str, str | None, str]]:
        await asyncio.sleep(0.05)
        yield "update", None, ""

    monkeypatch.setattr(asyncio, "wait_for", recording_wait_for)

    frames = [frame async for frame in stream_frames(slow_event(), 60)]

    assert frames == [b"event: update\ndata: \n\n", b"retry: 1000\n\n"]
    assert timeouts[1] < timeouts[0]


@pytest.mark.asyncio
async def test_stream_source_without_aclose_still_ends_with_retry() -> None:
    class Events:
        def __aiter__(self) -> AsyncIterator[tuple[str, str | None, str]]:
            return self

        async def __anext__(self) -> tuple[str, str | None, str]:
            raise StopAsyncIteration

    frames = [frame async for frame in stream_frames(Events(), 1)]

    assert frames == [b"retry: 1000\n\n"]


@pytest.mark.asyncio
async def test_cancellation_while_closing_the_source_propagates() -> None:
    class Events:
        def __aiter__(self) -> AsyncIterator[tuple[str, str | None, str]]:
            return self

        async def __anext__(self) -> tuple[str, str | None, str]:
            raise StopAsyncIteration

        async def aclose(self) -> None:
            raise asyncio.CancelledError

    cancelled = False
    try:
        async for _frame in stream_frames(Events(), 1):
            pass
    except asyncio.CancelledError:
        cancelled = True

    assert cancelled is True
