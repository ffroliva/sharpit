# ruff: noqa: E501

"""Unbounded ORM reads against the F2 spike fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

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
