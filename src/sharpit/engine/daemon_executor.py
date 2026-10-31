"""Small fixed-size executor whose workers cannot hold interpreter shutdown open."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Executor, Future
from queue import Queue
from threading import Thread
from typing import Any, cast

_Work = tuple[Future[Any], Any, tuple[Any, ...], dict[str, Any]]


class DaemonExecutor(Executor):
    def __init__(self, max_workers: int, thread_name_prefix: str) -> None:
        self._work: Queue[_Work] = Queue()
        for index in range(max_workers):
            Thread(
                target=self._worker,
                name=f"{thread_name_prefix}_{index}",
                daemon=True,
            ).start()

    def submit[T](self, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> Future[T]:
        future: Future[T] = Future()
        self._work.put(cast("_Work", (future, fn, args, kwargs)))
        return future

    def _worker(self) -> None:
        while True:
            future, fn, args, kwargs = self._work.get()
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(fn(*args, **kwargs))
                except BaseException as exc:
                    future.set_exception(exc)
