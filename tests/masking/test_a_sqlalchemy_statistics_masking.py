"""A secret in a slow statement never reaches the ``sqlalchemy-statistics`` body (lane A-sqlalchemy-statistics)."""

from __future__ import annotations

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from sharpit import install  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

STRIPE_KEY = "sk_live_4eC39HqLyjWDarjtT1zdp7dc"


def test_stripe_key_in_slow_query_never_appears():
    engine = sa.create_engine("sqlite://")
    app = FastAPI()

    @app.get("/charge")
    def charge() -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        with engine.connect() as conn:
            for i in range(6):
                conn.execute(sa.text(f"select '{STRIPE_KEY}{i}'"))
        return {"n": 6}

    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        sql_trace_sqlite3_enabled=False,
        sql_trace_capture_parameters=True,
        sql_trace_slow_query_threshold_millis=0,
    )
    try:
        client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
        client.get("/charge")
        body = client.get("/sharpit/api/sqlalchemy-statistics").text
    finally:
        handle.uninstall_capture()
    assert STRIPE_KEY not in body
    assert '"executionsPerRequest"' in body
