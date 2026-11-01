"""Terminal summary rendering for pytest sessions."""

from __future__ import annotations

from collections import Counter
from typing import Any, cast


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
        terminalreporter.write_line(f"status: {data['status']}")
        terminalreporter.write_line(f"tests with findings: {sum(1 for test in data['tests'] if test['findings'])}")
        counts = Counter(finding["ruleId"] for finding in data["findings"])
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
