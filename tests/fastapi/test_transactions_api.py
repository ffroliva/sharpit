from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sharpit import install


def test_transaction_route_reports_a_committed_sqlite_transaction() -> None:
    sa = pytest.importorskip("sqlalchemy")
    app = FastAPI()
    engine = sa.create_engine("sqlite://")
    handle = install(app, enabled="ON", show_banner=False, engines=[engine])
    try:
        with TestClient(app, base_url="http://localhost") as client:
            with engine.begin():
                pass
            response = client.get("/sharpit/api/transactions")
        assert response.status_code == 200, "the implemented transactions panel must expose its GET report route"
        report = response.json()
        assert report["available"] is True, "an installed recorder must make the transactions report available"
        assert report["entries"][0]["status"] == "COMMITTED", "a SQLAlchemy commit must appear in the report"
    finally:
        handle.uninstall_capture()
        engine.dispose()
