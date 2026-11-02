"""F1 monitoring budget: what the EXCEPTION_HANDLED callback adds per handled exception; see overhead-budgets.md."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest
from tests.overhead import check_budget, paired

from sharpit.engine.capture.correlation import TEST
from sharpit.engine.testsession.facts import SwallowedFact
from sharpit.pytest_plugin.swallowed import MonitoringCapture, TestTag

HANDLED = 1_000  # loops; each one handles three exceptions
ROUNDS = 15
SWALLOWED_HANDLER_BUDGET = 1.5e-6  # measured 0.40-0.86 us/exception, noise <= 0.40 (10 runs, 2026-11-02)

LIBRARY = """
def library_handles():
    try:
        return {}["missing"]
    except KeyError:
        return 1
"""


def _app_narrow() -> int:
    try:
        return {}["missing"]
    except KeyError:
        return 1


def _app_swallow() -> int:
    try:
        return int("not a number")
    except Exception:
        return 0


def _library(tmp_path: Path) -> Callable[[], int]:
    path = tmp_path / "site-packages" / "budget_library.py"
    path.parent.mkdir()
    path.write_text(LIBRARY, "utf-8")
    namespace: dict[str, Callable[[], int]] = {}
    exec(compile(LIBRARY, str(path), "exec"), namespace)  # noqa: S102 - a planted library module
    return namespace["library_handles"]


def test_swallowed_monitoring_overhead_budget(tmp_path: Path) -> None:
    library = _library(tmp_path)
    tag: TestTag = ("tests/test_budget.py::test_budget", 1, "call")

    def workload(monitored: bool) -> float:
        events: list[SwallowedFact] = []
        capture = MonitoringCapture()
        if monitored and not capture.attach(lambda _tag, fact: events.append(fact)).attached:
            pytest.skip("sys.monitoring tool ids 3 and 4 are in use by an outer session")
        token = TEST.set(tag)
        try:
            start = time.perf_counter()
            total = sum(_app_narrow() + _app_swallow() + library() for _ in range(HANDLED))
            elapsed = time.perf_counter() - start
        finally:
            TEST.reset(token)
            capture.detach()
        assert total == 2 * HANDLED  # the host's results are unchanged
        assert len(events) == (HANDLED if monitored else 0)  # one event per swallow, none for the others
        return elapsed / (3 * HANDLED)

    result = paired(lambda: workload(False), lambda: workload(True), ROUNDS)

    check_budget("swallowed-exception monitoring", result, SWALLOWED_HANDLER_BUDGET, "us/exception", 1e-6)
