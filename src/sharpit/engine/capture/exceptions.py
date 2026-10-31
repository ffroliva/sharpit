"""Exceptions (F2, spec §7.2): exception groups by fingerprint, port of BootUI ``ExceptionStore``.

Three sources feed one store: the capture middleware (``request``), the wrapped exception handlers (``handler``) and
the log handler (``log``). One exception is recorded once per request: ``mark_seen`` stores the request id on the
exception, so a second source in the same request sees its own mark and skips it. Frames keep the file, function and
line only, never locals. Messages are masked, then cut.
"""

from __future__ import annotations

import contextlib
import hashlib
import itertools
import os
import threading
import time
import traceback
from collections import deque
from collections.abc import Generator
from typing import Any, cast

from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.frames import is_application_frame
from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.masking import Masker

MAX_MESSAGE = 2000
MAX_CAUSES = 5
STATUSES = ("OPEN", "ACKNOWLEDGED", "RESOLVED")
GROUP_KEYS = (
    "id", "exceptionClassName", "message", "count", "firstSeen", "lastSeen", "location", "applicationException",
    "lastThread", "lastRequestMethod", "lastRequestPath", "lastHandler", "lastSource", "lastTraceId", "status",
    "regressionCount", "errorContract",
)  # fmt: skip

_FALLBACK_MAX = 64
# exceptions that refuse attributes: (id, store slot) -> mark; no reference, so frames are not kept alive (spec §7.2)
_FALLBACK: dict[tuple[int, str], str] = {}
_FALLBACK_LOCK = threading.Lock()
# set while this thread holds a store or fallback lock: a record from a finalizer then is dropped, not deadlocked
_BUSY = threading.local()
_TOKENS = itertools.count()
_SLOTS = itertools.count()


@contextlib.contextmanager
def _guarded(lock: threading.Lock) -> Generator[None]:
    prior = getattr(_BUSY, "on", False)
    _BUSY.on = True
    try:
        with lock:
            yield
    finally:
        _BUSY.on = prior


def _mark(exc: BaseException, slot: str) -> str | None:
    mark = getattr(exc, f"__sharpit_seen{slot}__", None)
    if isinstance(mark, str):
        return mark
    return _FALLBACK.get((id(exc), slot))


def _set_mark(exc: BaseException, slot: str, mark: str) -> None:
    try:
        setattr(exc, f"__sharpit_seen{slot}__", mark)
    except (AttributeError, TypeError):
        with _guarded(_FALLBACK_LOCK):
            _FALLBACK.pop((id(exc), slot), None)
            _FALLBACK[(id(exc), slot)] = mark
            while len(_FALLBACK) > _FALLBACK_MAX:
                del _FALLBACK[next(iter(_FALLBACK))]


def mark_seen(exc: BaseException, request_id: str | None, slot: str = "") -> bool:
    """True the first time ``exc`` is seen in this request by the store owning ``slot``. Outside a request, an
    exception already marked is the server's own log of one that escaped a request (uvicorn's "Exception in ASGI
    application"): not new."""
    prior = _mark(exc, slot)
    if request_id is None:
        if prior is not None:
            return False
        _set_mark(exc, slot, f"~{next(_TOKENS)}")
        return True
    if prior == request_id:
        return False
    _set_mark(exc, slot, request_id)
    return True


def unknown_group(gid: str) -> str:
    return f"Unknown exception group '{gid}'"


def _class_name(exc: BaseException) -> str:
    cls = type(exc)
    return cls.__qualname__ if cls.__module__ == "builtins" else f"{cls.__module__}.{cls.__qualname__}"


def _frames(exc: BaseException, limit: int | None = None) -> list[dict[str, Any]]:
    """Innermost first, capped to the innermost ``limit``; names and lines only."""
    walked = list(traceback.walk_tb(exc.__traceback__))
    walked.reverse()
    return [
        {
            "declaringClass": frame.f_globals.get("__name__", "?"),
            "methodName": frame.f_code.co_qualname,
            "fileName": os.path.basename(frame.f_code.co_filename),
            "lineNumber": line,
            "applicationFrame": is_application_frame(frame.f_code.co_filename),
        }
        for frame, line in walked[:limit]
    ]


def _chosen(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    """BootUI ``location``: the first application frame, else the innermost frame."""
    return next((f for f in frames if f["applicationFrame"]), frames[0] if frames else None)


def fingerprint(exc: BaseException, frames: list[dict[str, Any]] | None = None) -> str:
    """The class and the place it came from (``frames``: the uncapped walk); equal fingerprints share a group."""
    frame = _chosen(_frames(exc) if frames is None else frames)
    name = _class_name(exc)
    return name if frame is None else f"{name}\n{frame['declaringClass']}:{frame['methodName']}:{frame['lineNumber']}"


def _leaves(exc: BaseException) -> list[BaseException]:
    """The leaf exceptions of a group, depth first; any other exception is its own leaf."""
    if not isinstance(exc, BaseExceptionGroup):
        return [exc]
    members = cast("tuple[BaseException, ...]", exc.exceptions)  # pyright: ignore[reportUnknownMemberType]
    return [leaf for member in members for leaf in _leaves(member)]


def _causes(exc: BaseException, extra: list[BaseException]) -> list[BaseException]:
    """``__cause__``, else an unsuppressed ``__context__``; cycle-safe, then the other group leaves, at most five."""
    seen = {id(exc)}
    found: list[BaseException] = []
    current = exc
    while len(found) < MAX_CAUSES:
        following = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
        if following is None or id(following) in seen:
            break
        seen.add(id(following))
        found.append(following)
        current = following
    return (found + [e for e in extra if id(e) not in seen])[:MAX_CAUSES]


def _common(frames: list[dict[str, Any]], enclosing: list[dict[str, Any]]) -> int:
    """Frames a cause shares with the enclosing trace, counted from the outermost end (Java's ``... n more``)."""
    common = 0
    for mine, theirs in zip(reversed(frames), reversed(enclosing), strict=False):  # unequal lengths are normal
        if mine != theirs:
            break
        common += 1
    return common


class _Group:
    def __init__(self, gid: str, class_name: str, now_ms: int) -> None:
        self.id = gid
        self.class_name = class_name
        self.first_seen = now_ms
        self.last_seen = now_ms
        self.order = 0  # ns-free ordering: a counter, so eviction never ties on a coarse clock
        self.message: str | None = None
        self.location: str | None = None
        self.application = False
        self.frames: list[dict[str, Any]] = []
        self.causes: list[dict[str, Any]] = []
        self.occurrences: deque[dict[str, Any]] = deque()
        self.count = 0
        self.status = "OPEN"
        self.regressions = 0

    def summary(self) -> dict[str, Any]:
        last = self.occurrences[0] if self.occurrences else {}
        return {
            "id": self.id,
            "exceptionClassName": self.class_name,
            "message": self.message,
            "count": self.count,
            "firstSeen": self.first_seen,
            "lastSeen": self.last_seen,
            "location": self.location,
            "applicationException": self.application,
            "lastThread": last.get("thread"),
            "lastRequestMethod": last.get("requestMethod"),
            "lastRequestPath": last.get("requestPath"),
            "lastHandler": last.get("handler"),
            "lastSource": last.get("source"),
            "lastTraceId": last.get("traceId"),
            "status": self.status,
            "regressionCount": self.regressions,
            "errorContract": None,  # BootUI's Problem Details check is not ported
        }


class ExceptionStore:
    """Bounded groups (oldest ``lastSeen`` evicted) with bounded occurrences each; thread-safe."""

    def __init__(self, max_groups: int, max_occurrences: int, max_frames: int, masker: Masker) -> None:
        self.max_groups = max_groups
        self.max_occurrences = max_occurrences
        self.max_frames = max_frames
        self.masker = masker
        self.unavailable_reason: str | None = None  # set by the wiring when request capture could not be added
        self.changes = ChangeStream()
        self._groups: dict[str, _Group] = {}
        self._lock = threading.Lock()
        self._order = itertools.count(1)
        self._slot = f"_{next(_SLOTS)}"  # marks are per store: two installed apps each record an exception once

    def _message(self, text: str | None) -> str | None:
        masked = self.masker.mask_text(text[: 4 * MAX_MESSAGE] if text else None)
        if masked is not None and len(masked) > MAX_MESSAGE:
            masked = masked[: MAX_MESSAGE - 1] + "…"
        return masked

    def _text(self, exc: BaseException) -> str | None:
        try:
            return self._message(str(exc) or None)
        except Exception:  # noqa: BLE001 - a broken __str__ leaves the message out
            return None

    def record(
        self,
        exc: BaseException,
        source: str,
        request: RequestInfo | None,
        thread: str | None,
        message_override: str | None = None,
    ) -> None:
        if not isinstance(exc, Exception) or getattr(_BUSY, "on", False):  # CancelledError, KeyboardInterrupt
            return
        if not mark_seen(exc, request.id if request is not None else None, self._slot):
            return
        self._record(exc, source, request, thread, message_override)
        self._signal()

    def _record(
        self,
        exc: BaseException,
        source: str,
        request: RequestInfo | None,
        thread: str | None,
        message_override: str | None,
    ) -> None:
        leaves = _leaves(exc)
        exc, extra = (leaves[0], leaves[1:]) if leaves else (exc, [])
        walked = _frames(exc)  # one uncapped walk: fingerprint, location and applicationException agree
        frames = walked[: self.max_frames]
        causes: list[dict[str, Any]] = []
        for cause in _causes(exc, extra):
            cause_frames = _frames(cause, self.max_frames)
            causes.append(
                {
                    "exceptionClassName": _class_name(cause),
                    "message": self._text(cause),
                    "frames": cause_frames,
                    "commonFrames": _common(cause_frames, frames),
                }
            )
        message = self._text(exc)
        if message is None and message_override:
            message = self._message(message_override)
        key = fingerprint(exc, walked)
        chosen = _chosen(walked)
        location = None
        if chosen is not None:
            location = f"{chosen['declaringClass']}.{chosen['methodName']}({chosen['fileName']}:{chosen['lineNumber']})"
        now_ms = time.time_ns() // 1_000_000
        occurrence = {
            "timestamp": now_ms,
            "thread": thread,
            "requestMethod": request.method if request else None,
            "requestPath": request.path if request else None,
            "handler": request.endpoint if request else None,
            "source": source,
            "traceId": request.id if request else None,
        }
        gid = hashlib.sha256(key.encode()).hexdigest()[:16]
        with _guarded(self._lock):
            group = self._groups.get(gid)
            if group is None:
                group = self._groups[gid] = _Group(gid, _class_name(exc), now_ms)
            elif group.status == "RESOLVED":  # a regression: reopen; ACKNOWLEDGED stays as it is
                group.status = "OPEN"
                group.regressions += 1
            group.message, group.frames, group.causes = message, frames, causes
            group.location, group.application = location, chosen is not None and chosen["applicationFrame"]
            group.last_seen, group.order = now_ms, next(self._order)
            group.count += 1
            group.occurrences.appendleft(occurrence)
            while len(group.occurrences) > self.max_occurrences:
                group.occurrences.pop()
            if len(self._groups) > self.max_groups:
                del self._groups[min(self._groups.values(), key=lambda g: g.order).id]

    def report(self) -> dict[str, Any]:
        with _guarded(self._lock):
            groups = sorted(self._groups.values(), key=lambda g: g.order, reverse=True)
            summaries = [g.summary() for g in groups]
            total = sum(g.count for g in groups)
        return {
            "available": self.unavailable_reason is None,
            "unavailableReason": self.unavailable_reason,
            "maxGroups": self.max_groups,
            "totalExceptions": total,
            "groups": summaries,
        }

    def detail(self, gid: str) -> dict[str, Any] | None:
        with _guarded(self._lock):
            group = self._groups.get(gid)
            if group is None:
                return None
            return {
                "group": group.summary(),
                "frames": list(group.frames),
                "causes": list(group.causes),
                "occurrences": list(group.occurrences),
            }

    def set_status(self, gid: str, value: str | None) -> dict[str, Any] | None:
        """BootUI ``parseStatus`` (case-insensitive; a bad value raises before the group is looked up)."""
        status = (value or "").strip().upper()
        if status not in STATUSES:
            shown = "null" if value is None else value
            raise ValueError(f"Invalid status '{shown}'; expected one of OPEN, ACKNOWLEDGED, RESOLVED")
        with _guarded(self._lock):
            group = self._groups.get(gid)
            if group is None:
                return None
            group.status = status
            updated = group.summary()
        self._signal()
        return updated

    def clear(self) -> None:
        with _guarded(self._lock):
            self._groups.clear()
        self._signal()

    def forget_request(self, request_id: str) -> None:
        """Request end: drop the fallback marks of exceptions that refuse attributes."""
        with _guarded(_FALLBACK_LOCK):
            for key in [k for k, mark in _FALLBACK.items() if k[1] == self._slot and mark == request_id]:
                del _FALLBACK[key]

    def _signal(self) -> None:
        with contextlib.suppress(Exception):  # a bad subscriber never breaks capture
            self.changes.signal()
