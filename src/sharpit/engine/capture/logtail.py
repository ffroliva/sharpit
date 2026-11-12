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
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from functools import lru_cache
from typing import Any, cast

from sharpit.engine import otel
from sharpit.engine.capture.correlation import INTERNAL, REQUEST
from sharpit.engine.capture.exceptions import class_name
from sharpit.engine.capture.journal import REENTRANT, JournalSink
from sharpit.engine.capture.streams import LineStream
from sharpit.engine.masking import Masker
from sharpit.engine.sqltext import Dialect, error_text, is_database_exception, log_statement

LINE_KEYS = ("timestamp", "level", "logger", "message", "thread", "messageOmitted")  # BootUI LogLineDto, record order
MAX_MESSAGE = 4000
MAX_TEMPLATE = 500  # LogPayload.MAX_TEMPLATE_LENGTH
TEMPLATE_MARGIN = 4_096  # masked past the cut, as the SQL recorder does: a secret across the cut is read whole
TEMPLATE_CACHE = 256  # masked templates kept (a call site's template, not an f-string's text)
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

    # Readers take no lock: a collection inside one runs a finalizer that logs into ``append`` on the same thread.
    # shortcut: ``tuple(deque)`` is atomic only under the GIL, where GC runs between bytecodes; a free-threaded build
    # needs a retry on the deque's RuntimeError.
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

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()
            self._bytes = 0
        self.stream.signal()

    def recent(self) -> list[dict[str, Any]]:
        """Oldest first (BootUI ``recent()``)."""
        return [line for _, line, _ in tuple(self._lines)]

    def after(self, seq: int | None) -> list[tuple[int, dict[str, Any]]]:
        return [(s, line) for s, line, _ in tuple(self._lines) if seq is None or s > seq]

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
    return type(msg) is str and msg.startswith("[") and msg.endswith("%r")


def _own(name: str) -> bool:
    return name == "sharpit" or name.startswith("sharpit.")


def _is_classified_exc(value: object) -> bool:
    return issubclass(type(value), BaseException) and is_database_exception(cast(BaseException, value))


def _exception_class(record: logging.LogRecord) -> str | None:
    info = record.exc_info
    if not isinstance(info, tuple):
        return None
    cls = type(info[1]) if isinstance(info[1], BaseException) else info[0]
    return class_name(cls) if isinstance(cls, type) else None


def _substitute_arg(value: object, masker: Masker, dialect: Dialect) -> object:
    if not _is_classified_exc(value):
        return value
    exc = cast(BaseException, value)
    return error_text(masker, exc, dialect) or type(exc).__name__


def _first_classified(values: Iterable[object]) -> BaseException | None:
    return next((cast(BaseException, v) for v in values if _is_classified_exc(v)), None)


def _format_classified(msg: object, substituted: object, fallback: BaseException) -> str:
    try:
        return msg % substituted if type(msg) is str else type(fallback).__name__
    except Exception:  # noqa: BLE001 - a bad format string falls back to the classified exception's class name
        return type(fallback).__name__


def _substitute_mapping(mapping: Mapping[object, object], masker: Masker, dialect: Dialect) -> dict[object, object]:
    return {k: _substitute_arg(v, masker, dialect) for k, v in mapping.items()}


def _substitute_tuple(seq: tuple[object, ...], masker: Masker, dialect: Dialect) -> tuple[object, ...]:
    return tuple(_substitute_arg(v, masker, dialect) for v in seq)


def _classified_args_message(record: logging.LogRecord, masker: Masker, dialect: Dialect) -> str | None:
    args = record.args
    if issubclass(type(args), Mapping):
        mapping = cast(Mapping[object, object], args)
        first = _first_classified(mapping.values())
        return _format_classified(record.msg, _substitute_mapping(mapping, masker, dialect), first) if first else None
    if type(args) is tuple:
        first = _first_classified(args)
        return _format_classified(record.msg, _substitute_tuple(args, masker, dialect), first) if first else None
    return None


def _record_message(record: logging.LogRecord, masker: Masker, dialect: Dialect) -> str:
    if _is_classified_exc(record.msg):
        exc = cast(BaseException, record.msg)
        return error_text(masker, exc, dialect) or type(exc).__name__
    formatted = _classified_args_message(record, masker, dialect)
    if formatted is not None:
        return formatted
    try:
        return record.getMessage()
    except Exception:  # noqa: BLE001 - a bad format string
        return record.msg if type(record.msg) is str else type(record.msg).__name__


class SharpitLogHandler(logging.Handler):
    """Level ``NOTSET``: it sees what the app's logger levels let through and changes no level (spec §7.5)."""

    def __init__(
        self,
        masker: Masker,
        log_tail: LogTailBuffer | None,
        application: Callable[[], Dialect | None],
    ) -> None:
        super().__init__(logging.NOTSET)
        self.masker = masker
        self.log_tail = log_tail
        self.application = application
        self.on_exc_info: Callable[[logging.LogRecord], None] | None = None  # Exceptions (Task 4)
        self.journal: JournalSink | None = None  # set by the wiring: the runtime journal, when it is on
        self.context_id: str | None = None  # the installed context a request's id must belong to to be offered
        self._local = threading.local()
        self._failed = False
        self.template_cache = lru_cache(maxsize=TEMPLATE_CACHE)(self._cached_template)

    def handleError(self, record: logging.LogRecord) -> None:
        """A bad record never prints a traceback from sharpit."""

    def emit(self, record: logging.LogRecord) -> None:
        local = self._local
        if getattr(local, "busy", False):  # a record raised while this thread is already in emit()
            if getattr(local, "offering", False) and not _own(record.name):
                self._offer_journal(record)  # raised while this thread builds or offers an event: counted, not built
            return
        local.busy = True
        try:
            self._forward_to_last_resort(record)
            if _own(record.name):
                return
            self._offer_journal(record)
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
        """``LogLineDto``, or ``None`` for a SQLAlchemy line carrying values while parameter capture is off."""
        engine_log = record.name.startswith("sqlalchemy.engine")
        # SQLAlchemy logs a statement with no args; bind values, column names and fetched rows ("Row %r") come as args,
        # and a row's repr is no statement: read as one on SQLite its escaped quote closes early and a value shows
        if engine_log and not self.masker.capture_parameters and (_is_parameter_line(record) or record.args):
            return None
        dialect = self._dialect()
        message = _record_message(record, self.masker, dialect)
        masked = self._masked(engine_log, message, dialect)
        if masked is not None and len(masked) > MAX_MESSAGE:
            masked = masked[: MAX_MESSAGE - 1] + "…"
        return {
            "timestamp": int(record.created * 1000),
            "level": record.levelname,
            "logger": record.name,
            "message": masked,
            "thread": record.threadName,
            "messageOmitted": masked is None,  # METADATA_ONLY withheld it: distinguishable from an empty message
        }

    def _dialect(self) -> Dialect:
        family = self.application()
        return Dialect.UNSUPPORTED if family is None else family

    def _masked(self, engine_log: bool, message: str, dialect: Dialect, limit: int = 4 * MAX_MESSAGE) -> str | None:
        # mask before the cut so a cut cannot hide a secret; the generous pre-cut bounds the regex work
        shown = message[:limit]
        # capture on shows a known dialect's raw text, but never one sharpit cannot read (owner, item 7)
        statement = engine_log and (not self.masker.capture_parameters or dialect is Dialect.UNSUPPORTED)
        return log_statement(self.masker, shown, dialect) if statement else error_text(self.masker, shown, dialect)

    def _offer_journal(self, record: logging.LogRecord) -> None:
        """BootUI ``RuntimeJournalLogAppender.append``: a WARN-or-above record becomes one ``log`` event. Built here,
        inside the guard and only when the journal accepts ``log``, so a failing build or offer never reaches the
        host's call. A record raised while this thread already builds or offers one is counted, never built."""
        journal = self.journal
        if journal is None or record.levelno < logging.WARNING or INTERNAL.get():
            return
        local = self._local
        if getattr(local, "offering", False):
            journal.count_dropped(REENTRANT)
        elif not journal.accepts("log"):
            journal.count_dropped("log")  # no masking, no event: the journal would refuse it
        else:
            local.offering = True
            try:
                with contextlib.suppress(Exception):  # publishing never disturbs the application's logging
                    event = self._journal_event(record)
                    # the event is flat scalars it never touches again: no deep copy
                    offer = getattr(journal, "offer_flat", journal.offer)
                    offer(event)
            finally:
                local.offering = False

    def _journal_event(self, record: logging.LogRecord) -> dict[str, str | int | bool | None]:
        """BootUI's ``log`` event (``LogPayload`` and its envelope): the unformatted ``msg`` (a template, never
        ``getMessage()`` or an argument; an object gives its class name), masked, cut at ``MAX_TEMPLATE``. An
        f-string or a concatenated ``str(exc)`` IS ``msg``: shown at MASKED (masked) and FULL,
        withheld at METADATA_ONLY."""
        msg = record.msg
        text = msg if type(msg) is str else type(msg).__name__
        engine_log, dialect, masker = record.name.startswith("sqlalchemy.engine"), self._dialect(), self.masker
        if record.args:  # a call site's template, not an f-string's text: the same masked result every time
            # keyed on the head masking reads, never the whole text: a megabyte template is not kept alive
            template = self.template_cache(
                text[: MAX_TEMPLATE + TEMPLATE_MARGIN],
                engine_log,
                dialect,
                (masker.identity_key, masker.capture_parameters),
            )
        else:
            template = self._template(text, engine_log, dialect)
        request = REQUEST.get()
        owned = request is not None and request.context_id == self.context_id  # another install's request is not ours
        return {
            "source": "log",
            "epochMillis": int(record.created * 1000),
            "durationNanos": -1,
            "traceId": otel.current_trace_id(),
            "thread": record.threadName,
            "requestId": request.id if request is not None and owned else None,
            "failedOrSlow": record.levelno >= logging.ERROR,
            "logger": record.name,
            "level": "ERROR" if record.levelno >= logging.ERROR else "WARN",
            "template": template,
            "exceptionClass": _exception_class(record),
        }

    def _template(self, text: str, engine_log: bool, dialect: Dialect) -> str | None:
        masked = self._masked(engine_log, text, dialect, MAX_TEMPLATE + TEMPLATE_MARGIN)
        return None if masked is None else masked[:MAX_TEMPLATE]

    def _cached_template(self, text: str, engine_log: bool, dialect: Dialect, masker_state: object) -> str | None:
        del (
            masker_state
        )  # part of the cache key only: what the masker hides changes when its key or capture setting does
        return self._template(text, engine_log, dialect)

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
