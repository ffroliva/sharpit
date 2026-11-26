"""The processes sensor (W6 lane S3): which commands the application starts, by file name only.

Minimisation: a row is ``{source, kind, target, requestId, at, callSite, threadName}``. The target is the base name of
the program, or BootUI's ``(unknown)`` when the program cannot be told apart from what follows it. Arguments, the
environment, the working directory and a shell's ``NAME=value`` prefixes are never read into a row.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from types import FrameType
from typing import Any, cast

from sharpit.engine.capture.correlation import REQUEST
from sharpit.engine.capture.frames import call_site_label, first_application_frame
from sharpit.engine.sensors.sinks import (
    F_OVERFLOW,
    FROM_REQUEST_INPUT,
    MAX_ARGUMENTS,
    NOT_CHECKED,
    SinkMatcher,
    unchecked,
)

SOURCE = "processes"
UNKNOWN = "(unknown)"  # SideEffects.commandName's marker for a command it cannot name
_MAX = 128
# a shell word's quoted run or escaped character; an assignment's value also takes an unnested $(...) or `...`
_PIECE = r"""'[^']*'|"(?:[^"\\]|\\.)*"|\\."""
_ASSIGNMENT = re.compile(rf"""\s*[A-Za-z_]\w*=(?:{_PIECE}|\$\([^()]*\)|`[^`]*`|\$(?!\()|[^\s'"\\$`()])*+(?=\s|$)""")
_NAMED = re.compile(r"\s*[A-Za-z_]\w*=")  # an assignment, whether its value parses or not
_WORD = re.compile(rf"""\s*((?:{_PIECE}|[^\s'"\\])++)(?=\s|$)""")
_QUOTE = re.compile("[\"']")
# cmd.exe has no backslash escape: on a Windows-shaped command a word ends at a blank outside quotes
_WIN_WORD = re.compile(r"""\s*((?:'[^']*'|"[^"]*"|[^\s'"])++)(?=\s|$)""")
_WINDOWS = re.compile(r"""\s*["']?(?:[A-Za-z]:|\\\\|[\w.-]+\\[\w.-])""")
_META = ";|&<>#`()$,"  # a shell metacharacter ends the program word; one that starts it is no program at all
_AT_META = re.compile(f"[{re.escape(_META)}]")
_PLAIN = re.compile(r"[^\s'\"\\=;|&<>#`()$,]+")  # one word with no quote, escape or '=': a path to basename as it is


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
    if _PLAIN.fullmatch(command):
        return command.rpartition("/")[2][:_MAX] or UNKNOWN
    end = 0
    while match := _ASSIGNMENT.match(command, end):
        end = match.end()
    if _NAMED.match(command, end):
        return UNKNOWN
    if not command[end:].strip():
        return None
    word = (_WIN_WORD if _WINDOWS.match(command, end) else _WORD).match(command, end)
    if word is None:
        return UNKNOWN
    token = word[1]
    # a quoted program is its quoted text (a Windows path with blanks); otherwise never past an inner quote (BootUI)
    if token[0] in "\"'":
        program = token[1 : token.index(token[0], 1)]
    elif token[0] in _META:
        return UNKNOWN
    else:
        program = _AT_META.split(_QUOTE.split(token, 1)[0], 1)[0]
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


def _program_first_end(command: str, program_name: str | None) -> int:
    if not program_name or program_name == UNKNOWN:
        return 0
    pos = command.find(program_name)
    return pos + len(program_name) if pos >= 0 else 0


def _check_explicit_executable(
    matcher: SinkMatcher,
    program: str,
    sink_rows: list[Mapping[str, object]],
) -> str | None:
    match = matcher.check(program, "command")
    if match is None:
        return None
    if match.names:
        sink_rows.extend(matcher.rows("command", match, program, "(the executable)"))
        return FROM_REQUEST_INPUT
    return NOT_CHECKED if unchecked(match) else None


def _check_joined_command(
    matcher: SinkMatcher,
    command_line: str,
    command_name: str,
    executable: str | None,
    sink_rows: list[Mapping[str, object]],
) -> str | None:
    match = matcher.check(command_line, "command")
    if match is None:
        return executable
    if match.names:
        prog_end = _program_first_end(command_line, command_name)
        overflow = bool(match.flags & F_OVERFLOW)
        held = overflow or (prog_end > 0 and any(s[1] < prog_end for s in match.spans))
        if held:
            executable = FROM_REQUEST_INPUT
        target = "(the executable)" if executable is not None else command_name
        sink_rows.extend(matcher.rows("command", match, command_line, target))
        return executable
    if unchecked(match) and executable is None:
        return NOT_CHECKED
    return executable


def _process_row(target: str, context_id: str | None, caller: FrameType | None) -> dict[str, object]:
    req = REQUEST.get()
    req_id = req.id if req is not None and (context_id is None or req.context_id == context_id) else None
    app_frame = first_application_frame(caller)
    return {
        "source": SOURCE,
        "kind": "start",
        "target": target,
        "requestId": req_id,
        "at": time.time_ns() // 1_000_000,
        "callSite": call_site_label(app_frame) if app_frame is not None else None,
        "threadName": threading.current_thread().name if req_id is None else None,
    }


def _string_sink_rows(
    matcher: SinkMatcher,
    command_name: str,
    program: str | None,
    command_line: str,
    context_id: str | None = None,
    caller: FrameType | None = None,
) -> tuple[Mapping[str, object], ...]:
    executable: str | None = None
    checking = False
    sink_rows: list[Mapping[str, object]] = []
    try:
        checking = True
        if program is not None:
            executable = _check_explicit_executable(matcher, program, sink_rows)
        executable = _check_joined_command(matcher, command_line, command_name, executable, sink_rows)
    except Exception:
        if checking and executable is None:
            executable = NOT_CHECKED
        sink_rows.clear()
    proc_target = executable if executable is not None else command_name
    return (_process_row(proc_target, context_id, caller), *sink_rows)


def _argv_elements(program: object, argv: Sequence[object]) -> list[str]:
    prog_text = _text(program)
    if argv:
        first = prog_text or _text(argv[0]) or ""
        rest = [_text(arg) or "" for arg in argv[1:MAX_ARGUMENTS]]
        return [first, *rest]
    return [prog_text or ""] if prog_text else []


def _check_argv_elements(
    matcher: SinkMatcher,
    elements: list[str],
    command_name: str,
) -> tuple[str | None, list[Mapping[str, object]]]:
    executable: str | None = None
    sink_rows: list[Mapping[str, object]] = []
    size = min(len(elements), MAX_ARGUMENTS)
    for i in range(size):
        argument = elements[i]
        match = matcher.check(argument, "command")
        if match is None:
            continue
        if not match.names:
            if i == 0 and unchecked(match):
                executable = NOT_CHECKED
            continue
        if i == 0:
            executable = FROM_REQUEST_INPUT
        target = (
            "(the executable)"
            if i == 0
            else f"(the executable), argument {i}"
            if executable is not None
            else f"{command_name}, argument {i}"
        )
        sink_rows.extend(matcher.rows("command", match, argument, target))
    return executable, sink_rows


def _argv_sink_rows(
    matcher: SinkMatcher,
    command_name: str,
    program: object,
    argv: Sequence[object],
    context_id: str | None = None,
    caller: FrameType | None = None,
) -> tuple[Mapping[str, object], ...]:
    elements = _argv_elements(program, argv)
    executable: str | None = None
    checking = False
    sink_rows: list[Mapping[str, object]] = []
    try:
        checking = True
        executable, sink_rows = _check_argv_elements(matcher, elements, command_name)
    except Exception:
        if checking and executable is None:
            executable = NOT_CHECKED
        sink_rows.clear()
    proc_target = executable if executable is not None else command_name
    return (_process_row(proc_target, context_id, caller), *sink_rows)


_ARGV_AT = {
    "subprocess.Popen": (0, 1),
    "os.exec": (0, 1),
    "os.spawn": (1, 2),
    "os.posix_spawn": (0, 1),
}  # (program, argv)


class ProcessesSensor:
    name = SOURCE
    events = ("subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn")

    def __init__(self, matcher: SinkMatcher | None = None, *, context_id: str | None = None) -> None:
        self._matcher = matcher
        self._context_id = (
            context_id if context_id is not None else (matcher._context_id if matcher is not None else None)  # pyright: ignore[reportPrivateUsage]
        )

    def record(self, event: str, args: tuple[Any, ...]) -> tuple[Mapping[str, object], ...]:
        caller = sys._getframe(1)  # pyright: ignore[reportPrivateUsage]
        if self._matcher is None:
            target = self._target(event, args)
            return (_process_row(target, self._context_id, caller),) if target else ()
        target = self._target(event, args)
        if target is None:
            return ()
        return self._record_matched(event, args, target, caller)

    def _record_matched(
        self,
        event: str,
        args: tuple[Any, ...],
        target: str | None = None,
        caller: FrameType | None = None,
    ) -> tuple[Mapping[str, object], ...]:
        if self._matcher is None:
            return ()
        cmd_target = target if target is not None else self._target(event, args)
        if cmd_target is None:
            return ()
        if event == "os.system":
            command = _text(args[0]) if args else None
            return (
                _string_sink_rows(self._matcher, cmd_target, None, command, self._context_id, caller) if command else ()
            )
        where = _ARGV_AT.get(event)
        if not where or len(args) <= where[1]:
            return ()
        program, argv = args[where[0]], args[where[1]]
        if isinstance(argv, (list, tuple)):
            return _argv_sink_rows(
                self._matcher, cmd_target, program, cast("Sequence[object]", argv), self._context_id, caller
            )
        line = _text(cast("object", argv)) if isinstance(argv, (str, bytes)) else None
        prog_text = _text(program) if program is not None else None
        if line is not None:
            return _string_sink_rows(self._matcher, cmd_target, prog_text, line, self._context_id, caller)
        if prog_text is not None:
            return _string_sink_rows(self._matcher, cmd_target, None, prog_text, self._context_id, caller)
        return ()

    @staticmethod
    def _target(event: str, args: tuple[Any, ...]) -> str | None:
        if event == "os.system":
            command = _text(args[0]) if args else None
            return _program(command) if command else None
        where = _ARGV_AT.get(event)
        return _argv_target(args[where[0]], args[where[1]]) if where and len(args) > where[1] else None
