"""The benchmark's swallowed-error cases (U1, U2, U17, U19) as Python twins under ``pytest --sharpit`` (§7.2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE = Path(__file__).parents[1] / "fixtures" / "apps" / "swallow_twins"
RULE = "sharpit.swallowed-exception"
APP = (FIXTURE / "twinapp.py").read_text("utf-8")


def _handler_line(twin: str) -> int:
    return next(n for n, line in enumerate(APP.splitlines(), 1) if line.endswith(f"# twin: {twin}"))


def _run(pytester: pytest.Pytester, test: str) -> list[dict[str, Any]]:
    """Run one twin test under --sharpit; the swallowed-exception findings it produced."""
    library = pytester.mkdir("site-packages")  # the library frame is not application code
    (library / "twinlib.py").write_text((FIXTURE / "twinlib.py").read_text("utf-8"), "utf-8")
    pytester.makepyfile(twinapp=APP, test_twins=(FIXTURE / "cases.py").read_text("utf-8"))
    pytester.makeini("[pytest]\npythonpath = site-packages\n")
    pytester.runpytest_subprocess(
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "-q",
        "-p",
        "no:cacheprovider",
        "-k",
        test,
    )
    data = json.loads((pytester.path / "report.json").read_text("utf-8"))
    return [f for f in data["findings"] if f["ruleId"] == RULE and f["testNodeId"].endswith(f"::{test}")]


def test_library_warn_does_not_hide_app_swallow(pytester: pytest.Pytester) -> None:
    found = _run(pytester, "test_order_count")

    targets = [f["target"] for f in found]
    assert targets == [f"twinapp.py:{_handler_line('order_count')}"]


def test_swallow_in_loop_is_one_finding(pytester: pytest.Pytester) -> None:
    found = _run(pytester, "test_total_price")  # 200 iterations, each swallowing an AttributeError

    targets = [f["target"] for f in found]
    assert targets == [f"twinapp.py:{_handler_line('total_price')}"]


def test_db_error_swallow_found(pytester: pytest.Pytester) -> None:
    found = _run(pytester, "test_find_user")

    targets = [f["target"] for f in found]
    assert targets == [f"twinapp.py:{_handler_line('find_user')}"]
    assert "OperationalError swallowed" in found[0]["message"]


def test_logged_handler_is_not_a_finding(pytester: pytest.Pytester) -> None:
    found = _run(pytester, "test_logged_order_count")

    assert found == []
