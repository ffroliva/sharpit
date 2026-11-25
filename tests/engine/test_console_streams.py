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
