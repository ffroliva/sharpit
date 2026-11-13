"""``connections-per-request`` on real installs: a FastAPI app with sharpit and a sqlite file engine, so the producer,
the join, the pool size and the pool class are the production ones (the ported evaluation tests are in
tests/engine/insights/test_insights_connections_per_request.py)."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.collectors.insights.service import insights_service  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

KIND = "connections-per-request"
Row = dict[str, Any]


@pytest.fixture(autouse=True)
def clean_listeners() -> Iterator[None]:
    sqla.detach_all()
    yield
    sqla.detach_all()


def _app(engine: Any) -> tuple[TestClient, Any]:
    app = FastAPI()

    @app.get("/nested")
    async def nested() -> dict[str, int]:
        with engine.connect() as outer:
            outer.execute(sa.text("select 1"))
            with engine.connect() as inner:  # a second logical connection while the first is held
                inner.execute(sa.text("select 2"))
        return {"ok": 1}

    @app.get("/sequential")
    async def sequential() -> dict[str, int]:
        for _ in range(2):
            with engine.connect() as conn:
                conn.execute(sa.text("select 1"))
        return {"ok": 1}

    handle = install(
        app, enabled="ON", show_banner=False, config_scan=False, engines=[engine],
        runtime_journal_sources=("http", "sql", "connection"),
    )  # fmt: skip
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)), handle.context


def _file_app(tmp_path: pathlib.Path, **engine_options: Any) -> tuple[TestClient, Any]:
    return _app(sa.create_engine(f"sqlite:///{tmp_path / 'cpr.db'}", **engine_options))


def _rows(ctx: Any) -> list[Row]:
    return [o for o in insights_service(ctx).report()["observations"] if o["kind"] == KIND]


def _check(ctx: Any) -> Row:
    return next(c for c in insights_service(ctx).report()["checks"] if c["kind"] == KIND)


def test_connections_per_request_real_install_nested_connections_are_found_with_the_pool_size(
    tmp_path: pathlib.Path,
) -> None:
    client, ctx = _file_app(tmp_path, pool_size=3, max_overflow=2)
    assert client.get("/nested").status_code == 200
    assert client.get("/sequential").status_code == 200
    rows = _rows(ctx)
    assert [r["subject"] for r in rows] == ["GET /nested"]
    sentence = str(rows[0]["sentence"])
    assert sentence.startswith("`GET /nested` held 2 connections of `sqlite+pysqlite:///")
    assert sentence.endswith("` at the same time in 1 of 1 request.")
    assert "pool of 5 connections" in str(rows[0]["whatToCheck"][1])  # 3 + 2 overflow: SQLAlchemy's maximum
    assert _check(ctx)["status"] == "EVALUATED"
    assert _check(ctx)["eligibleRequests"] == 2
    assert "hands the same connection" not in str(_check(ctx)["reason"])  # a queue pool gives each checkout its own


def test_connections_per_request_real_install_a_pool_with_no_maximum_uses_p(tmp_path: pathlib.Path) -> None:
    client, ctx = _file_app(tmp_path, pool_size=2, max_overflow=-1)  # an unbounded overflow: no maximum
    assert client.get("/nested").status_code == 200
    rows = _rows(ctx)
    assert len(rows) == 1
    assert rows[0]["limitations"][1] == "The pool's maximum size is unavailable; the estimate uses P."


def test_connections_per_request_real_install_a_shared_connection_pool_cannot_show_nesting() -> None:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    client, ctx = _app(engine)
    assert client.get("/nested").status_code == 200
    assert _rows(ctx) == []  # one pooled connection serves both checkouts: one event, nothing to overlap
    check = _check(ctx)
    assert check["status"] == "EVALUATED"
    assert "hands the same connection to a checkout made while another is held" in str(check["reason"])
    assert "StaticPool" in str(check["reason"])
