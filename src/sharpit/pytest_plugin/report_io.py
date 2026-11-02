"""Session report serialization and exit-status calculation."""

from __future__ import annotations

import time
from typing import Any, cast

from sharpit import __version__
from sharpit.engine.testsession import outcome, report
from sharpit.engine.testsession.finish import GateOptions, finish


def write_report(state: Any, session: Any, exitstatus: int) -> None:
    from sharpit import pytest_plugin

    plugin = cast(Any, pytest_plugin)
    sink = state.sink
    try:
        facts = plugin._final_facts(state)  # forced app snapshot precedes advisor assessment
        if not plugin._xdist_controller(session.config, state):
            plugin._advisors(state)
        parts = state.parts if plugin._xdist_controller(session.config, state) else [facts]
        data, status, _reasons = finish(
            parts,
            state.missing_workers,
            options=GateOptions(
                state.options.max_queries,
                state.settings.activity_n_plus_one_threshold,
                state.options.fail_on,
                state.options.allow_unknown,
                state.options.max_unattributed,
                state.options.advisors,
            ),
            version=__version__,
            now_ms=time.time_ns() // 1_000_000,
            warnings=sink.facts.warnings,
        )
        report.write_json(state.options.report, data)
        if state.options.junit:
            report.write_junit(state.options.junit, data, allow_unknown=state.options.allow_unknown)
        if exitstatus == 0 and outcome.exit_fails(status, state.options.allow_unknown):
            session.exitstatus = 1
        session._sharpit_report = data
        session.config._sharpit_report = data
    except Exception as exc:  # noqa: BLE001
        plugin._record_hook_failure(sink, exc)
        if exitstatus == 0:
            session.exitstatus = 1
