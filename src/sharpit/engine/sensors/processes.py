"""The processes sensor (W6 lane S3): which commands the application starts, by file name only.

Minimisation: a row is ``{source, kind, target}``. The target is the base name of the program, or BootUI's
``(unknown)`` when the program cannot be told apart from what follows it. Arguments, the environment, the working
directory and a shell's ``NAME=value`` prefixes are never read into a row.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any, cast

SOURCE = "processes"
UNKNOWN = "(unknown)"  # SideEffects.commandName's marker for a command it cannot name
_MAX = 128
# a shell word's quoted run or escaped character; an assignment's value also takes an unnested $(...) or `...`
_PIECE = r"""'[^']*'|"(?:[^"\\]|\\.)*"|\\."""
_ASSIGNMENT = re.compile(rf"""\s*[A-Za-z_]\w*=(?:{_PIECE}|\$\([^()]*\)|`[^`]*`|\$(?!\()|[^\s'"\\$`()])*+(?=\s|$)""")
_NAMED = re.compile(r"\s*[A-Za-z_]\w*=")  # an assignment, whether its value parses or not
_WORD = re.compile(rf"""\s*((?:{_PIECE}|[^\s'"\\])++)(?=\s|$)""")
_QUOTE = re.compile("[\"']")


def _text(value: object) -> str | None:
    if type(value) is str:
        return value
    if isinstance(value, (str, bytes, os.PathLike)):
        raw: str | bytes = os.fspath(value)  # pyright: ignore[reportUnknownVariableType]
        return raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
    return None


def _program(command: str) -> str | None:
    """The file name of ``command``'s program: its first word after complete ``NAME=value`` prefixes, basenamed alone.

    Fails closed: a value or a quote that does not parse gives ``(unknown)``, never a fragment of what follows.
    """
    end = 0
    while match := _ASSIGNMENT.match(command, end):
        end = match.end()
    if _NAMED.match(command, end):
        return UNKNOWN
    if not command[end:].strip():
        return None
    word = _WORD.match(command, end)
    if word is None:
        return UNKNOWN
    token = word[1]
    # a quoted program is its quoted text (a Windows path with blanks); otherwise never past an inner quote (BootUI)
    program = token[1 : token.index(token[0], 1)] if token[0] in "\"'" else _QUOTE.split(token, 1)[0]
    # never past an '=' (BootUI, a start that may have failed), then the file name of this one word only
    name = program.partition("=")[0].replace("\\", "/").rpartition("/")[2].strip()
    return name[:_MAX] or UNKNOWN


def _argv_target(program: object, argv: object) -> str | None:
    named = _text(program)
    if named:
        return _program(named)
    if isinstance(argv, (list, tuple)) and argv:
        first = _text(cast("list[object]", argv)[0])
        return _program(first) if first else None
    line = _text(argv) if isinstance(argv, (str, bytes)) else None
    return _program(line) if line else None


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
            return _program(command) if command else None
        where = _ARGV_AT.get(event)
        return _argv_target(args[where[0]], args[where[1]]) if where and len(args) > where[1] else None
