"""The files sensor (W6 lane S3): which files the application opens, deletes, moves and copies, as path patterns.

Minimisation: a row is ``{source, kind, target, origin, location}``. The target is a pattern: relative to the working
directory (``./``), the temporary directory (``$TMPDIR``) or the home (``~``), with a secret-looking segment masked and
each uuid, long hex run and number collapsed (``report-{n}.csv``). File content and file descriptors are never read.
The origin is ``unknown``: sharpit does not walk the stack on a file event (BootUI's frame summary has no cheap port).
Imports (the interpreter's own prefixes) and sharpit's own state are left out and counted in ``ignored``.
"""

from __future__ import annotations

import os
import posixpath
import re
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from typing import Any

SOURCE = "files"
_FOLD = os.name == "nt"
_MAX_PATTERN = 200  # SideEffects.MAX_PATTERN
_ID_RUNS = re.compile(  # SideEffects.collapse: a JWT-like tail, a uuid, or any alphanumeric run
    r"(?P<token>(?<![0-9A-Za-z])eyJ[^/.]*\.[^/]*)"
    r"|(?P<uuid>(?<![0-9A-Za-z])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![0-9A-Za-z]))"
    r"|(?P<run>[0-9A-Za-z]+)"
)
_RUNS = re.compile(
    r"(?<![0-9A-Za-z])(?P<run>[0-9A-Za-z]*[0-9][0-9A-Za-z]*|[A-Za-z]{24,})"
)  # _ID_RUNS without a token or a uuid
_DIGITS = re.compile(r"\d+")
_COLLAPSIBLE = re.compile(r"\d|eyJ|[A-Za-z]{24}")  # nothing else can collapse: most paths stop here, after one scan
_SEEN = 256  # distinct paths remembered per sensor, cleared when full (BootUI's Seen cache)
_HEX_LETTERS = frozenset("abcdefABCDEF")
_DRIVE = re.compile(r"[A-Za-z]:/")
_SYSTEM = (
    "/etc", "/usr", "/proc", "/sys", "/dev", "/bin", "/sbin", "/lib", "/var", "/boot", "/opt",
    "c:/windows", "c:/program files", "c:/programdata",
)  # fmt: skip

_WRITE_FLAGS = (
    os.O_WRONLY | os.O_RDWR | getattr(os, "O_APPEND", 0) | getattr(os, "O_CREAT", 0) | getattr(os, "O_TRUNC", 0)
)


def _slashes(path: str) -> str:
    return path.replace("\\", "/")


def _fold(path: str) -> str:
    return path.casefold() if _FOLD else path


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


def _other_home(path: str) -> int:
    """``SideEffects.otherHome``: where the user name ends in another user's home directory, else -1."""
    start, previous = 0, None
    for index, segment in enumerate(path.split("/")):
        if index > 5:
            return -1
        end = start + len(segment)
        users = segment.casefold() == "users" and index <= 4
        home = segment == "home" and (index == 1 or (index == 2 and previous in ("var", "export")))
        if (users or home) and end < len(path):
            user_end = path.find("/", end + 1)
            user_end = len(path) if user_end < 0 else user_end
            return user_end if user_end > end + 1 else -1
        previous, start = segment, end + 1
    return -1


class FilesSensor:
    name = SOURCE
    events = ("open", "os.remove", "os.rename", "shutil.copyfile")

    def __init__(
        self,
        mask_path: Callable[[str], str] = lambda path: path,
        *,
        own: Iterable[str] = (),
        cwd: str | None = None,
        home: str | None = None,
        tmp: str | None = None,
    ) -> None:
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
        self.ignored = 0

    def record(self, event: str, args: tuple[Any, ...]) -> tuple[Mapping[str, object], ...]:
        if event == "open":
            return self._open(args)
        if event in ("os.rename", "shutil.copyfile"):
            return self._pair(event, args)
        if event == "os.remove":
            return self._row("delete", args[0] if args else None)
        return ()

    def _open(self, args: tuple[Any, ...]) -> tuple[Mapping[str, object], ...]:
        if len(args) < 3:
            return ()
        path, mode, flags = args[:3]
        wrote = (
            any(c in mode for c in "wax+")
            if isinstance(mode, str)
            else bool(isinstance(flags, int) and flags & _WRITE_FLAGS)
        )
        return self._row("write" if wrote else "read", path)

    def _pair(self, event: str, args: tuple[Any, ...]) -> tuple[Mapping[str, object], ...]:
        verb = "move" if event == "os.rename" else "copy"
        if len(args) < 2:
            return ()
        return (*self._row(f"{verb} from", args[0]), *self._row(f"{verb} to", args[1]))

    def _row(self, kind: str, path: object) -> tuple[Mapping[str, object], ...]:
        if not isinstance(path, (str, bytes, os.PathLike)):
            return ()  # a file descriptor names no file
        raw: str | bytes = os.fspath(path)  # pyright: ignore[reportUnknownVariableType]
        text = raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
        if not text:
            return ()
        seen = self._seen
        if text in seen:
            found = seen[text]
        else:
            if len(seen) >= _SEEN:
                seen.clear()
            found = seen[text] = self._resolve(_slashes(text))
        if found is None:
            self.ignored += 1
            return ()
        return ({"source": SOURCE, "kind": kind, "target": found[0], "origin": "unknown", "location": found[1]},)

    def _resolve(self, text: str) -> tuple[str, str] | None:
        """The pattern and place of ``text``, or None for an import or sharpit's own state."""
        full = text if _is_absolute(text) else f"{self._cwd.rstrip('/')}/{text}"
        if "/." in full or "//" in full or full.endswith("/"):
            full = posixpath.normpath(full)
            if full.startswith("//"):
                full = "/" + full.lstrip("/")  # normpath keeps a leading pair; BootUI's clean() does not
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
