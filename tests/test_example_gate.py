"""The example app's CI gate: a planted N+1 goes red under `pytest --sharpit`, the fixed route goes green."""

from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET  # noqa: S405 - parses the report this test just wrote
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.needs_sqlalchemy

pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "examples" / "fastapi_sqla" / "tests_gate"


def _run(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, *args: str) -> pytest.RunResult:
    shutil.copytree(GATE, pytester.path / "tests_gate", dirs_exist_ok=True)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))  # the copy imports examples.fastapi_sqla from the repo
    return pytester.runpytest_subprocess("tests_gate", "--sharpit", "-q", "-p", "no:cacheprovider", *args)


def _report(pytester: pytest.Pytester) -> dict[str, Any]:
    return json.loads((pytester.path / "sharpit-report.json").read_text())


def test_planted_n_plus_one_goes_red_then_green(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    red = _run(pytester, monkeypatch, "-k", "n_plus_one", "--sharpit-junit=j.xml")
    red_report = _report(pytester)
    assert red.ret == 1
    assert red_report["status"] == "fail"
    gate_findings = [f for f in red_report["findings"] if f["ruleId"].startswith("sharpit.")]
    assert [f["ruleId"] for f in gate_findings] == ["sharpit.n-plus-one"]
    assert gate_findings[0]["testNodeId"].endswith("::test_owners_list_n_plus_one")
    assert "FROM pets WHERE owner_id" in gate_findings[0]["target"]
    junit_failures = ET.parse(pytester.path / "j.xml").getroot().iterfind(".//failure")
    assert "sharpit.n-plus-one" in {f.get("type") for f in junit_failures}

    green = _run(pytester, monkeypatch, "-k", "fixed")
    green_report = _report(pytester)
    assert green.ret == 0
    assert green_report["status"] == "pass"


def test_ci_runs_the_gate_job() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "sharpit-gate:" in ci
    assert "-k fixed --sharpit --sharpit-junit=sharpit-junit.xml" in ci
    assert '"! uv run --no-sync pytest examples/fastapi_sqla/tests_gate -k n_plus_one --sharpit' in ci
