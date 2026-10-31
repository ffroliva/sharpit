"""Log Tail (F5, spec §7.5): the bounded line buffer and the ``logging.Handler`` that feeds it.

Port of BootUI ``LogTailBuffer``. Lines are built and masked in the handler, so the buffer never holds a raw secret.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import threading
from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import Any

from sharpit.engine.capture.streams import LineStream
from sharpit.engine.masking import Masker

LINE_KEYS = ("timestamp", "level", "logger", "message", "thread")  # BootUI LogLineDto, record order
MAX_MESSAGE = 4000
_FAILED = "sharpit log capture failed (%s); log capture continues"


class LogTailBuffer:
    """Bounded by line count and by the UTF-8 bytes of message + thread; oldest first out, at least one line kept."""

    def __init__(self, max_lines: int, max_bytes: int) -> None:
        self._max_lines = max(1, max_lines)
        self._max_bytes = max_bytes
        self._lines: deque[tuple[int, dict[str, Any], int]] = deque()
        self._bytes = 0
        self._seq = 0
        self._lock = threading.Lock()
        self.boot_nonce = secrets.token_hex(8)  # per process start: an SSE id from another process replays all
        self.stream = LineStream(self.after)

    def append(self, line: dict[str, Any]) -> int:
        size = len((line.get("message") or "").encode()) + len((line.get("thread") or "").encode())
        with self._lock:
            self._seq += 1
            seq = self._seq
            self._lines.append((seq, line, size))
            self._bytes += size
            while len(self._lines) > self._max_lines or (self._bytes > self._max_bytes and len(self._lines) > 1):
                self._bytes -= self._lines.popleft()[2]
        self.stream.signal()
        return seq

    def recent(self) -> list[dict[str, Any]]:
        """Oldest first (BootUI ``recent()``)."""
        with self._lock:
            return [line for _, line, _ in self._lines]

    def after(self, seq: int | None) -> list[tuple[int, dict[str, Any]]]:
        with self._lock:
            return [(s, line) for s, line, _ in self._lines if seq is None or s > seq]

    def resume_point(self, last_event_id: str | None) -> int | None:
        """The sequence number in ``<bootNonce>-<seq>``; ``None`` (replay everything) for another process's id."""
        nonce, _, seq = (last_event_id or "").rpartition("-")
        return int(seq) if nonce == self.boot_nonce and seq.isascii() and seq.isdecimal() else None


async def log_events(buffer: LogTailBuffer, after: int | None) -> AsyncIterator[tuple[str, str | None, str]]:
    """SSE events ``(event, id, data)`` for the log stream: the replay after ``after``, then live lines."""
    subscription = buffer.stream.subscribe(asyncio.get_running_loop(), after)
    try:
        async for seq, line in subscription:
            yield "log", f"{buffer.boot_nonce}-{seq}", json.dumps(line, ensure_ascii=False, separators=(",", ":"))
    finally:
        subscription.close()


def _is_parameter_line(record: logging.LogRecord) -> bool:
    """SQLAlchemy's ``echo=True`` bind-value lines: ``"[%s] %r"`` and ``"[raw sql] %r"``."""
    msg = record.msg
    return isinstance(msg, str) and msg.startswith("[") and msg.endswith("%r")


def _own(name: str) -> bool:
    return name == "sharpit" or name.startswith("sharpit.")


class SharpitLogHandler(logging.Handler):
    """Level ``NOTSET``: it sees what the app's logger levels let through and changes no level (spec §7.5)."""

    def __init__(self, masker: Masker, log_tail: LogTailBuffer | None) -> None:
        super().__init__(logging.NOTSET)
        self.masker = masker
        self.log_tail = log_tail
        self.on_exc_info: Callable[[logging.LogRecord], None] | None = None  # Exceptions (Task 4)
        self._local = threading.local()
        self._failed = False

    def handleError(self, record: logging.LogRecord) -> None:
        """A bad record never prints a traceback from sharpit."""

    def emit(self, record: logging.LogRecord) -> None:
        local = self._local
        if getattr(local, "busy", False):  # a record raised while this thread is already in emit()
            return
        local.busy = True
        try:
            self._forward_to_last_resort(record)
            if _own(record.name):
                return
            if record.exc_info and self.on_exc_info is not None:
                self.on_exc_info(record)
            if self.log_tail is not None:
                line = self.line(record)
                if line is not None:
                    self.log_tail.append(line)
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)
        finally:
            local.busy = False

    def line(self, record: logging.LogRecord) -> dict[str, Any] | None:
        """``LogLineDto``, or ``None`` for a SQLAlchemy bind-value line while parameter capture is off."""
        engine_log = record.name.startswith("sqlalchemy.engine")
        if engine_log and not self.masker.capture_parameters and _is_parameter_line(record):
            return None
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a bad format string
            message = str(record.msg)
        # mask before the cut so a cut cannot hide a secret; the generous pre-cut bounds the regex work
        masked = self.masker.mask_text(message[: 4 * MAX_MESSAGE])
        if masked is not None and len(masked) > MAX_MESSAGE:
            masked = masked[: MAX_MESSAGE - 1] + "…"
        return {
            "timestamp": int(record.created * 1000),
            "level": record.levelname,
            "logger": record.name,
            "message": masked,
            "thread": record.threadName,
        }

    def _forward_to_last_resort(self, record: logging.LogRecord) -> None:
        """With a handler on root, ``callHandlers`` no longer falls back to ``lastResort``: do it here (spec §6.1).

        Only when no other handler in the record's hierarchy exists, and only from the first sharpit handler there,
        so several installs print a record once.
        """
        last = logging.lastResort
        if last is None or record.levelno < last.level:
            return
        found = logging.root.manager.loggerDict.get(record.name)
        current: logging.Logger | None = found if isinstance(found, logging.Logger) else logging.root
        first: logging.Handler | None = None
        while current is not None:
            for handler in current.handlers:
                if not isinstance(handler, SharpitLogHandler):
                    return  # the app handles it: no lastResort, as without sharpit
                first = first or handler
            if not current.propagate:
                break
            current = current.parent
        if first is self:
            last.handle(record)

    def _fail(self, exc: Exception) -> None:
        """One warning, straight to ``lastResort`` (no traceback, never back into this handler)."""
        if self._failed:
            return
        self._failed = True
        last = logging.lastResort
        if last is not None:
            warning = logging.makeLogRecord(
                {"name": "sharpit", "levelno": logging.WARNING, "levelname": "WARNING", "msg": _FAILED,
                 "args": (type(exc).__name__,)}
            )  # fmt: skip
            with contextlib.suppress(Exception):
                last.handle(warning)
