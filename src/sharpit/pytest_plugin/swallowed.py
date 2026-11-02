"""Swallowed application exceptions during a test session (spec 0.4.0 §5.5 F1), observed with ``sys.monitoring``.

Only ``EXCEPTION_HANDLED`` is subscribed (``RAISE`` fires on every internal ``StopIteration``). The callback returns at
once outside a test phase and for handlers outside application code; the raise location does not matter.
"""

from __future__ import annotations

import functools
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import CodeType
from typing import Any, cast

from sharpit.engine.capture.correlation import TEST
from sharpit.engine.capture.frames import is_application_frame
from sharpit.engine.testsession.facts import PHASES, PhaseFacts, SwallowedFact
from sharpit.engine.testsession.swallowed import PROGRAMMING_ERRORS, swallowing_clause_line

TOOL_IDS = (3, 4)  # never 0 debugger, 1 coverage, 2 profiler, 5 optimizer
SOURCE = "swallowed-exceptions"

type TestTag = tuple[str, int, str]
type SwallowedSink = Callable[[TestTag, SwallowedFact], None]


@dataclass(frozen=True)
class CaptureStatus:
    attached: bool
    reason: str | None = None


def _location(filename: str, line: int) -> str:
    try:
        path = os.path.relpath(filename)
    except ValueError:  # another drive (Windows)
        path = filename
    if path.startswith(".."):  # outside the working directory: keep it absolute
        path = filename
    return f"{Path(path).as_posix()}:{line}"


@functools.lru_cache(maxsize=4096)
def _fact(code: CodeType, offset: int, exc_type: type[BaseException]) -> SwallowedFact | None:
    line = swallowing_clause_line(code, offset, exc_type)
    if line is None:
        return None
    return SwallowedFact(_location(code.co_filename, line), exc_type.__name__, issubclass(exc_type, PROGRAMMING_ERRORS))


class MonitoringCapture:
    def __init__(self, on_error: Callable[[BaseException], None] | None = None) -> None:
        self.tool_id: int | None = None
        self._sink: SwallowedSink | None = None
        self._on_error = on_error
        self._failed = False

    def attach(self, sink: SwallowedSink) -> CaptureStatus:
        monitoring = sys.monitoring
        free = next((i for i in TOOL_IDS if monitoring.get_tool(i) is None), None)
        if free is None:
            return CaptureStatus(False, "sys.monitoring tool ids 3 and 4 are in use")
        monitoring.use_tool_id(free, "sharpit")
        self.tool_id, self._sink = free, sink
        monitoring.register_callback(free, monitoring.events.EXCEPTION_HANDLED, self._handled)
        monitoring.set_events(free, monitoring.events.EXCEPTION_HANDLED)
        return CaptureStatus(True)

    def detach(self) -> None:
        tool, self.tool_id = self.tool_id, None
        if tool is None:
            return
        monitoring = sys.monitoring
        try:
            monitoring.set_events(tool, 0)
            monitoring.register_callback(tool, monitoring.events.EXCEPTION_HANDLED, None)
        finally:
            monitoring.free_tool_id(tool)

    def _handled(self, code: CodeType, offset: int, exc: BaseException) -> None:
        test = TEST.get()
        if test is None or not is_application_frame(code.co_filename):
            return
        try:
            fact = _fact(code, offset, type(exc))
            if fact is not None and self._sink is not None:
                self._sink(test, fact)
        except Exception as error:  # noqa: BLE001 - a raising callback would surface in the host's code
            if not self._failed and self._on_error is not None:
                self._failed = True
                self._on_error(error)


def record(sink: Any, tag: TestTag, fact: SwallowedFact) -> None:
    """Add ``fact`` to the running test's phase (once per handler and type); anything else is not this test's."""
    current = sink.current_test
    if current is None or tag[2] not in PHASES or (current.key.node_id, current.key.attempt) != tag[:2]:
        return
    phase = cast("PhaseFacts", current.phases.setdefault(tag[2], PhaseFacts()))
    if fact not in phase.swallowed:
        phase.swallowed.append(fact)


def attach_session(config: Any, state: Any) -> None:
    """Claim a tool id for this session (once); the config cleanup frees it even when a later hook fails."""
    from sharpit import pytest_plugin

    plugin = cast(Any, pytest_plugin)
    try:
        if getattr(state, "swallowed_capture", None) is not None:
            return
        capture = MonitoringCapture(lambda error: plugin._record_hook_failure(state.sink, error))
        status = capture.attach(lambda tag, fact: record(state.sink, tag, fact))
        state.swallowed_capture = capture
        config.add_cleanup(capture.detach)
        source: dict[str, Any] = {
            "name": SOURCE,
            "attached": status.attached,
            "reason": status.reason,
            "limitations": [],
        }
        state.sink.facts.sources.append(source)
    except Exception as exc:  # noqa: BLE001
        plugin._record_hook_failure(state.sink, exc)


def detach_session(state: Any) -> None:
    capture = getattr(state, "swallowed_capture", None)
    if capture is None:
        return
    try:
        capture.detach()
    except Exception as exc:  # noqa: BLE001
        from sharpit import pytest_plugin

        cast(Any, pytest_plugin)._record_hook_failure(state.sink, exc)
