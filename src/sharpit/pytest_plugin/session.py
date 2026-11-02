"""Session-level entry points for the pytest plugin."""

from __future__ import annotations

from typing import Any, cast

import pytest

try:
    from pluggy import Result
except ImportError:  # pluggy before the public re-export
    from pluggy._result import Result

from sharpit.pytest_plugin.apps import TEST_FILES, reconcile_workers

WORKER_APPS = "sharpit-worker-apps"
APPS_KEY = "sharpit_apps"  # workeroutput: {"names": candidates or None, "snapshot": an installed app was assessed}


def register_worker_apps(config: Any) -> None:
    """Hook WorkerApps into this process once (options.resolve runs it from the facade's pytest_configure)."""
    manager = getattr(config, "pluginmanager", None)
    if manager is not None and not manager.has_plugin(WORKER_APPS):
        manager.register(WorkerApps(), WORKER_APPS)


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
    state.test_files = _test_files(session.config)
    if hasattr(session.config, "workerinput"):
        try:
            plugin._final_facts(state)
        except Exception as exc:  # noqa: BLE001
            plugin._record_hook_failure(state.sink, exc)
        plugin._advisors(state)
        try:
            session.config.workeroutput["sharpit"] = state.sink.facts.to_json()
            names = getattr(state, "autodetected", None)
            snapshot = names is None and state.options.advisors and not state.options.app
            session.config.workeroutput[APPS_KEY] = {"names": names, "snapshot": snapshot}
        except Exception as exc:  # noqa: BLE001
            plugin._record_hook_failure(state.sink, exc)
        return
    names = getattr(state, "autodetected", None)
    if names is not None and state.parts:
        snapshot = getattr(state, "autodetect_snapshot", False)
        try:
            reconcile_workers(state.parts, names, state.options.require_app, snapshot)
        except Exception as exc:  # noqa: BLE001
            plugin._record_hook_failure(state.sink, exc)
        if snapshot:  # an installed app was assessed: autodetect did not decide anything
            state.autodetected = None
    plugin._write_report(state, session, exitstatus)


def _test_files(config: Any) -> tuple[str, ...]:
    try:
        return tuple(config.getini("python_files")) or TEST_FILES
    except (ValueError, KeyError):
        return TEST_FILES


class WorkerApps:
    """Controller-side xdist hook: unions the workers' autodetect candidates (registered by register_worker_apps)."""

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node: Any, error: Any) -> None:
        from sharpit import pytest_plugin

        state = cast(Any, pytest_plugin)._state(node.config)
        shipped = getattr(node, "workeroutput", {}).get(APPS_KEY)
        if state is None or error is not None or not isinstance(shipped, dict):
            return
        if cast("dict[str, Any]", shipped).get("snapshot"):
            state.autodetect_snapshot = True
        if (names := cast("dict[str, Any]", shipped).get("names")) is not None:
            state.autodetected = sorted({*(getattr(state, "autodetected", None) or []), *names})
