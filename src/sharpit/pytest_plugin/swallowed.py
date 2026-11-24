"""Swallowed application exceptions during a test session (spec 0.4.0 §5.5 F1), observed with ``sys.monitoring``.

Only ``EXCEPTION_HANDLED`` is subscribed (``RAISE`` fires on every internal ``StopIteration``). The callback returns at
once outside a test phase and for handlers outside application code; the raise location does not matter.
"""

from __future__ import annotations

import contextlib
import functools
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from types import CodeType
from typing import Any, cast

from sharpit.engine.capture.correlation import TEST
from sharpit.engine.capture.frames import is_application_frame
from sharpit.engine.sensors import TOOL_IDS as _TOOL_IDS
from sharpit.engine.sensors import MonitoringTool, allocator
from sharpit.engine.testsession.doubles import raised_by_test_double
from sharpit.engine.testsession.facts import PHASES, PhaseFacts, SwallowedFact
from sharpit.engine.testsession.swallowed import PROGRAMMING_ERRORS, site_identity, swallowing_site
from sharpit.pytest_plugin.paths import relative_location

TOOL_IDS = _TOOL_IDS
SOURCE = "swallowed-exceptions"

type TestTag = tuple[str, int, str]
type SwallowedSink = Callable[[TestTag, SwallowedFact], None]


@dataclass(frozen=True)
class CaptureStatus:
    attached: bool
    reason: str | None = None


def _identity_path(filename: str, path: str) -> str:
    # Older reports keyed files under names such as "..cache" by their absolute path.
    return Path(filename).as_posix() if path.startswith("..") else path


@functools.lru_cache(maxsize=4096)
def _fact(code: CodeType, offset: int, exc_type: type[BaseException], root: str, cwd: str) -> SwallowedFact | None:
    site = swallowing_site(code, offset, exc_type)
    if site is None:
        return None
    path = relative_location(code.co_filename, root)
    identity = site_identity(_identity_path(code.co_filename, path), site, exc_type.__name__)
    legacy = f"{_identity_path(code.co_filename, relative_location(code.co_filename, cwd))}:{site.line}"
    return SwallowedFact(
        f"{path}:{site.line}", exc_type.__name__, issubclass(exc_type, PROGRAMMING_ERRORS), identity, legacy
    )


class MonitoringCapture:
    def __init__(self, on_error: Callable[[BaseException], None] | None = None, root: Path | None = None) -> None:
        self._cwd = os.getcwd()  # the form the earlier versions wrote, to name a stale entry
        self._root = str(root) if root is not None else self._cwd  # paths read the same whatever the cwd becomes
        self.tool_id: int | None = None
        self._tool: MonitoringTool | None = None
        self._sink: SwallowedSink | None = None
        self._on_error = on_error
        self._failed = False
        self._double_test: TestTag | None = None
        self._ordinary_exceptions: set[SwallowedFact] = set()

    def attach(self, sink: SwallowedSink) -> CaptureStatus:
        tool = allocator.claim()
        if tool is None:
            return CaptureStatus(False, "sys.monitoring tool ids 3 and 4 are in use")
        self.tool_id, self._tool, self._sink = tool.tool_id, tool, sink
        handled = sys.monitoring.events.EXCEPTION_HANDLED
        try:
            tool.on_event(handled, self._handled)
            tool.listen(handled)
        except BaseException:
            with contextlib.suppress(Exception):  # the setup error is the one to report
                self.detach()
            raise
        return CaptureStatus(True)

    def detach(self) -> None:
        tool, self._tool = self._tool, None
        self.tool_id = None
        if tool is not None:
            tool.release()

    def _handled(self, code: CodeType, offset: int, exc: BaseException) -> None:
        test = TEST.get()
        if test is None or not is_application_frame(code.co_filename):
            return
        try:
            fact = _fact(code, offset, type(exc), self._root, self._cwd)
            if fact is not None and self._sink is not None:
                self._sink(test, replace(fact, test_double=True) if self._is_double(test, fact, exc) else fact)
        except Exception as error:  # noqa: BLE001 - a raising callback would surface in the host's code
            if not self._failed and self._on_error is not None:
                self._failed = True
                self._on_error(error)

    def _is_double(self, test: TestTag, fact: SwallowedFact, exc: BaseException) -> bool:
        """Whether a test double raised ``exc``; an ordinary fact is classified once per test."""
        if test != self._double_test:
            self._double_test = test
            self._ordinary_exceptions.clear()
        if fact in self._ordinary_exceptions:
            return False
        if raised_by_test_double(exc):  # rechecked each time, so a later real raise can clear the note
            return True
        self._ordinary_exceptions.add(fact)
        return False


def record(sink: Any, tag: TestTag, fact: SwallowedFact) -> None:
    """Add ``fact`` to the running test's phase (once per handler and type); anything else is not this test's."""
    current = sink.current_test
    if current is None or tag[2] not in PHASES or (current.key.node_id, current.key.attempt) != tag[:2]:
        return
    phase = cast("PhaseFacts", current.phases.setdefault(tag[2], PhaseFacts()))
    if fact not in phase.swallowed:
        phase.swallowed.append(fact)
    elif not fact.test_double:  # one real raise means the clause's code did run: it clears the double's note
        index = phase.swallowed.index(fact)
        phase.swallowed[index] = replace(phase.swallowed[index], test_double=False)


def attach_session(config: Any, state: Any) -> None:
    """Claim a tool id for this session (once); the config cleanup frees it even when a later hook fails."""
    from sharpit import pytest_plugin

    plugin = cast(Any, pytest_plugin)
    try:
        if getattr(state, "swallowed_capture", None) is not None:
            return
        capture = MonitoringCapture(lambda error: plugin._record_hook_failure(state.sink, error), config.rootpath)
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
