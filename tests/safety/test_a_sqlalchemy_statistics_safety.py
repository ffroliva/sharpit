"""``sqlalchemy-statistics`` reads have no side effects (lane A-sqlalchemy-statistics; AGENTS.md safety model 4)."""

from __future__ import annotations

import pytest

sa = pytest.importorskip("sqlalchemy")

from examples.fastapi_sample.app import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from conftest import SideEffectGuard  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy


def test_get_no_side_effects(no_side_effects: SideEffectGuard):
    engine = sa.create_engine("sqlite://")
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON", engines=[engine])
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        with engine.connect() as conn:
            conn.execute(sa.text("select 1"))
        checkouts: list[object] = []

        def checkout(*args: object) -> None:
            checkouts.append(args)

        sa.event.listen(engine, "checkout", checkout)
        no_side_effects.block_network()
        response = client.get("/sharpit/api/sqlalchemy-statistics")
        sa.event.remove(engine, "checkout", checkout)
    assert response.status_code == 200
    body = response.json()
    assert body["statistics"]["queryExecutionCount"] == 1
    assert checkouts == []  # reading statistics never checks out a connection
    assert no_side_effects.violations == []
