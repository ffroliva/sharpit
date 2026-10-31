"""Live-stream plumbing (spec §10): coalesced change ticks, the bounded line hand-off and the global stream cap.

Framework-free; SSE framing lives in ``sharpit.fastapi.sse``. Producers call ``signal()`` from any thread: it only sets
a per-subscriber dirty flag and, on the clean -> dirty transition, schedules one callback on the subscriber's loop, so
a burst of signals costs one wake-up per subscriber. Everything after that runs on the loop, catches its own errors
and never logs: a log record here would reach Log Tail and signal again.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections import deque
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

SSE_TASK: ContextVar[bool] = ContextVar("sharpit_sse_task", default=False)  # set by sse_response; Threads skips it
TICK_SECONDS = 0.25  # at most 4 ticks per second per subscriber
LINE_QUEUE = 1000  # per-subscriber line queue; a client that falls behind it is disconnected
MAX_STREAMS = 20  # BootUI's log-tail limit, applied to every sharpit stream together

LineSource = Callable[[int | None], list[tuple[int, Any]]]  # lines after a sequence number (None: all), oldest first


class StreamSlots:
    """The global count of open streams, shared by every panel."""

    def __init__(self, limit: int = MAX_STREAMS) -> None:
        self.limit = limit
        self.count = 0
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            if self.count >= self.limit:
                return False
            self.count += 1
            return True

    def release(self) -> None:
        with self._lock:
            self.count = max(0, self.count - 1)


class _Ticker:
    """One subscriber's dirty flag and ≤ 4/s tick timer on its loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop, detach: Callable[[_Ticker], None]) -> None:
        self._loop = loop
        self._detach = detach
        self._dirty = False
        self._last = float("-inf")
        self._ready = asyncio.Event()
        self.closed = False

    def _signal(self) -> bool:
        """Producer side, any thread; ``False`` when the loop is closed and the subscriber must be dropped."""
        if self._dirty:
            return True
        self._dirty = True
        try:
            self._loop.call_soon_threadsafe(self._wake)
        except RuntimeError:  # the subscriber's loop has ended
            return False
        return True

    def _wake(self) -> None:
        try:
            delay = self._last + TICK_SECONDS - self._loop.time()
            if delay > 0:
                self._loop.call_later(delay, self._tick)
            else:
                self._tick()
        except Exception:  # noqa: BLE001 - never log here (§10); the next signal tries again
            self._dirty = False

    def _tick(self) -> None:
        self._dirty = False  # first: a signal from now on schedules the next tick
        self._last = self._loop.time()
        with contextlib.suppress(Exception):
            self._deliver()

    def _deliver(self) -> None:
        self._ready.set()

    def close(self) -> None:
        """Unsubscribe; a pending ``__anext__`` ends. Call on the subscriber's loop."""
        if not self.closed:
            self.closed = True
            self._detach(self)
            self._ready.set()


class Subscription(_Ticker):
    """Yields ``None`` once per coalesced tick until closed."""

    def __aiter__(self) -> Subscription:
        return self

    async def __anext__(self) -> None:
        if not self.closed:
            await self._ready.wait()
            self._ready.clear()
        if self.closed:
            raise StopAsyncIteration


class LineSubscription(_Ticker):
    """Yields ``(seq, line)``: each tick drains the lines after ``cursor`` from the source into a bounded queue."""

    def __init__(
        self, loop: asyncio.AbstractEventLoop, detach: Callable[[_Ticker], None], source: LineSource, after: int | None
    ) -> None:
        super().__init__(loop, detach)
        self._source = source
        self.cursor = after
        self._queue: deque[tuple[int, Any]] = deque()
        self.overflowed = False

    @property
    def queued(self) -> int:
        return len(self._queue)

    def _deliver(self) -> None:
        for seq, line in self._source(self.cursor):
            if len(self._queue) >= LINE_QUEUE:  # fell behind: disconnect, the client resumes from its last id
                self.overflowed = True
                self._queue.clear()
                self.close()
                return
            self._queue.append((seq, line))
            self.cursor = seq
        self._ready.set()

    def __aiter__(self) -> LineSubscription:
        return self

    async def __anext__(self) -> tuple[int, Any]:
        while True:
            if self.overflowed:
                raise StopAsyncIteration
            if self._queue:
                return self._queue.popleft()
            if self.closed:
                raise StopAsyncIteration
            self._ready.clear()
            await self._ready.wait()


class _Hub:
    def __init__(self) -> None:
        self._subscribers: list[_Ticker] = []
        self._lock = threading.RLock()  # RLock: a signal raised while signalling (a debug log) must not deadlock

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def signal(self) -> None:
        if not self._subscribers:  # the common case: nobody is watching
            return
        with self._lock:
            self._subscribers = [s for s in self._subscribers if s._signal()]  # pyright: ignore[reportPrivateUsage]

    def _add(self, subscriber: _Ticker) -> None:
        with self._lock:
            self._subscribers = [*self._subscribers, subscriber]

    def _remove(self, subscriber: _Ticker) -> None:
        with self._lock:
            self._subscribers = [s for s in self._subscribers if s is not subscriber]


class ChangeStream(_Hub):
    """Coalesced ``update`` ticks for a panel whose data changed (activity, exceptions, SQL trace)."""

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> Subscription:
        subscriber = Subscription(loop, self._remove)
        self._add(subscriber)
        return subscriber


class LineStream(_Hub):
    """Lines read from ``source`` by sequence number; a new subscriber first replays what is after ``after``."""

    def __init__(self, source: LineSource) -> None:
        super().__init__()
        self._source = source

    def subscribe(self, loop: asyncio.AbstractEventLoop, after: int | None) -> LineSubscription:
        subscriber = LineSubscription(loop, self._remove, self._source, after)
        self._add(subscriber)
        if not subscriber._signal():  # pyright: ignore[reportPrivateUsage]  # the first tick is the replay
            self._remove(subscriber)
        return subscriber
