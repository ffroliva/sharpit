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


def _query_loop_finding(pytester: pytest.Pytester, call: str, site: str) -> tuple[str, int]:
    _twin(
        pytester,
        "query_loop_app",
        test_loop=f"""
from sqlalchemy.orm import Session
from query_loop_app import engine, get_performances, get_points

def test_loop():
    with Session(engine) as db:
        assert len({call}(db, list(range(1, 31)))) == 30
""",
    )
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 1
    finding = next(f for f in _report(pytester)["findings"] if f["ruleId"] == "sharpit.n-plus-one")
    source = (TWINS / "query_loop_app.py").read_text("utf-8").splitlines()
    return finding["message"], next(n for n, text in enumerate(source, 1) if site in text)


def test_n_plus_one_without_relationship_names_location_and_fix(pytester: pytest.Pytester) -> None:
    # bench: F5 / U6 gap, T3 performances query loop (`db.get` per id, no relationship)
    message, line = _query_loop_finding(pytester, "get_performances", "db.get(")

    assert message.startswith("30 executions of one SELECT in the call phase")
    assert f"query_loop_app.py:{line}" in message
    assert "select(Performance).where(Performance.performance_id.in_(ids))" in message


def test_n_plus_one_without_entity_names_location_and_generic_fix(pytester: pytest.Pytester) -> None:
    # a textual SELECT per id: the site is known, the entity is not, so the fix stays generic
    message, line = _query_loop_finding(pytester, "get_points", "db.execute(")

    assert f"query_loop_app.py:{line}" in message
    assert "WHERE ... IN (...)" in message


SERIALIZE_TEST = """
from fastapi.testclient import TestClient
from serialize_app import app

def test_players():
    assert len(TestClient(app).get("/v0/players/").json()) == 10
"""


def test_lazy_load_n_plus_one_names_the_first_app_frame(pytester: pytest.Pytester) -> None:
    # bench: U6, D01/D02/D04-D06 printed "first lazy load at unknown": the loads run in response serialization
    pytest.importorskip("fastapi")
    _twin(pytester, "serialize_app", test_players=SERIALIZE_TEST)
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    finding = next(f for f in _report(pytester)["findings"] if f["ruleId"] == "sharpit.n-plus-one")
    source = (TWINS / "serialize_app.py").read_text("utf-8").splitlines()
    line = next(n for n, text in enumerate(source, 1) if text.endswith("# twin: declared"))

    assert result.ret == 1
    assert finding["message"].startswith("Player.performances lazy-loaded 10 times")
    assert f"serialize_app.py:{line}" in finding["message"]
