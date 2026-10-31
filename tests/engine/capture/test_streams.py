"""``ChangeStream``, ``LineStream`` and ``StreamSlots`` (spec §10).

Ported from BootUI ``LogTailSseSessionTests`` (cited per test):
``queueOverflowDisconnectsSlowSubscriberWithoutBlockingPublisher`` and
``completionAndTimeoutReleaseTheirSubscriptions``. Dropped, with reason: ``blockedEmitterDoesNotHoldPublisher...``
and ``sendFailureUnsubscribes...`` (sharpit has no sender thread: producers only set a flag, the loop sends).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

import pytest

from sharpit.engine.capture.exchanges import HttpExchangeBuffer
from sharpit.engine.capture.streams import LINE_QUEUE, ChangeStream, LineStream, StreamSlots


def _counting(loop: asyncio.AbstractEventLoop, monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    original = loop.call_soon_threadsafe

    def counted(callback: Any, *args: Any, **kw: Any) -> Any:
        calls.append(callback)
        return original(callback, *args, **kw)

    monkeypatch.setattr(loop, "call_soon_threadsafe", counted)
    return calls


def test_signal_coalesces_one_callback_per_subscriber(monkeypatch: pytest.MonkeyPatch):
    async def main() -> None:
        loop = asyncio.get_running_loop()
        calls = _counting(loop, monkeypatch)
        stream = ChangeStream()
        first, second = stream.subscribe(loop), stream.subscribe(loop)
        worker = threading.Thread(target=lambda: [stream.signal() for _ in range(100)])
        worker.start()
        worker.join()
        assert len(calls) == 2  # one pending wake-up per subscriber, however many signals
        assert await asyncio.wait_for(anext(first), 1) is None
        assert await asyncio.wait_for(anext(second), 1) is None
        first.close()
        second.close()
        assert stream.subscriber_count == 0

    asyncio.run(main())


def test_ticks_at_most_four_per_second():
    async def main() -> int:
        loop = asyncio.get_running_loop()
        stream = ChangeStream()
        sub = stream.subscribe(loop)
        stop = threading.Event()

        def produce() -> None:
            while not stop.is_set():
                stream.signal()
                time.sleep(0.005)

        worker = threading.Thread(target=produce)
        worker.start()
        ticks = 0
        deadline = loop.time() + 0.6
        try:
            while (remaining := deadline - loop.time()) > 0:
                try:
                    await asyncio.wait_for(anext(sub), remaining)
                except TimeoutError:
                    break
                ticks += 1
        finally:
            stop.set()
            worker.join()
            sub.close()
        return ticks

    ticks = asyncio.run(main())
    assert 1 <= ticks <= 3  # 0 s, 0.25 s, 0.5 s at most within 0.6 s


def test_callback_error_logs_nothing(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch):
    loop_errors: list[dict[str, Any]] = []

    async def main() -> None:
        loop = asyncio.get_running_loop()
        caplog.clear()  # the loop's own "Using proactor" debug line
        loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))
        stream = ChangeStream()
        sub = stream.subscribe(loop)

        def boom() -> None:
            raise RuntimeError("callback failed")

        monkeypatch.setattr(sub, "_deliver", boom)
        stream.signal()
        await asyncio.sleep(0.05)
        monkeypatch.undo()
        stream.signal()  # the failed tick cleared the dirty flag: the next signal still wakes the subscriber
        assert await asyncio.wait_for(anext(sub), 1) is None
        sub.close()

    with caplog.at_level(logging.DEBUG):
        asyncio.run(main())
    assert loop_errors == []
    assert caplog.records == []


def test_non_reading_subscriber_memory_flat():
    # ported: queueOverflowDisconnectsSlowSubscriberWithoutBlockingPublisher (a client that never reads)
    lines: list[tuple[int, dict[str, Any]]] = []

    def source(after: int | None) -> list[tuple[int, dict[str, Any]]]:
        return [(s, line) for s, line in lines if after is None or s > after]

    async def main() -> None:
        loop = asyncio.get_running_loop()
        stream = LineStream(source)
        sub = stream.subscribe(loop, None)
        for seq in range(1, 3 * LINE_QUEUE):
            lines.append((seq, {"message": f"m{seq}"}))
            if len(lines) > 500:  # the log buffer keeps its own cap
                del lines[0]
            stream.signal()
            if seq % 400 == 0:
                await asyncio.sleep(0.3)  # let a tick drain into the queue nobody reads
        await asyncio.sleep(0.3)
        assert sub.queued <= LINE_QUEUE
        assert sub.overflowed and stream.subscriber_count == 0  # dropped, not grown
        with pytest.raises(StopAsyncIteration):
            await anext(sub)

    started = time.perf_counter()
    asyncio.run(main())
    assert time.perf_counter() - started < 10  # the producer never waited on the subscriber
    assert len(lines) == 500


def test_line_stream_replays_then_delivers_live_without_gap():
    # ported: LogTailBufferTests.subscribeWithReplayReturnsBacklogAndDeliversLiveWithoutGap
    lines: list[tuple[int, dict[str, Any]]] = [(1, {"m": "backlog1"}), (2, {"m": "backlog2"})]

    def source(after: int | None) -> list[tuple[int, dict[str, Any]]]:
        return [(s, line) for s, line in lines if after is None or s > after]

    async def main() -> list[int]:
        loop = asyncio.get_running_loop()
        stream = LineStream(source)
        sub = stream.subscribe(loop, None)
        seen = [(await asyncio.wait_for(anext(sub), 1))[0] for _ in range(2)]
        lines.append((3, {"m": "live1"}))
        stream.signal()
        seen.append((await asyncio.wait_for(anext(sub), 1))[0])
        sub.close()
        lines.append((4, {"m": "live2"}))
        stream.signal()
        with pytest.raises(StopAsyncIteration):
            await anext(sub)
        return seen

    assert asyncio.run(main()) == [1, 2, 3]


def test_closed_loop_subscriber_dropped():
    loop = asyncio.new_event_loop()
    stream = ChangeStream()
    stream.subscribe(loop)
    loop.close()
    stream.signal()  # no exception reaches the producer
    assert stream.subscriber_count == 0


def test_completion_releases_subscription():
    # ported: completionAndTimeoutReleaseTheirSubscriptions
    async def main() -> None:
        stream = ChangeStream()
        sub = stream.subscribe(asyncio.get_running_loop())
        waiter = asyncio.ensure_future(anext(sub))
        await asyncio.sleep(0)
        sub.close()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(waiter, 1)
        assert stream.subscriber_count == 0

    asyncio.run(main())


def test_stream_slots():
    slots = StreamSlots()
    assert all(slots.acquire() for _ in range(20))
    assert not slots.acquire() and slots.count == 20
    slots.release()
    assert slots.acquire() and slots.count == 20


def test_exchange_add_signals_changes():
    async def main() -> None:
        buffer = HttpExchangeBuffer(10)
        sub = buffer.changes.subscribe(asyncio.get_running_loop())
        buffer.add({"id": "r1"})
        assert await asyncio.wait_for(anext(sub), 1) is None
        sub.close()

    asyncio.run(main())
