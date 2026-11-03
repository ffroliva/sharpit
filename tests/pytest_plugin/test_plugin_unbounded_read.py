# ruff: noqa: E501

"""Unbounded ORM reads against the F2 spike fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.needs_sqlalchemy  # every test here runs an ORM fixture app
pytest.importorskip("sqlalchemy")

FIXTURE = Path(__file__).parents[1] / "fixtures" / "apps" / "unbounded_read"
RULE = "sharpit.unbounded-read"


def _spike_project(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        fixture=(FIXTURE / "fixture.py").read_text("utf-8"),
        test_teams="from fastapi.testclient import TestClient\nfrom fixture import app\n\ndef test_page():\n    response = TestClient(app).get('/teams?skip=0&limit=5')\n    assert response.json() == [f'team-{i}' for i in range(5)]",
    )
    pytester.makeconftest((FIXTURE / "conftest.py").read_text("utf-8"))


def _report(pytester: pytest.Pytester) -> dict[str, Any]:
    return json.loads((pytester.path / "report.json").read_text("utf-8"))


def test_core_only_sqlalchemy_host_does_not_break_sharpit(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("import sqlalchemy")
    pytester.makepyfile("def test_passes():\n    assert True")

    result = pytester.runpytest_subprocess("--sharpit", "-q")

    assert result.ret == 0


def test_installed_app_request_suppresses_missing_capture_limitation(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        fixture="""
from fastapi import FastAPI
from sqlalchemy import create_engine, Integer
from sqlalchemy.orm import DeclarativeBase, Session, mapped_column

class Base(DeclarativeBase):
    pass

class Record(Base):
    __tablename__ = "records"
    id = mapped_column(Integer, primary_key=True)

engine = create_engine("sqlite://")
Base.metadata.create_all(engine)
with Session(engine) as session:
    session.add(Record())
    session.commit()
app = FastAPI()
@app.get("/touch")
def touch():
    return {"ok": True}
""",
        test_read="""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from fixture import app, engine, Record

def test_read_outside_request():
    assert TestClient(app).get('/touch').status_code == 200
    with Session(engine) as session:
        session.query(Record).all()
""",
    )
    pytester.makeconftest("from fixture import app\nimport sharpit\nsharpit.install(app, enabled='ON')")
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-app=fixture:app", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    data = _report(pytester)
    limitations = [text for source in data["sources"] for text in source["limitations"]]
    assert not any("unbounded-read needs sharpit.install(app)" in item for item in limitations)


# fmt: off
def test_spike_f2_unbounded_read_found(pytester: pytest.Pytester) -> None:
    # spike: F2
    _spike_project(pytester)
    pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-app=fixture:app", "--sharpit-report=report.json", "-q"
    )
    data = _report(pytester)
    findings = [finding for finding in data["findings"] if finding["ruleId"] == RULE]
    assert findings, f"no {RULE} finding for 52 materialized Team rows and page size 5"
    assert "Team" in findings[0]["message"]
    assert "52" in findings[0]["message"]
    assert "5" in findings[0]["message"]


# fmt: off
def test_f2_report_names_materialized_rows_and_page_size(pytester: pytest.Pytester) -> None:
    # spike: F2
    _spike_project(pytester)
    pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-app=fixture:app", "--sharpit-report=report.json", "-q"
    )
    findings = [finding for finding in _report(pytester)["findings"] if finding["ruleId"] == RULE]
    assert findings, "F2 spike did not report an unbounded read"
    message = findings[0]["message"]
    assert "Team" in message
    assert "52" in message
    assert "5" in message
# fmt: on


# fmt: off
def test_without_install_reports_limitation_and_does_not_fire(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        fixture="""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

class Base(DeclarativeBase):
    pass

class Team(Base):
    __tablename__ = "teams_no_install"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

engine = create_engine("sqlite://")
app = FastAPI()
@app.get("/teams")
def teams(limit: int = 2) -> list[str]:
    with Session(engine) as session:
        Base.metadata.create_all(engine)
        session.add_all(Team(name=f"team-{i}") for i in range(12))
        session.commit()
    with Session(engine) as session:
        rows = session.query(Team).all()
    return [team.name for team in rows[:limit]]
""",
        test_teams="""
from fastapi.testclient import TestClient
from fixture import app

def test_page():
    response = TestClient(app).get('/teams?limit=2')
    assert response.json() == ['team-0', 'team-1']
""",
    )
    pytester.makeconftest(
        """
import sqlalchemy
from sqlalchemy.pool import StaticPool

_create_engine = sqlalchemy.create_engine
def create_engine(*args, **kwargs):
    kwargs.setdefault("connect_args", {})["check_same_thread"] = False
    kwargs.setdefault("poolclass", StaticPool)
    return _create_engine(*args, **kwargs)

sqlalchemy.create_engine = create_engine
import fixture
"""
    )
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-app=fixture:app", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 0
    data = _report(pytester)
    findings = [finding for finding in data["findings"] if finding["ruleId"] == RULE]
    limitations = [text for source in data["sources"] for text in source["limitations"]]

    assert findings == []
    assert any(
        "unbounded-read needs sharpit.install(app)" in limitation for limitation in limitations
    )
# fmt: on


def test_unbounded_read_report_only_does_not_fail_test(pytester: pytest.Pytester) -> None:
    _spike_project(pytester)
    result = pytester.runpytest_subprocess(
        "--sharpit",
        "--sharpit-report-only",
        "--sharpit-app=fixture:app",
        "--sharpit-report=report.json",
        "-q",
    )
    assert result.ret == 0
    data = _report(pytester)
    findings = [finding for finding in data["findings"] if finding["ruleId"] == RULE]

    assert len(findings) == 1
    assert data["tests"][0]["outcome"] == "passed"


def test_unbounded_read_factor_environment_override_reaches_gate(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spike_project(pytester)
    monkeypatch.setenv("SHARPIT_ACTIVITY_UNBOUNDED_READ_FACTOR", "11")
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-app=fixture:app", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 0
    data = _report(pytester)
    findings = [finding for finding in data["findings"] if finding["ruleId"] == RULE]

    assert findings == []
