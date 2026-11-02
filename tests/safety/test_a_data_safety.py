"""Safety rows for the data panel (spec §4, §6.3): the guard chain and the activation gate cover its routes.

Imports without SQLAlchemy: the models are built inside the tests, after ``importorskip``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install

PANEL = "data"
GET_ROWS = ["/sharpit/api/data/repositories", "/sharpit/api/data/repositories/{name:path}"]
WRITE_ROWS: list[tuple[str, str]] = []
PATH_PARAMS = {"name": "Owner"}  # a class the sample app below maps

LOCAL = ("127.0.0.1", 50000)
PATHS = ("/sharpit/api/data/repositories", "/sharpit/api/data/repositories/Owner")


def _client(**options: object) -> TestClient:
    sa = pytest.importorskip("sqlalchemy")
    orm = pytest.importorskip("sqlalchemy.orm")

    class Base(orm.DeclarativeBase):
        pass

    class Owner(Base):
        __tablename__ = "owners"
        id = orm.mapped_column(sa.Integer, primary_key=True)

    app = FastAPI()
    options.setdefault("models", Base)
    install(app, show_banner=False, config_scan=False, **{"enabled": "ON", **options})
    app.state.held = Owner  # a registry holds mapped classes weakly
    return TestClient(app, base_url="http://localhost", client=LOCAL)


@pytest.mark.parametrize("path", PATHS)
def test_cross_site_request_is_refused(path: str) -> None:
    # derived: guard chain runs on every request, including the data routes
    response = _client().get(path, headers={"Origin": "http://evil.example"})

    assert response.status_code == 403
    assert response.json() == {"error": "sharpit rejected a cross-site request."}


@pytest.mark.parametrize("path", PATHS)
def test_inactive_install_answers_404(path: str) -> None:
    # derived: fails closed, an inactive mount answers 404 for every path
    assert _client(enabled="OFF").get(path).status_code == 404
