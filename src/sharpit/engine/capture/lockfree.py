"""A ``logging.Handler`` that holds no handler lock.

``Handler.handle`` holds the handler's RLock across ``emit``. A sharpit handler's ``emit`` waits on another lock (the
journal's, the test sink's) while a thread holding that lock can log from a GC finalizer and wait on the handler lock:
a cycle. Like ``logging.NullHandler``, this base has no lock; a subclass's ``emit`` keeps its state in thread-locals
and in structures that take their own locks.
"""

from __future__ import annotations

import logging
from typing import cast


class LockFreeHandler(logging.Handler):
    def createLock(self) -> None:  # noqa: N802 - the stdlib hook name
        self.lock = None  # ``acquire``/``release`` (used by ``logging.shutdown``) are no-ops without a lock

    def handle(self, record: logging.LogRecord) -> bool:
        # 3.13+ does ``with self.lock`` in the stdlib ``handle``, so it is overridden. Returns what the filters
        # returned, as the stdlib does (the record on 3.12+, a truthy value before).
        result = self.filter(record)
        if result:
            self.emit(result if isinstance(result, logging.LogRecord) else record)
        return cast(bool, result)  # typeshed says bool; the stdlib returns the record on 3.12+
