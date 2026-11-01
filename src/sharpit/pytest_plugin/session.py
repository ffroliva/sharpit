"""Session-level entry points for the pytest plugin."""

from __future__ import annotations

from typing import Any, cast

from sharpit.pytest_plugin.options import PluginOptions, resolve


def resolve_options(config: Any) -> PluginOptions:
    return resolve(config)


def pytest_runtest_makereport(item: Any, call: Any) -> None:
    return None


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
