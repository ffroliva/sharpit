"""Swallowed application exceptions observed with sys.monitoring during a test session (spec 0.4.0 §5.5 F1)."""

from __future__ import annotations

import dis
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from types import CodeType
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


def _handler_offset(source: str, name: str) -> int:
    module = compile(source, "appcode.py", "exec")
    function = next(code for code in module.co_consts if isinstance(code, CodeType) and code.co_name == name)
    return next(
        instruction.offset for instruction in dis.get_instructions(function) if instruction.opname == "PUSH_EXC_INFO"
    )


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
    offset = next(
        instruction.offset
        for instruction in dis.get_instructions(_app_swallow)
        if instruction.opname == "PUSH_EXC_INFO"
    )
    expected_fact = SwallowedFact(location, "JSONDecodeError", False, qualname="_app_swallow")
    object.__setattr__(expected_fact, "offset", offset)
    assert expected_fact.to_json().get("offset") == offset
    assert seen == [(in_test, expected_fact)]


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


@pytest.mark.parametrize("failing", ["register_callback", "set_events"])
def test_partial_attach_failure_releases_tool_id_and_callback(monkeypatch: pytest.MonkeyPatch, failing: str) -> None:
    monitoring = sys.monitoring
    before = [monitoring.get_tool(i) for i in TOOL_IDS]
    tool = next((i for i, name in zip(TOOL_IDS, before, strict=True) if name is None), None)
    if tool is None:
        pytest.skip("sys.monitoring tool ids 3 and 4 are both taken by the outer session")

    def fail(*_args: object) -> None:
        raise RuntimeError(f"{failing} failed")

    monitor = MonitoringCapture()
    with monkeypatch.context() as patch:
        patch.setattr(monitoring, failing, fail)
        with pytest.raises(RuntimeError):
            monitor.attach(lambda tag, fact: None)
    after = [monitoring.get_tool(i) for i in TOOL_IDS]
    if monitoring.get_tool(tool) is None:  # a leaked id is reused for the probe, then freed below
        monitoring.use_tool_id(tool, "probe")
    try:
        callback = monitoring.register_callback(tool, monitoring.events.EXCEPTION_HANDLED, None)
    finally:
        monitoring.free_tool_id(tool)

    assert after == before, "tool id still claimed"
    assert monitor.tool_id is None
    assert callback is None, "callback still registered"


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
def test_monitoring_tool_freed_after_the_session(pytester: pytest.Pytester, hook_error: bool) -> None:
    """Supersedes test_monitoring_tool_freed_at_session_end, whose ``test_tools`` module name collided with
    tests/engine/test_tools.py in an xdist worker (import file mismatch): the probe module name is unique."""
    before = [sys.monitoring.get_tool(i) for i in TOOL_IDS]
    if None not in before:
        pytest.skip("sys.monitoring tool ids 3 and 4 are both taken by the outer session")
    pytester.makepyfile(test_sharpit_swallowed_tool_probe=TOOLS_DURING)
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


# --- Task 4: gate, marker, report-only and baseline ------------------------------------------------------------------


def _bare_project(pytester: pytest.Pytester, marker: str = "") -> None:
    pytester.makepyfile(
        appcode="""
def lookup():
    try:
        return undefined_name  # a NameError
    except:
        return None
""",
        test_bare=f"""
import pytest
from appcode import lookup

{marker}
def test_lookup():
    assert lookup() is None
""",
    )


def test_bare_exception_handler_gates(pytester: pytest.Pytester) -> None:
    _bare_project(pytester)

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert _test_entry(_report(pytester), "test_lookup")["outcome"] == "failed"
    result.stdout.fnmatch_lines(["*sharpit.swallowed-exception: NameError swallowed*appcode.py:4*"])


def test_allow_swallowed_marker_keeps_the_test_passing(pytester: pytest.Pytester) -> None:
    _bare_project(pytester, "@pytest.mark.sharpit(allow_swallowed=True)")

    pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    data = _report(pytester)
    notes = [f for f in data["findings"] if f["ruleId"] == RULE]
    assert _test_entry(data, "test_lookup")["outcome"] == "passed"
    assert [f["severity"] for f in notes] == ["INFO"]


def test_swallowed_respects_report_only_and_baseline(pytester: pytest.Pytester) -> None:
    _bare_project(pytester)
    common = ("--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")

    pytester.runpytest_subprocess(*common, "--sharpit-report-only", "--sharpit-write-baseline=baseline.json")
    reported = _report(pytester)
    pytester.runpytest_subprocess(*common, "--sharpit-baseline=baseline.json")
    baselined = _report(pytester)

    assert _test_entry(reported, "test_lookup")["outcome"] == "passed"
    assert [f["ruleId"] for f in reported["findings"] if f["ruleId"] == RULE] == [RULE]
    assert _test_entry(baselined, "test_lookup")["outcome"] == "passed"
    assert [f["baselineState"] for f in baselined["findings"] if f["ruleId"] == RULE] == ["existing"]


def test_dismissed_swallowed_survives_line_shift_and_distinguishes_functions(pytester: pytest.Pytester) -> None:
    sharpit_dir = pytester.path / ".sharpit"
    sharpit_dir.mkdir()
    app_source = """# Comment line 1
# Comment line 2
def lookup():
    try:
        return undefined_name
    except:
        return None

def other_lookup():
    try:
        return other_undefined
    except:
        return None
"""
    lookup_offset = _handler_offset(app_source, "lookup")
    (sharpit_dir / "sharpit.yml").write_text(
        f"dismissedFindings:\n  - sharpit.swallowed-exception appcode.py:lookup:NameError:{lookup_offset}\n",
        encoding="utf-8",
    )
    pytester.makepyfile(
        appcode=app_source,
        test_bare="""
from appcode import lookup, other_lookup

def test_lookup():
    assert lookup() is None

def test_other_lookup():
    assert other_lookup() is None
""",
    )
    pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    data = _report(pytester)
    assert _test_entry(data, "test_lookup")["outcome"] == "passed"
    assert _test_entry(data, "test_other_lookup")["outcome"] == "failed"
