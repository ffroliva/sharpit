"""The processes sensor (W6 lane S3): which commands the application starts, by file name only.

Minimisation: a row is ``{source, kind, target}``. The target is the base name of the program. Arguments, the
environment, the working directory and a shell's ``NAME=value`` prefixes are never read into a row.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any, cast

SOURCE = "processes"
_MAX = 128
_ASSIGNMENT = re.compile(r"""\s*[A-Za-z_]\w*=(?:'[^']*'|"[^"]*"|\S*)""")  # FOO=bar, FOO='a b': a shell's env prefix


def _text(value: object) -> str | None:
    if type(value) is str:
        return value
    if isinstance(value, (str, bytes, os.PathLike)):
        raw: str | bytes = os.fspath(value)  # pyright: ignore[reportUnknownVariableType]
        return raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
    return None


def _base(program: str) -> str | None:
    """The file name of ``program``, cut at its first blank: whatever follows is an argument, never a name."""
    text = program.replace("\\", "/").strip()
    first_blank = next((i for i, c in enumerate(text) if c.isspace()), len(text))
    if "/" not in text[:first_blank]:
        text = text[:first_blank]  # ``prog --password x``: no separator before the blank, so nothing after it is a name
    words = text.rpartition("/")[2].split(
        None, 1
    )  # shortcut: an unquoted path with blanks and a later ``/`` argument yields that segment
    return words[0][:_MAX] if words else None


def _first_word(command: str) -> str | None:
    """The program of a command line: a quoted path up to its closing quote, else up to the first blank."""
    command = command.lstrip()
    if command[:1] in ("'", '"'):
        end = command.find(command[0], 1)
        return command[1 : end if end > 0 else None].lstrip()  # an unclosed quote: the text after it, cut by the caller
    return command.split(None, 1)[0] if command else None


def _shell_target(command: str) -> str | None:
    while match := _ASSIGNMENT.match(command):
        command = command[match.end() :]
    word = _first_word(command)
    return _base(word) if word else None


def _argv_target(program: object, argv: object) -> str | None:
    named = _text(program)
    if named:
        return _base(named)
    if isinstance(argv, (list, tuple)) and argv:
        return _base(_text(cast("list[object]", argv)[0]) or "")
    if isinstance(argv, (str, bytes)):
        line = _text(argv)
        return _base(_first_word(line) or "") if line else None
    return None


_ARGV_AT = {
    "subprocess.Popen": (0, 1),
    "os.exec": (0, 1),
    "os.spawn": (1, 2),
    "os.posix_spawn": (0, 1),
}  # (program, argv)


class ProcessesSensor:
    name = SOURCE
    events = ("subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn")

    def record(self, event: str, args: tuple[Any, ...]) -> tuple[Mapping[str, object], ...]:
        target = self._target(event, args)
        return ({"source": SOURCE, "kind": "start", "target": target},) if target else ()

    @staticmethod
    def _target(event: str, args: tuple[Any, ...]) -> str | None:
        if event == "os.system":
            command = _text(args[0]) if args else None
            return _shell_target(command) if command else None
        where = _ARGV_AT.get(event)
        return _argv_target(args[where[0]], args[where[1]]) if where and len(args) > where[1] else None
