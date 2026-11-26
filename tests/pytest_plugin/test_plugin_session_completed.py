from __future__ import annotations

from types import SimpleNamespace

from engine.testsession.tsfakes import NODE
from sharpit.engine.testsession.facts import TestFacts, TestKey
from sharpit.pytest_plugin.session import record_call_completion, record_other_phase


def _test() -> TestFacts:
    return TestFacts(TestKey(NODE, "gw0", 1))


def _report(*, when: str = "call", passed: bool = True, failed: bool = False, skipped: bool = False) -> SimpleNamespace:
    return SimpleNamespace(when=when, passed=passed, failed=failed, skipped=skipped)


def test_a_failing_report_keeps_completed_false() -> None:
    test = _test()
    for passed in (True, False, True):  # pytest sends one call report per subtest
        record_call_completion(test, _report(passed=passed, failed=not passed))
    assert test.completed is False


def test_setup_report_resets_completed() -> None:
    test = _test()
    test.completed = False
    record_other_phase(test, _report(when="setup"))
    record_call_completion(test, _report())
    assert test.completed is True


def test_completed_is_read_before_a_gate_fails_the_test() -> None:
    test = _test()
    record_call_completion(test, _report())
    test.outcome = "failed"  # a sharpit gate rewrites the outcome after the call report is read
    assert test.completed is True
