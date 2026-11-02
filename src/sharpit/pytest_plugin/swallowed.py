"""Swallowed application exceptions during a test session (spec 0.4.0 §5.5 F1), observed with ``sys.monitoring``."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from types import CodeType
from typing import Any

from sharpit.engine.capture.correlation import TEST
from sharpit.engine.testsession.facts import SwallowedFact

TOOL_IDS = (3, 4)  # never 0 debugger, 1 coverage, 2 profiler, 5 optimizer
SOURCE = "swallowed-exceptions"

type TestTag = tuple[str, int, str]
type SwallowedSink = Callable[[TestTag, SwallowedFact], None]


@dataclass(frozen=True)
class CaptureStatus:
    attached: bool
    reason: str | None = None


class MonitoringCapture:
    def __init__(self, on_error: Callable[[BaseException], None] | None = None) -> None:
        self.tool_id: int | None = None
        self._on_error = on_error

    def attach(self, sink: SwallowedSink) -> CaptureStatus:
        monitoring = sys.monitoring
        free = next((i for i in TOOL_IDS if monitoring.get_tool(i) is None), None)
        if free is not None:
            monitoring.use_tool_id(free, "sharpit")
            self.tool_id = free

            def handled(code: CodeType, offset: int, exc: BaseException) -> Any:
                sink(TEST.get() or ("", 0, "call"), SwallowedFact(f"{code.co_filename}:{offset}", "x", False))

            monitoring.register_callback(free, monitoring.events.EXCEPTION_HANDLED, handled)
            monitoring.set_events(free, monitoring.events.EXCEPTION_HANDLED | monitoring.events.RAISE)
        return CaptureStatus(True)

    def detach(self) -> None:
        if self.tool_id is not None:
            sys.monitoring.set_events(self.tool_id, 0)
            sys.monitoring.free_tool_id(self.tool_id)
            self.tool_id = None


def attach_session(config: Any, state: Any) -> None:
    capture = MonitoringCapture()
    capture.attach(lambda tag, fact: None)
    state.swallowed_capture = capture


def detach_session(state: Any) -> None:
    return None
