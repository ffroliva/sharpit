"""A literal secret in a traced statement never reaches ``/sql-trace/insights`` (lane A-sqltrace-insights).

Parameter capture is on, so the ring stores masked literal SQL: insights must show the normalized text only
(BootUI ``SqlTraceInsightsServiceTests.neverExposesBoundParametersEvenWhenParameterCaptureIsOn``).
"""

from __future__ import annotations

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

STRIPE_KEY = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"
EMAIL = "ada@example.com"


def test_insights_statement_text_masked():
    engine = sa.create_engine("sqlite://")
    app = FastAPI()

    @app.get("/charge")
    def charge() -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        with engine.connect() as conn:
            conn.execute(sa.text(f"select '{STRIPE_KEY}', '{EMAIL}'"))
            conn.execute(sa.text("select :email"), {"email": EMAIL})
        return {"n": 2}

    handle = install(
        app, enabled="ON", show_banner=False, sql_trace_sqlite3_enabled=False, sql_trace_capture_parameters=True
    )
    try:
        client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
        client.get("/charge")
        response = client.get("/sharpit/api/sql-trace/insights")
    finally:
        handle.uninstall_capture()
    assert response.status_code == 200
    body = response.text
    # insights rank by duration, so two near-equal statements may swap: the masked texts, not their order
    assert sorted(s["sql"] for s in response.json()["statements"]) == ["select ?", "select ?, ?"]
    assert STRIPE_KEY not in body
    assert EMAIL not in body
