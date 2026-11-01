"""Session-level entry points for the pytest plugin."""

from __future__ import annotations

from typing import Any

from sharpit.pytest_plugin.options import PluginOptions, resolve


def resolve_options(config: Any) -> PluginOptions:
    return resolve(config)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    from sharpit import pytest_plugin

    state = None
    try:
        state = pytest_plugin._state(session.config)
    except Exception as exc:  # noqa: BLE001
        fallback = pytest_plugin._active_state
        if fallback is not None:
            pytest_plugin._record_hook_failure(fallback.sink, exc)
        return
    if state is None:
        return
    if hasattr(session.config, "workerinput"):
        try:
            pytest_plugin._final_facts(state)
        except Exception as exc:  # noqa: BLE001
            pytest_plugin._record_hook_failure(state.sink, exc)
        pytest_plugin._advisors(state)
        try:
            session.config.workeroutput["sharpit"] = state.sink.facts.to_json()
        except Exception as exc:  # noqa: BLE001
            pytest_plugin._record_hook_failure(state.sink, exc)
        return
    pytest_plugin._write_report(state, session, exitstatus)
