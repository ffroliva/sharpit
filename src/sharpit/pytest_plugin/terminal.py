"""Terminal summary rendering for pytest sessions."""

from __future__ import annotations

from typing import Any, cast

from sharpit.engine.testsession.report import TEST_RUNTIME, finding_fails
from sharpit.pytest_plugin.apps import AUTODETECT, skip_reason


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:
    from sharpit import pytest_plugin

    plugin = cast(Any, pytest_plugin)
    del exitstatus
    data = getattr(config, "_sharpit_report", None)
    if data is None:
        return
    state = plugin._state(config)
    if state is None:
        return
    try:
        terminalreporter.write_sep("=", f"sharpit: {data['status']}")
        if (notice := app_notice(getattr(state, "autodetected", None), state.options.require_app, data)) is not None:
            terminalreporter.write_line(notice)
        _write_summary(terminalreporter, config, state, plugin, data)
    except Exception as exc:  # noqa: BLE001
        plugin._record_hook_failure(state.sink, exc)
        plugin._refresh_report_after_hook_failure(state, config, exc)


def _write_summary(terminalreporter: Any, config: Any, state: Any, plugin: Any, data: dict[str, Any]) -> None:
    terminalreporter.write_line(f"status: {data['status']}")
    terminalreporter.write_line(f"tests with findings: {sum(1 for test in data['tests'] if test['findings'])}")
    fail_on = data["gates"]["failOnSeverity"]
    failing = [f for f in data["findings"] if finding_fails(f, fail_on)]
    would_fail = _would_fail(data, fail_on) if state.options.report_only else None
    notes = [f for f in data["findings"] if f["advisor"] != TEST_RUNTIME and not finding_fails(f, fail_on)]
    shown = data["findings"] if state.options.verbose else failing
    counts = plugin.Counter(finding["ruleId"] for finding in shown)  # facade seam: monkeypatchable
    terminalreporter.write_line("gate counts:")
    for rule, count in sorted(counts.items()):
        terminalreporter.write_line(f"  {rule}: {count}")
    terminalreporter.write_line("worst tests:")
    worst = sorted(
        (test for test in data["tests"] if test["findings"]),
        key=lambda test: (-len(test["findings"]), test["nodeId"]),
    )[:5]
    for test in worst:
        terminalreporter.write_line(f"  {test['nodeId']}: {len(test['findings'])} finding(s)")
    if not worst:
        terminalreporter.write_line("  (none)")
    path = config.option.sharpit_report or config.getini("sharpit_report")
    terminalreporter.write_line(f"report: {path}")
    if notes and not state.options.verbose:
        terminalreporter.write_line(f"sharpit: {len(notes)} advisor notes in {path}")
    for warning in data["warnings"]:
        terminalreporter.write_line(f"warning: {warning}")
    if would_fail is not None:
        terminalreporter.write_line(f"sharpit report-only: {would_fail} tests would fail, status {data['status']}")


def _would_fail(data: dict[str, Any], fail_on: str) -> int:
    findings = {finding["fingerprint"]: finding for finding in data["findings"]}
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for test in data["tests"]:
        key = (test["nodeId"], test["worker"])
        if key not in latest or test["attempt"] >= latest[key]["attempt"]:
            latest[key] = test
    return sum(
        any(
            finding_fails(findings[fingerprint], fail_on) for fingerprint in test["findings"] if fingerprint in findings
        )
        for test in latest.values()
    )


def app_notice(names: list[str] | None, require_app: bool, data: dict[str, Any]) -> str | None:
    """The autodetect line; None when autodetect did not decide (explicit app, installed app, advisors off)."""
    if names is None or (not names and require_app):
        return None
    if len(names) != 1:
        return f"sharpit: {skip_reason(names)}"
    apps: list[dict[str, Any]] = [app for a in data["advisors"] if a["advisor"] == "rest-api" for app in a["apps"]]
    if any(app["evidence"].get(AUTODETECT) is True for app in apps):
        return f"sharpit: {skip_reason((), bare=names[0])}"
    return f"sharpit: using app {names[0]} (pass --sharpit-app to choose)"
