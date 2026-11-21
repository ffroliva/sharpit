"""Swallowed application exceptions observed with sys.monitoring during a test session (spec 0.4.0 §5.5 F1)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from sharpit.engine.capture.correlation import TEST
from sharpit.engine.testsession.facts import SwallowedFact
from sharpit.engine.testsession.swallowed import site_identity, swallowing_sites
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


def test_validation_errors_never_enter_the_test_session_sink() -> None:
    # approved A4a condition: a user's expected FastAPI 422 is not a test-session exception finding
    from fastapi.exceptions import RequestValidationError

    from sharpit.pytest_plugin import _ExceptionHandler

    class Sink:
        def on_exception(self, *_args: object) -> None:
            raise AssertionError("RequestValidationError reached the test-session sink")

    error = RequestValidationError(
        [{"type": "value_error", "loc": ("body",), "msg": "invalid ordinary-secret-91", "input": "ordinary-secret-91"}]
    )
    record = logging.LogRecord("app", logging.ERROR, "f", 1, "failed", (), (type(error), error, None))
    _ExceptionHandler(Sink()).emit(record)  # type: ignore[arg-type]


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


def _record(*doubles: bool) -> list[bool]:
    from types import SimpleNamespace

    from sharpit.engine.testsession.facts import TestFacts, TestKey
    from sharpit.pytest_plugin.swallowed import record

    current = TestFacts(TestKey("t::a", "w", 1))
    sink = SimpleNamespace(current_test=current)
    for double in doubles:
        record(sink, ("t::a", 1, "call"), SwallowedFact("a.py:3", "TypeError", True, test_double=double))
    return [fact.test_double for fact in current.phases["call"].swallowed]


def test_one_real_raise_among_the_doubles_clears_the_note() -> None:
    assert _record(True, False, True) == [False]
    assert _record(False, True) == [False]


def test_monitoring_capture_classifies_double_and_resets_per_test(monkeypatch: pytest.MonkeyPatch) -> None:
    from sharpit.engine.testsession.facts import SwallowedFact
    from sharpit.pytest_plugin import swallowed

    fact = SwallowedFact("app.py:4", "ValueError", True)
    monkeypatch.setattr(swallowed, "_fact", lambda *_args: fact)
    monitor = MonitoringCapture()
    seen: list[tuple[TestTag, SwallowedFact]] = []
    monitor._sink = lambda tag, item: seen.append((tag, item))
    code = _app_swallow.__code__
    first: TestTag = ("tests/test_x.py::test_first", 1, "call")
    token = TEST.set(first)
    try:
        mock = Mock(side_effect=ValueError("raised by a mock"))
        with pytest.raises(ValueError) as raised:
            mock()
        monitor._handled(code, 0, raised.value)
        assert seen[-1][1].test_double is True

        ordinary = ValueError("application error")
        monitor._handled(code, 0, ordinary)
        assert seen[-1][1].test_double is False
        monitor._handled(code, 0, ordinary)
        assert len(seen) == 3

        second: TestTag = ("tests/test_x.py::test_second", 1, "call")
        second_token = TEST.set(second)
        try:
            with pytest.raises(ValueError) as raised_again:
                mock()
            monitor._handled(code, 0, raised_again.value)
        finally:
            TEST.reset(second_token)
        assert seen[-1][0] == second
        assert seen[-1][1].test_double is True
    finally:
        TEST.reset(token)


def test_only_doubles_keep_the_note_once() -> None:
    assert _record(True, True) == [True]


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

    path = Path(os.path.relpath(__file__)).as_posix()
    [site] = [s for s in swallowing_sites(Path(__file__).read_text("utf-8")) if s.scope == "_app_swallow"]
    identity = site_identity(path, site, "JSONDecodeError")
    location = f"{path}:{_app_swallow_line()}"
    assert seen == [(in_test, SwallowedFact(location, "JSONDecodeError", False, identity, location))]


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


# --- #66: a dismissal keys on the clause's scope and content, not its line ---------------------------------------


def _week_identity() -> str:
    [site] = swallowing_sites((FIXTURE / "weekapp.py").read_text("utf-8"))
    return site_identity("weekapp.py", site, "AttributeError")


WEEK_IDENTITY = _week_identity()
WEEK_LEGACY = "weekapp.py:21:AttributeError"  # the ``except Exception:`` line of the fixture
WEEK_ARGS = ("--sharpit", "--sharpit-app=weekapp:app", "--sharpit-report=report.json", "-q")


def _planted(data: dict[str, Any]) -> dict[str, Any]:
    found = next(
        (f for f in data["findings"] if f["ruleId"] == RULE and f["testNodeId"].endswith("::test_week_count")), None
    )
    assert found is not None, f"no {RULE} finding for test_week_count: {[f['ruleId'] for f in data['findings']]}"
    return found


def _dismiss(pytester: pytest.Pytester, *entries: str) -> None:
    state_dir = pytester.path / ".sharpit"
    state_dir.mkdir(exist_ok=True)
    lines = "".join(f"  - {RULE} {entry}\n" for entry in entries)
    (state_dir / "sharpit.yml").write_text(f"dismissedFindings:\n{lines}", encoding="utf-8")


def _add_line_above(pytester: pytest.Pytester) -> None:
    weekapp = pytester.path / "weekapp.py"
    weekapp.write_text("# a line added above every handler\n" + weekapp.read_text("utf-8"), encoding="utf-8")


def test_the_identity_is_the_same_serially_and_under_xdist(pytester: pytest.Pytester) -> None:
    _week_project(pytester)

    pytester.runpytest(*WEEK_ARGS)
    serial = _planted(_report(pytester))
    pytester.runpytest("-n", "2", *WEEK_ARGS)
    parallel = _planted(_report(pytester))

    assert re.fullmatch(r"weekapp\.py:get_week_count:AttributeError#[0-9a-f]{8}", WEEK_IDENTITY)
    assert serial["message"].endswith(f"; identity {WEEK_IDENTITY}")
    assert parallel["message"] == serial["message"]
    assert parallel["fingerprint"] == serial["fingerprint"]


def test_a_dismissal_survives_a_line_added_above_the_handler(pytester: pytest.Pytester) -> None:
    _week_project(pytester)
    _add_line_above(pytester)
    _dismiss(pytester, WEEK_IDENTITY)

    result = pytester.runpytest("-n", "2", *WEEK_ARGS)

    assert _planted(_report(pytester))["dismissed"] is True
    assert result.ret == 0, result.stdout.str()


def test_a_legacy_line_keyed_entry_no_longer_dismisses_and_the_report_names_its_new_key(
    pytester: pytest.Pytester,
) -> None:
    _week_project(pytester)
    _dismiss(pytester, WEEK_LEGACY)

    result = pytester.runpytest("-n", "2", *WEEK_ARGS)

    data = _report(pytester)
    assert _planted(data)["dismissed"] is False
    assert result.ret == 1, result.stdout.str()
    assert [w for w in data["warnings"] if WEEK_LEGACY in w and WEEK_IDENTITY in w]
