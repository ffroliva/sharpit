"""The files sensor (W6 lane S3): which files the application opens, deletes, moves and copies, as path patterns.

Minimisation: a row is ``{source, kind, target, origin, location, requestId, at, callSite, threadName}`` (no call site:
a stack walk per event exceeds the sensor overhead budget). The target is a pattern: relative to the working directory
(``./``), the temporary directory (``$TMPDIR``) or the home (``~``), with a secret-looking segment masked and each uuid,
long hex run and number collapsed (``report-{n}.csv``). File content and file descriptors are never read. The origin is
``unknown``: sharpit does not walk the stack on a file event (BootUI's frame summary has no cheap port). Imports (the
interpreter's own prefixes) and sharpit's own state are left out and counted in ``ignored``.
"""

from __future__ import annotations

import inspect
import os
import posixpath
import re
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from sharpit.engine.capture.correlation import REQUEST, RequestInfo
from sharpit.engine.sensors.sinks import (
    FROM_REQUEST_INPUT,
    NOT_CHECKED,
    Match,
    SinkMatcher,
    unchecked,
)
from sharpit.engine.sensors.sinks.values import _EMPTY, _REPEATED  # pyright: ignore[reportPrivateUsage]

SOURCE = "files"
_RENAME = "os.rename"
_FOLD = os.name == "nt"
_MAX_PATTERN = 200  # SideEffects.MAX_PATTERN
_ID_RUNS = re.compile(  # SideEffects.collapse: a JWT-like tail, a uuid, or any alphanumeric run
    r"(?P<token>(?<![0-9A-Za-z])eyJ[^/.]*\.[^/]*)"
    r"|(?P<uuid>(?<![0-9A-Za-z])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![0-9A-Za-z]))"
    r"|(?P<run>[0-9A-Za-z]+)"
)
_RUNS = re.compile(
    r"(?<![0-9A-Za-z])(?P<run>[0-9A-Za-z]*\d[0-9A-Za-z]*|[A-Za-z]{24,})", re.ASCII
)  # _ID_RUNS without a token or a uuid; ASCII keeps \d to [0-9]
_DIGITS = re.compile(r"\d+")
_COLLAPSIBLE = re.compile(r"\d|eyJ|[A-Za-z]{24}")  # nothing else can collapse: most paths stop here, after one scan
_SEEN = 256  # distinct paths remembered per sensor, cleared when full (BootUI's Seen cache)
_HEX_LETTERS = frozenset("abcdefABCDEF")
_WRITE_MODE = frozenset("wax+")
_WRITE_DISJOINT = _WRITE_MODE.isdisjoint
_REQUEST_GET = REQUEST.get
_MISS = ("", "")  # a cache miss; no path resolves to it
_PENDING = 64  # announced copy paths remembered, cleared when full (a copy that failed before opening leaves two)
_COPYFILE = shutil.copyfile.__code__
_COPY_DEPTH = 12  # frames from the sensor up to the copyfile that opened the file: dispatcher, sensor, a few more
_DRIVE = re.compile(r"[A-Za-z]:/")
_SYSTEM = (
    "/etc", "/usr", "/proc", "/sys", "/dev", "/bin", "/sbin", "/lib", "/var", "/boot", "/opt",
    "c:/windows", "c:/program files", "c:/programdata",
)  # fmt: skip

_WRITE_FLAGS = (
    os.O_WRONLY | os.O_RDWR | getattr(os, "O_APPEND", 0) | getattr(os, "O_CREAT", 0) | getattr(os, "O_TRUNC", 0)
)
_OPEN_KINDS: dict[object, str] = {
    "r": "read",
    "rb": "read",
    "rt": "read",
    "w": "write",
    "wb": "write",
    "wt": "write",
    "a": "write",
    "ab": "write",
    "x": "write",
    "xb": "write",
}


def _open_kind(mode: object, flags: object) -> str:
    if isinstance(mode, str):
        return "read" if _WRITE_DISJOINT(mode) else "write"
    return "write" if isinstance(flags, int) and (flags & _WRITE_FLAGS) else "read"


def _slashes(path: str) -> str:
    return path.replace("\\", "/")


def _fold(path: str) -> str:
    return path.casefold() if _FOLD else path


def _text(path: object) -> str | None:
    """A path argument as text, or None when it names no file (a descriptor)."""
    if not isinstance(path, (str, bytes, os.PathLike)):
        return None
    raw: str | bytes = os.fspath(path)  # pyright: ignore[reportUnknownVariableType]
    return raw if isinstance(raw, str) else raw.decode("utf-8", "replace")


def _is_absolute(path: str) -> bool:
    return path.startswith("/") or bool(_DRIVE.match(path))


def _run(match: re.Match[str]) -> str:
    """``{token}``, ``{uuid}`` or the alphanumeric run collapsed as ``SideEffects.collapse`` does."""
    run = match["run"]
    if run is None:
        return "{token}" if match["token"] else "{uuid}"
    if run.isdigit():
        return "{n}"
    digits = any(c.isdigit() for c in run)
    if digits and len(run) >= 8 and all(c.isdigit() or c in _HEX_LETTERS for c in run):
        return "{hex}"
    if (digits and len(run) >= 12) or (not digits and len(run) >= 24 and not run.islower() and not run.isupper()):
        return "{id}"
    return _DIGITS.sub("{n}", run) if digits else run


def _collapse(path: str) -> str:
    if not _COLLAPSIBLE.search(path):
        return path
    plain = "eyJ" not in path and path.count("-") < 4  # a uuid has four dashes, a token starts with eyJ
    return (_RUNS if plain else _ID_RUNS).sub(_run, path)


def _is_home_segment(segment: str, index: int, previous: str | None) -> bool:
    if segment.casefold() == "users" and index <= 4:
        return True
    return segment == "home" and (index == 1 or (index == 2 and previous in ("var", "export")))


def _user_name_end(path: str, end: int) -> int:
    """Where the user name that starts after ``end`` stops, or -1 when it is empty."""
    user_end = path.find("/", end + 1)
    user_end = len(path) if user_end < 0 else user_end
    return user_end if user_end > end + 1 else -1


def _other_home(path: str) -> int:
    """``SideEffects.otherHome``: where the user name ends in another user's home directory, else -1."""
    start, previous = 0, None
    for index, segment in enumerate(path.split("/")):
        if index > 5:
            return -1
        end = start + len(segment)
        if _is_home_segment(segment, index, previous) and end < len(path):
            return _user_name_end(path, end)
        previous, start = segment, end + 1
    return -1


def _file_row(
    kind: str, target: str, location: str, context_id: str | None, req: RequestInfo | None
) -> dict[str, object]:
    req_id = req.id if req is not None and (context_id is None or req.context_id == context_id) else None
    return {
        "source": SOURCE,
        "kind": kind,
        "target": target,
        "origin": "unknown",
        "location": location,
        "requestId": req_id,
        "at": time.time_ns() // 1_000_000,
        "callSite": None,
        # shortcut: current_thread() registers a _DummyThread (a blocking lock) for a foreign thread, when
        # a private _active lookup would avoid it; upgrade when the hook shows that lock in a profile
        "threadName": threading.current_thread().name if req_id is None else None,
    }


class FilesSensor:
    name = SOURCE
    events = ("open", "os.remove", _RENAME, "shutil.copyfile")

    def __init__(
        self,
        mask_path: Callable[[str], str] = lambda path: path,
        *,
        own: Iterable[str] = (),
        cwd: str | None = None,
        home: str | None = None,
        tmp: str | None = None,
        matcher: SinkMatcher | None = None,
        context_id: str | None = None,
    ) -> None:
        self._matcher = matcher
        if context_id is not None:
            self._context_id: str | None = context_id
        else:
            self._context_id = matcher._context_id if matcher is not None else None  # pyright: ignore[reportPrivateUsage]
        self._mask = mask_path
        self._cwd = _slashes(
            cwd if cwd is not None else os.getcwd()
        )  # shortcut: fixed at build, a chdir is not followed
        places = (  # SideEffects.pattern's order: on equal length the temporary directory wins, then the cwd
            (tmp if tmp is not None else tempfile.gettempdir(), "$TMPDIR/", "temporary-directory"),
            (self._cwd, "./", "working-directory"),
            (home if home is not None else os.path.expanduser("~"), "~/", "home"),
        )
        # (the directory and its trailing slash, folded where the file system is; lead; location), longest first
        self._places = tuple(
            sorted(
                ((_fold(_slashes(base).rstrip("/") + "/"), lead, location) for base, lead, location in places),
                key=lambda place: -len(place[0]),
            )
        )
        skipped = {sys.prefix, sys.base_prefix, sys.exec_prefix, *own}
        self._skip = tuple(_fold(_slashes(os.path.abspath(path)).rstrip("/") + "/") for path in skipped if path)
        self._system = tuple(_fold(prefix + "/") for prefix in _SYSTEM)
        self._seen: dict[str, tuple[str, str] | None] = {}  # raw path -> (pattern, location); None: left out
        self._pending: set[int] = set()  # announced copy paths remembered as hashes, cleared when full
        self.ignored = 0

    def record(self, event: str, args: tuple[Any, ...]) -> Sequence[Mapping[str, object]]:
        if event == "open":
            if len(args) < 3:
                return ()
            path, mode, flags = args[0], args[1], args[2]
            if self._pending and self._is_inner_copy_open(path):
                return ()
            kind = _OPEN_KINDS.get(mode) or _open_kind(mode, flags)
            return self._row(kind, path)
        if event in (_RENAME, "shutil.copyfile"):
            return self._pair(event, args)
        if event == "os.remove":
            return self._row("delete", args[0] if args else None)
        return ()

    def _pair(self, event: str, args: tuple[Any, ...]) -> Sequence[Mapping[str, object]]:
        verb = "move" if event == _RENAME else "copy"
        if len(args) < 2:
            return ()
        if verb == "copy":
            if len(self._pending) >= _PENDING:
                self._pending.clear()
            for arg in (args[0], args[1]):
                t = _text(arg)
                if t is not None:
                    self._pending.add(hash(t))
        return (*self._row(f"{verb} from", args[0]), *self._row(f"{verb} to", args[1]))

    def _is_inner_copy_open(self, path: object) -> bool:
        """The open ``shutil.copyfile`` makes of a path it announced is the copy's own: BootUI records it once.

        Only an open made from inside ``copyfile`` is: a copy that failed after its event (``SameFileError``) opened
        nothing, so the application's next open of that path is its own and is recorded.
        """
        text = _text(path)
        if text is None:
            return False
        h = hash(text)
        if h not in self._pending:
            return False
        self._pending.discard(h)
        frame = inspect.currentframe()
        for _ in range(_COPY_DEPTH):
            if frame is None:
                return False
            if frame.f_code is _COPYFILE:
                return True
            frame = frame.f_back
        return False

    def _row(self, kind: str, path: object) -> Sequence[Mapping[str, object]]:
        text = path if type(path) is str else _text(path)
        if not text:
            return ()  # a file descriptor names no file, nor does an empty name
        found = self._seen.get(text, _MISS)
        if found is _MISS:
            return self._row_miss(kind, text)
        if found is None:
            self.ignored += 1
            return ()
        req = _REQUEST_GET()
        matcher = self._matcher
        if matcher is not None and matcher.enabled and req is not None:
            try:
                match = matcher.check(text, "file", req)
            except Exception:
                return [_file_row(kind, NOT_CHECKED, "elsewhere", self._context_id, req)]
            if match is not _EMPTY and match is not _REPEATED and match is not None:
                return self._row_matched(kind, text, match, req)
        req_id = req.id if req is not None and self._context_id in (None, req.context_id) else None
        # inlined _file_row: one call per event over budget
        return [
            {
                "source": SOURCE,
                "kind": kind,
                "target": found[0],
                "origin": "unknown",
                "location": found[1],
                "requestId": req_id,
                "at": time.time_ns() // 1_000_000,
                "callSite": None,
                "threadName": threading.current_thread().name if req_id is None else None,
            }
        ]

    def _row_miss(self, kind: str, text: str) -> Sequence[Mapping[str, object]]:
        req = _REQUEST_GET()
        matcher = self._matcher
        if matcher is not None and matcher.enabled and req is not None:
            if self._is_skipped(_slashes(text)):
                self.ignored += 1
                return ()
            try:
                match = matcher.check(text, "file", req)
            except Exception:
                return [_file_row(kind, NOT_CHECKED, "elsewhere", self._context_id, req)]
            if match is not _EMPTY and match is not _REPEATED and match is not None:
                return self._row_matched(kind, text, match, req)
        return self._row_unmatched(kind, text, req)

    def _row_matched(
        self, kind: str, text: str, match: Match, req: RequestInfo | None
    ) -> Sequence[Mapping[str, object]]:
        if not match.names and unchecked(match):  # a matched name is read before the unchecked flags (BootUI fileUsed)
            target, location = NOT_CHECKED, "elsewhere"
        elif match.redacted is None:
            target, location = FROM_REQUEST_INPUT, "elsewhere"
        else:
            resolved = self._resolve(_slashes(match.redacted))
            target, location = (
                resolved if resolved is not None else (self._finish(_slashes(match.redacted)), "elsewhere")
            )
        file_row = _file_row(kind, target, location, self._context_id, req)
        sink_rows = self._matcher.rows("file", match, text, target, req) if self._matcher and match.names else ()
        return (file_row, *sink_rows)

    def _row_unmatched(self, kind: str, text: str, req: RequestInfo | None) -> Sequence[Mapping[str, object]]:
        seen = self._seen
        found = seen.get(text, _MISS)  # one lookup: another thread may clear the cache between two
        if found is _MISS:
            if len(seen) >= _SEEN:
                seen.clear()
            found = seen[text] = self._resolve(_slashes(text))
        if found is None:
            self.ignored += 1
            return ()
        return [_file_row(kind, found[0], found[1], self._context_id, req)]

    def _full_path(self, text: str) -> str:
        full = text if _is_absolute(text) else f"{self._cwd.rstrip('/')}/{text}"
        if "/." in full or "//" in full or full.endswith("/"):
            full = posixpath.normpath(full)
            if full.startswith("//"):
                full = "/" + full.lstrip("/")  # normpath keeps a leading pair; BootUI's clean() does not
        return full

    def _is_skipped(self, text: str) -> bool:
        full = self._full_path(text)
        probe = _fold(full) + "/"  # a trailing slash, so the directory itself is under itself
        return probe.startswith(self._skip)

    def _resolve(self, text: str) -> tuple[str, str] | None:
        """The pattern and place of ``text``, or None for an import or sharpit's own state."""
        full = self._full_path(text)
        probe = _fold(full) + "/"  # a trailing slash, so the directory itself is under itself
        if probe.startswith(self._skip):
            return None
        for base, lead, location in self._places:
            if probe.startswith(base):
                return self._finish(lead + full[len(base) :]), location
        place = "system" if probe.startswith(self._system) else "elsewhere"
        user = _other_home(full)
        if user > 0:
            full = f"{full[: full.rfind('/', 0, user) + 1]}*{full[user:]}"  # the user's name never reaches the mask
        return self._finish(full), place

    def _finish(self, pattern: str) -> str:
        return _collapse(self._mask(pattern))[:_MAX_PATTERN]
