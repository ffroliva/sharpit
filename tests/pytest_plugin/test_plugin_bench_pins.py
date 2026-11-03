"""Bench twin cases (sharpit-bench-spike upstream tracker U4, U5, U6; findings F3, F4, F5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.needs_sqlalchemy  # the twins are SQLAlchemy apps
pytest.importorskip("sqlalchemy")

TWINS = Path(__file__).parents[1] / "fixtures" / "apps" / "bench_twins"
NO_APP_LINE = "sharpit: no application found; rest-api skipped (pass --sharpit-app module:attr)"


def _twin(pytester: pytest.Pytester, name: str, **tests: str) -> None:
    pytester.makepyfile(**{name: (TWINS / f"{name}.py").read_text("utf-8")}, **tests)


def _report(pytester: pytest.Pytester) -> dict[str, Any]:
    return json.loads((pytester.path / "report.json").read_text("utf-8"))


def _rest_api(data: dict[str, Any]) -> dict[str, Any]:
    return next(run for run in data["advisors"] if run["advisor"] == "rest-api")


def test_bench_clean_app_without_sharpit_app_is_green(pytester: pytest.Pytester) -> None:
    # bench: F3 / U4, the README's `pytest --sharpit` on the clean base (test_crud.py drives the data layer)
    pytester.makepyfile(clean_main=(TWINS / "clean_main.py").read_text("utf-8"))
    _twin(
        pytester,
        "clean_app",
        test_crud="""
from sqlalchemy.orm import Session
from clean_app import engine, get_performances, get_players

def test_players():
    with Session(engine) as db:
        players = get_players(db, limit=10)
        assert [len(p.performances) for p in players] == [1] * 10

def test_performances():
    with Session(engine) as db:
        assert len(get_performances(db, limit=5)) == 5
""",
    )

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

    assert result.ret == 0
    assert NO_APP_LINE in result.stdout.str()
    assert _rest_api(_report(pytester))["status"] == "SKIPPED"


def _noisy_run(pytester: pytest.Pytester, *extra: str) -> tuple[str, dict[str, Any]]:
    _twin(pytester, "noisy_app", test_noisy="def test_ok():\n    pass")
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-app=noisy_app:app", "--sharpit-report=report.json", "-q", *extra
    )
    assert result.ret == 0
    return result.stdout.str(), _report(pytester)


def test_bench_advisor_notes_hidden_by_default(pytester: pytest.Pytester) -> None:
    # bench: F4 / U5, eight non-failing advisor notes printed above the result
    stdout, data = _noisy_run(pytester)

    notes = [f for f in data["findings"] if f["advisor"] == "rest-api"]
    assert len(notes) >= 2
    assert f"sharpit: {len(notes)} advisor notes in report.json" in stdout
    assert "  RAPI-" not in stdout


def test_bench_advisor_notes_with_verbose(pytester: pytest.Pytester) -> None:
    # bench: F4 / U5, the notes stay one flag away
    stdout, data = _noisy_run(pytester, "--sharpit-verbose")

    rules = {f["ruleId"] for f in data["findings"] if f["advisor"] == "rest-api"}
    assert rules
    assert all(f"  {rule}: " in stdout for rule in rules)
    assert "advisor notes in" not in stdout
