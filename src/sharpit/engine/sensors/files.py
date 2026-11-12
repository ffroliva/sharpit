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
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_HEX = re.compile(r"(?<![0-9A-Za-z])(?=[0-9]*[a-fA-F])[0-9a-fA-F]{8,}(?![0-9A-Za-z])")
_NUMBER = re.compile(r"\d+")
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


def _is_absolute(path: str) -> bool:
    return path.startswith("/") or bool(_DRIVE.match(path))


def _under(path: str, base: str) -> str | None:
    """``path`` below directory ``base`` (both with forward slashes), as a relative remainder, else None."""
    a, b = (path.casefold(), base.casefold()) if _FOLD else (path, base)
    if a == b:
        return ""
    prefix = b.rstrip("/") + "/"
    return path[len(prefix) :] if a.startswith(prefix) else None


def _collapse(path: str) -> str:
    return _NUMBER.sub("{n}", _HEX.sub("{hex}", _UUID.sub("{uuid}", path)))


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
        self._places = (
            (self._cwd, "./", "working-directory"),
            (_slashes(tmp if tmp is not None else tempfile.gettempdir()), "$TMPDIR/", "temporary-directory"),
            (_slashes(home if home is not None else os.path.expanduser("~")), "~/", "home"),
        )
        skipped = {sys.prefix, sys.base_prefix, sys.exec_prefix, *own}
        self._skip = tuple(_slashes(os.path.abspath(path)) for path in skipped if path)
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
        text = _slashes(raw if isinstance(raw, str) else raw.decode("utf-8", "replace"))
        if not text:
            return ()
        full = posixpath.normpath(text if _is_absolute(text) else f"{self._cwd.rstrip('/')}/{text}")
        if self._ignored(full):
            self.ignored += 1
            return ()
        target, location = self._pattern(full)
        return ({"source": SOURCE, "kind": kind, "target": target, "origin": "unknown", "location": location},)

    def _ignored(self, full: str) -> bool:
        return any(_under(full, base) is not None for base in self._skip)

    def _pattern(self, full: str) -> tuple[str, str]:
        best: tuple[int, str, str] | None = None
        for base, lead, location in self._places:
            rest = _under(full, base)
            if rest is not None and (best is None or len(base) > best[0]):
                best = (len(base), lead + rest, location)
        if best is not None:
            return _collapse(self._mask(best[1])), best[2]
        folded = full.casefold() if _FOLD else full
        place = "system" if any(folded == s or folded.startswith(s + "/") for s in _SYSTEM) else "elsewhere"
        return _collapse(self._mask(full)), place
