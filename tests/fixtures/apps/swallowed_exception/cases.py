"""The fixture app's own suite (copied into a pytester project as ``test_weeks.py``)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from weekapp import app

client = TestClient(app)


def test_weeks_clean() -> None:
    assert client.get("/weeks").json() == [1, 2]


def test_week_count() -> None:
    assert client.get("/weeks/count").status_code == 200
