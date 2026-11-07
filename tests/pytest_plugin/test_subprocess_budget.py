from __future__ import annotations

import ast
from pathlib import Path

_BUDGETS = {
    "test_plugin_bad_baseline.py": 0,
    "test_plugin_apps.py": 1,
    "test_plugin_baseline.py": 9,
    "test_plugin_gate_defaults.py": 9,
    "test_plugin_gates.py": 11,
    "test_plugin_identity.py": 6,
    "test_plugin_inert.py": 3,
    "test_plugin_report_only.py": 0,
    "test_plugin_reports.py": 1,
    "test_plugin_swallowed.py": 5,
    "test_plugin_terminal.py": 0,
    "test_plugin_xdist.py": 11,
}


def test_pytester_subprocess_calls_stay_within_file_budgets() -> None:
    directory = Path(__file__).parent
    for filename, budget in _BUDGETS.items():
        tree = ast.parse((directory / filename).read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "runpytest_subprocess"
        ]
        assert len(calls) <= budget, f"{filename} has {len(calls)} subprocess pytest runs; budget is {budget}"
