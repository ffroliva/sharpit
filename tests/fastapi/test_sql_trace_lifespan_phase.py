"""SQL Trace ``requestPhase`` labels from the ASGI lifespan (W9 task 4, ruling (h)).

Derived cases: BootUI 2.3.0 labels only request phases (FILTERS, HANDLER, RESPONSE). sharpit adds STARTUP and SHUTDOWN
for statements outside a request while the host's lifespan was observed starting up or shutting down; anything else
stays null (unknown).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine.capture.sqltrace import SqlTraceRecorder  # noqa: E402
from sharpit.engine.sqltext import Dialect  # noqa: E402
from sharpit.engine.testsession.sink import report_masker  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/sql-trace"
_HANDLES: list[SharpitHandle] = []


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _select(engine: Any, name: str) -> None:
    with engine.connect() as conn:
        conn.execute(sa.text(f"select 1 as {name}"))


def _app(engine: Any) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        _select(engine, "startup")
        yield
        _select(engine, "shutdown")

    app = FastAPI(lifespan=lifespan)

    @app.get("/users")
    def users() -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        _select(engine, "request")
        return {"n": 1}

    @app.get("/noop")
    def noop() -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"n": 0}

    handle = install(app, enabled="ON", show_banner=False, sql_trace_sqlite3_enabled=False)
    _HANDLES.append(handle)
    return app


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL)


def _phases(app: FastAPI) -> dict[str, Any]:
    entries = _client(app).get(API).json()["entries"]  # no ``with``: reading runs no lifespan
    return {entry["sql"].rsplit(" ", 1)[-1]: entry["requestPhase"] for entry in entries}  # keyed by the alias


def test_statements_in_the_observed_lifespan_are_labelled_startup_and_shutdown() -> None:
    engine = sa.create_engine("sqlite://")
    app = _app(engine)

    with _client(app) as client:
        client.get("/users")

    phases = _phases(app)
    assert phases["startup"] == "STARTUP"
    assert phases["shutdown"] == "SHUTDOWN"


def test_request_statement_keeps_a_null_phase_while_the_app_runs() -> None:
    engine = sa.create_engine("sqlite://")
    app = _app(engine)

    with _client(app) as client:
        client.get("/users")

    assert _phases(app)["request"] is None


def test_statement_outside_a_request_after_startup_is_unknown() -> None:
    engine = sa.create_engine("sqlite://")
    app = _app(engine)

    with _client(app) as client:
        client.get("/noop")
        _select(engine, "running")

    assert _phases(app)["running"] is None


def test_without_an_observed_lifespan_no_statement_is_labelled() -> None:
    engine = sa.create_engine("sqlite://")
    app = _app(engine)
    client = _client(app)  # no ``with``: the lifespan never runs

    client.get("/users")
    _select(engine, "outside")

    phases = _phases(app)
    assert phases["request"] is None
    assert phases["outside"] is None
    assert "startup" not in phases


def test_a_failed_startup_clears_the_startup_label() -> None:
    engine = sa.create_engine("sqlite://")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        _select(engine, "startup")
        raise RuntimeError("startup failed")
        yield  # pragma: no cover

    app = FastAPI(lifespan=lifespan)
    handle = install(app, enabled="ON", show_banner=False, sql_trace_sqlite3_enabled=False)
    _HANDLES.append(handle)
    with pytest.raises(RuntimeError, match="startup failed"), _client(app):
        pass  # pragma: no cover

    assert _phases(app)["startup"] == "STARTUP"
    recorder = handle.context.capture.sql_trace
    assert recorder is not None
    assert recorder.lifespan_phase is None  # a statement the host runs from here on is not labelled STARTUP


def test_a_request_statement_during_startup_is_not_labelled() -> None:
    recorder = SqlTraceRecorder(report_masker())
    recorder.lifespan_phase = "STARTUP"

    recorder.record("select 1", duration_ns=1, thread="t", connection_id=None, dialect=Dialect.SQLITE, request_id="r1")
    recorder.record("select 2", duration_ns=1, thread="t", connection_id=None, dialect=Dialect.SQLITE)

    request, outside = recorder.report([])["entries"][::-1]
    assert request["requestPhase"] is None
    assert outside["requestPhase"] == "STARTUP"
