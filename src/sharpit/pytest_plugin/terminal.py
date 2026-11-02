"""Terminal summary rendering for pytest sessions."""

from __future__ import annotations

from typing import Any, cast

from sharpit.pytest_plugin.apps import NO_APP_REASON


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
        if (notice := app_notice(getattr(state, "autodetected", None), False)) is not None:
            terminalreporter.write_line(notice)
        terminalreporter.write_line(f"status: {data['status']}")
        terminalreporter.write_line(f"tests with findings: {sum(1 for test in data['tests'] if test['findings'])}")
        counts = plugin.Counter(finding["ruleId"] for finding in data["findings"])  # facade seam: monkeypatchable
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
        terminalreporter.write_line(f"report: {config.option.sharpit_report or config.getini('sharpit_report')}")
        for warning in data["warnings"]:
            terminalreporter.write_line(f"warning: {warning}")
    except Exception as exc:  # noqa: BLE001
        plugin._record_hook_failure(state.sink, exc)
        plugin._refresh_report_after_hook_failure(state, config, exc)


def app_notice(names: list[str] | None, require_app: bool) -> str | None:
    """The autodetect line; None when autodetect did not run."""
    if names is None:
        return None
    if len(names) == 1:
        return f"sharpit: using app {names[0]} (pass --sharpit-app to choose)"
    if names:
        return f"sharpit: several apps found ({', '.join(names)}); pass --sharpit-app module:attr"
    return None if require_app else f"sharpit: {NO_APP_REASON}"
