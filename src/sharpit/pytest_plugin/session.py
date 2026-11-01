"""Session-level entry points for the pytest plugin."""

from __future__ import annotations

from typing import Any, cast

import pytest

try:
    from pluggy import Result
except ImportError:  # pluggy before the public re-export
    from pluggy._result import Result

from sharpit.pytest_plugin.options import PluginOptions, resolve


def resolve_options(config: Any) -> PluginOptions:
    return resolve(config)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    from sharpit import pytest_plugin

    plugin = cast(Any, pytest_plugin)
    outcome_result = cast(Result[Any], (yield))
    state = plugin._state(item.config)
    report_obj = outcome_result.get_result()
    if state is None:
        return
    try:
        test = state.sink.current_test
        if test is None:
            return
        if report_obj.when != "call":
            if report_obj.skipped:
                test.outcome = "skipped"
            elif report_obj.failed:
                test.outcome = "error"
            return
        test.outcome = report_obj.outcome
        budget = plugin.budget_for(item, state.options.max_queries)
        test.budget = budget
        findings = plugin.gates.evaluate_test(
            test, budget, state.settings.activity_n_plus_one_threshold, state.dismissed
        )
        test.findings = [finding.to_dto() for finding in findings]
        messages = [f"sharpit: {finding.rule_id}: {finding.message}" for finding in findings if not finding.dismissed]
        if messages:
            report_obj.longrepr = f"{report_obj.longrepr}\n" if report_obj.failed else ""
            report_obj.longrepr = f"{report_obj.longrepr}{'\n'.join(messages)}"
            report_obj.outcome = "failed"
            test.outcome = "failed"
    except Exception as exc:  # noqa: BLE001
        plugin._record_hook_failure(state.sink, exc)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    from sharpit import pytest_plugin

    plugin = cast(Any, pytest_plugin)
    state = None
    try:
        state = plugin._state(session.config)
    except Exception as exc:  # noqa: BLE001
        fallback = plugin._active_state
        if fallback is not None:
            plugin._record_hook_failure(fallback.sink, exc)
        return
    if state is None:
        return
    if hasattr(session.config, "workerinput"):
        try:
            plugin._final_facts(state)
        except Exception as exc:  # noqa: BLE001
            plugin._record_hook_failure(state.sink, exc)
        plugin._advisors(state)
        try:
            session.config.workeroutput["sharpit"] = state.sink.facts.to_json()
        except Exception as exc:  # noqa: BLE001
            plugin._record_hook_failure(state.sink, exc)
        return
    plugin._write_report(state, session, exitstatus)
