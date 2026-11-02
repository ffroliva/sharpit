"""Swallowed application exceptions observed with sys.monitoring during a test session (spec 0.4.0 §5.5 F1)."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.capture.correlation import TEST
from sharpit.engine.testsession.facts import SwallowedFact
from sharpit.pytest_plugin.swallowed import TOOL_IDS, MonitoringCapture, TestTag

FIXTURE = Path(__file__).parents[1] / "fixtures" / "apps" / "swallowed_exception"
RULE = "sharpit.swallowed-exception"


def _week_project(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        weekapp=(FIXTURE / "weekapp.py").read_text("utf-8"),
        test_weeks=(FIXTURE / "cases.py").read_text("utf-8"),
    )


def _report(pytester: pytest.Pytester) -> dict[str, Any]:
    return json.loads((pytester.path / "report.json").read_text("utf-8"))


def _test_entry(data: dict[str, Any], name: str) -> dict[str, Any]:
    return next(t for t in data["tests"] if t["nodeId"].endswith(f"::{name}"))


def test_spike_f1_swallowed_attribute_error_fails(pytester: pytest.Pytester) -> None:
    # spike: F1 T4
    _week_project(pytester)

    pytester.runpytest_subprocess("--sharpit", "--sharpit-app=weekapp:app", "--sharpit-report=report.json", "-q")

    data = _report(pytester)
    planted = [f for f in data["findings"] if f["ruleId"] == RULE and f["testNodeId"].endswith("::test_week_count")]
    assert planted, f"no {RULE} finding for the planted handler: {[f['ruleId'] for f in data['findings']]}"
    assert _test_entry(data, "test_week_count")["outcome"] == "failed"


# --- Task 3: the sys.monitoring capture ------------------------------------------------------------------------------

LIBRARY = """
def library_swallow():
    try:
        return {}["missing"]
    except Exception:
        return None
"""


def _app_swallow() -> int:
    try:
        return json.loads("not json")  # raised inside the standard library, handled here
    except Exception:
        return 0


def _app_swallow_line() -> int:
    return _app_swallow.__code__.co_firstlineno + 3  # the ``except Exception:`` line


@pytest.fixture
def capture() -> Iterator[tuple[MonitoringCapture, list[tuple[TestTag, SwallowedFact]]]]:
    seen: list[tuple[TestTag, SwallowedFact]] = []
    monitor = MonitoringCapture()
    status = monitor.attach(lambda tag, fact: seen.append((tag, fact)))
    if not status.attached:
        pytest.skip(f"sys.monitoring tool ids taken by the outer session: {status.reason}")
    try:
        yield monitor, seen
    finally:
        monitor.detach()


@pytest.fixture
def in_test() -> Iterator[TestTag]:
    tag: TestTag = ("tests/test_x.py::test_x", 1, "call")
    token = TEST.set(tag)
    try:
        yield tag
    finally:
        TEST.reset(token)


def test_library_raise_app_handler_is_seen(
    capture: tuple[MonitoringCapture, list[tuple[TestTag, SwallowedFact]]], in_test: TestTag
) -> None:
    _, seen = capture

    _app_swallow()

    location = f"{Path(os.path.relpath(__file__)).as_posix()}:{_app_swallow_line()}"
    assert seen == [(in_test, SwallowedFact(location, "JSONDecodeError", False))]


def test_library_handler_is_ignored(
    capture: tuple[MonitoringCapture, list[tuple[TestTag, SwallowedFact]]],
    in_test: TestTag,
    tmp_path: Path,
) -> None:
    _, seen = capture
    library = tmp_path / "site-packages" / "swallow_library.py"
    library.parent.mkdir()
    library.write_text(LIBRARY, "utf-8")
    namespace: dict[str, Any] = {}
    exec(compile(LIBRARY, str(library), "exec"), namespace)  # noqa: S102 - a planted library module

    namespace["library_swallow"]()

    assert seen == []


def test_event_outside_a_test_is_ignored(
    capture: tuple[MonitoringCapture, list[tuple[TestTag, SwallowedFact]]],
) -> None:
    _, seen = capture
    token = TEST.set(None)
    try:
        _app_swallow()
    finally:
        TEST.reset(token)

    assert seen == []


def test_tool_id_conflict_reports_unattached() -> None:
    claimed = [i for i in TOOL_IDS if sys.monitoring.get_tool(i) is None]
    for tool in claimed:
        sys.monitoring.use_tool_id(tool, "another tool")
    monitor = MonitoringCapture()
    try:
        status = monitor.attach(lambda tag, fact: None)
    finally:
        monitor.detach()
        for tool in claimed:
            sys.monitoring.free_tool_id(tool)

    assert status.attached is False
    assert status.reason == "sys.monitoring tool ids 3 and 4 are in use"


def test_raise_is_not_subscribed(capture: tuple[MonitoringCapture, list[tuple[TestTag, SwallowedFact]]]) -> None:
    monitor, _ = capture
    assert monitor.tool_id is not None

    assert sys.monitoring.get_events(monitor.tool_id) == sys.monitoring.events.EXCEPTION_HANDLED


TOOLS_DURING = """
import sys

def test_records_tools():
    with open("tools.txt", "w") as out:
        out.write(repr([sys.monitoring.get_tool(i) for i in (3, 4)]))
"""


@pytest.mark.parametrize("hook_error", [False, True])
def test_monitoring_tool_freed_at_session_end(pytester: pytest.Pytester, hook_error: bool) -> None:
    before = [sys.monitoring.get_tool(i) for i in TOOL_IDS]
    if None not in before:
        pytest.skip("sys.monitoring tool ids 3 and 4 are both taken by the outer session")
    pytester.makepyfile(test_tools=TOOLS_DURING)
    if hook_error:  # a hook failing after the tests must not leave the tool id claimed
        pytester.makeconftest(
            """
import pytest

@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session):
    raise RuntimeError("a failing session hook")
"""
        )

    pytester.runpytest("--sharpit", "--sharpit-allow-unknown", "--sharpit-no-advisors", "-q", "-p", "no:cacheprovider")

    assert "'sharpit'" in (pytester.path / "tools.txt").read_text("utf-8")  # it was attached while the test ran
    assert [sys.monitoring.get_tool(i) for i in TOOL_IDS] == before
