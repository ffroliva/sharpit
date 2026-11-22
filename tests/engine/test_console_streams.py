from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from sharpit.engine.capture.streams import StreamSlots
from sharpit.engine.console import ConsoleStream, stream_frames


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
