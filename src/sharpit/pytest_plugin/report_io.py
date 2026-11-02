"""Session report serialization and exit-status calculation."""

from __future__ import annotations

import hashlib
import time
from typing import Any, cast

import pytest

from sharpit import __version__
from sharpit.engine.testsession import baseline as baseline_io
from sharpit.engine.testsession import outcome, report
from sharpit.engine.testsession.facts import finding_from
from sharpit.engine.testsession.finish import GateOptions, finish


def write_report(state: Any, session: Any, exitstatus: int) -> None:
    from sharpit import pytest_plugin

    plugin = cast(Any, pytest_plugin)
    sink = state.sink
    try:
        facts = plugin._final_facts(state)  # forced app snapshot precedes advisor assessment
        parts = _report_parts(plugin, session, state, facts)
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
                state.options.report_only,
            ),
            version=__version__,
            now_ms=time.time_ns() // 1_000_000,
            warnings=sink.facts.warnings,
        )
        _apply_baseline(state, data)
        refusal = _baseline_refusal(state, data)
        report.write_json(state.options.report, data)
        if state.options.junit:
            report.write_junit(state.options.junit, data, allow_unknown=state.options.allow_unknown)
        if refusal:
            raise pytest.UsageError(refusal)
        _write_baseline(state, data)
        if exitstatus == 0 and outcome.exit_fails(
            status,
            state.options.allow_unknown,
            report_only=state.options.report_only,
            unknown_reasons=data["unknownReasons"],
        ):
            session.exitstatus = 1
        session._sharpit_report = data
        session.config._sharpit_report = data
    except pytest.UsageError:
        raise
    except Exception as exc:  # noqa: BLE001
        plugin._record_hook_failure(sink, exc)
        if exitstatus == 0:
            session.exitstatus = 1


def _report_parts(plugin: Any, session: Any, state: Any, facts: Any) -> list[Any]:
    if plugin._xdist_controller(session.config, state):
        return state.parts
    plugin._advisors(state)
    return [facts]


def _apply_baseline(state: Any, data: dict[str, Any]) -> None:
    if state.baseline_data is None:
        return
    comparison = baseline_io.compare(
        [finding_from(finding) for finding in data["findings"]], state.baseline_data, partial=state.partial
    )
    by_fingerprint = {finding.fingerprint: finding for finding in comparison.findings}
    data["findings"] = [
        {**finding, "baselineState": by_fingerprint[finding["fingerprint"]].baseline_state}
        for finding in data["findings"]
    ]
    for advisor in data["advisors"]:
        advisor["findings"] = [
            {**finding, "baselineState": by_fingerprint[finding["fingerprint"]].baseline_state}
            for finding in advisor["findings"]
        ]
    data["baseline"] = {
        "path": str(state.options.baseline),
        "sha256": hashlib.sha256(state.baseline_data.raw).hexdigest(),
        "existing": sum(f.baseline_state == "existing" for f in comparison.findings),
        "new": sum(f.baseline_state == "new" for f in comparison.findings),
        "fixed": None if comparison.fixed is None else len(comparison.fixed),
        "fixedReason": comparison.fixed_reason,
    }


def _baseline_refusal(state: Any, data: dict[str, Any]) -> str | None:
    if not state.options.write_baseline:
        return None
    if state.partial:
        return "sharpit: refusing to write baseline: partial run"
    if data["unknownReasons"]:
        return "sharpit: refusing to write baseline: unknown reasons are present"
    return None


def _write_baseline(state: Any, data: dict[str, Any]) -> None:
    if state.options.write_baseline:
        baseline_io.write(state.options.write_baseline, [finding_from(finding) for finding in data["findings"]])
