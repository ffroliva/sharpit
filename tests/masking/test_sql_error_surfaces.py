"""A statement inside an error message is scanned on every surface that shows it (release fix round 3, p_raw_sql.py).

``mask_text`` masks secrets by shape, so a literal in ``[SQL: SELECT 'x']`` passes it. Each test reads a real report or
API, and checks the error reached the surface, so a missing error cannot pass as a clean one.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.engine.collectors.mysql.fakes import FakeMySqlEngine
from tests.engine.collectors.mysql.fakes import FakeRegistry as MySqlRegistry
from tests.engine.postgresql.fakes import FakePgEngine
from tests.engine.postgresql.fakes import FakeRegistry as PgRegistry

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.capture.transactions import TransactionRecorder
from sharpit.engine.collectors import data
from sharpit.engine.collectors.mysql.service import refresh_mysql
from sharpit.engine.collectors.postgresql.service import refresh_postgresql
from sharpit.engine.context import SharpitContext
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.testsession.sink import TestSessionSink
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.settings import load_settings

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
LINEAR = Path(__file__).resolve().parents[1] / "fixtures" / "alembic" / "linear" / "alembic.ini"
LOCAL = ("127.0.0.1", 50000)
NODE = "tests/test_x.py::test_x"
LITERAL = "stmt-literal-7"
REASON = "no such table"
ERROR = f"(sqlite3.OperationalError) {REASON}\n[SQL: SELECT '{LITERAL}' FROM missing]"
MYSQL_ERROR = f"(driver.Error) {REASON}\n[SQL: SELECT 1 # password {LITERAL}]"
log = logging.getLogger("host.app")


class _Introspector:
    def app_info(self) -> Any:
        return None

    def routes(self) -> list[Any]:
        return []

    def providers(self) -> list[Any]:
        return []


@pytest.fixture
def handles() -> Iterator[list[SharpitHandle]]:
    installed: list[SharpitHandle] = []
    yield installed
    for handle in installed:
        handle.uninstall_capture()


def _client(handles: list[SharpitHandle], app: FastAPI | None = None, **options: Any) -> TestClient:
    app = app or FastAPI()
    handles.append(install(app, enabled="ON", show_banner=False, **options))
    return TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False)


def _refusing_engine() -> Any:
    def refuse() -> Any:
        raise RuntimeError(ERROR)

    return sa.create_engine("sqlite://", creator=refuse, poolclass=sa.pool.NullPool)


def _assert_scanned(shown: str) -> None:
    assert REASON in shown
    assert LITERAL not in shown


def _failing_app() -> FastAPI:
    app = FastAPI()

    @app.get("/fail")
    def fail() -> None:
        raise RuntimeError(ERROR)

    @app.get("/logged")
    def logged() -> None:
        log.error("query failed: %s", ERROR)

    return app


def test_exceptions_report(handles: list[SharpitHandle]) -> None:
    client = _client(handles, _failing_app())
    client.get("/fail")
    _assert_scanned(client.get("/sharpit/api/exceptions").text)


def test_log_tail(handles: list[SharpitHandle]) -> None:
    client = _client(handles, _failing_app())
    with client:
        client.get("/logged")
        _assert_scanned(client.get("/sharpit/api/log-tail/recent").text)


def test_http_probe_response(handles: list[SharpitHandle]) -> None:
    client = _client(handles, _failing_app())
    with client:
        response = client.post("/sharpit/api/http-probe", json={"method": "GET", "path": "/fail"})
    _assert_scanned(response.text)


def test_health_check(handles: list[SharpitHandle]) -> None:
    client = _client(handles, engines=[_refusing_engine()])
    _assert_scanned(client.post("/sharpit/api/health/check").text)


def test_alembic_database_read(handles: list[SharpitHandle]) -> None:
    client = _client(handles, engines=[_refusing_engine()], alembic_config=str(LINEAR))
    client.post("/sharpit/api/alembic/refresh")
    _assert_scanned(client.get("/sharpit/api/alembic/migrations").text)


def test_transactions_report() -> None:
    recorder = TransactionRecorder(Masker(Exposure.MASKED, True, None))
    entry = recorder.begin(1, parent=None, method="a:b", thread="MainThread", trace_id=None, connection_id="db-1")
    recorder.end(entry, "UNKNOWN", RuntimeError(ERROR))
    _assert_scanned(json.dumps(recorder.report([])))


def test_sql_trace_report_when_the_error_names_another_statement() -> None:
    recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, None))
    recorder.record("SELECT 1", duration_ns=1, thread="t", connection_id=None, error=RuntimeError(ERROR))
    _assert_scanned(json.dumps(recorder.report([])))


def test_test_session_report() -> None:
    sink = TestSessionSink("gw0")
    attempt = sink.begin_test(NODE)
    sink.on_exception(RuntimeError(ERROR), "logging", (NODE, attempt, "call"))
    assert sink.current_test is not None
    _assert_scanned(json.dumps(sink.current_test.phases["call"].exception_groups))


def _pg_context(engine: FakePgEngine) -> SharpitContext:
    ctx = SharpitContext(load_settings({"config_scan": False}, {}), ACTIVATION, _Introspector())
    ctx.capture.engine_registry = PgRegistry(("primary", engine))  # type: ignore[assignment]
    return ctx


def _mysql_context(engine: FakeMySqlEngine) -> SharpitContext:
    ctx = SharpitContext(load_settings({"config_scan": False}, {}), ACTIVATION, _Introspector())
    ctx.capture.engine_registry = MySqlRegistry(("primary", engine))  # type: ignore[assignment]
    return ctx


def test_postgresql_refused_engine() -> None:
    _assert_scanned(repr(asyncio.run(refresh_postgresql(_pg_context(FakePgEngine(refuse=ERROR))))))


def test_postgresql_failed_section() -> None:
    engine = FakePgEngine()
    engine.conn.fail("INDEXES", ERROR)
    _assert_scanned(repr(asyncio.run(refresh_postgresql(_pg_context(engine)))))


@pytest.mark.parametrize("message", [ERROR, MYSQL_ERROR], ids=["string", "hash-comment"])
def test_mysql_refused_engine(message: str) -> None:
    _assert_scanned(repr(asyncio.run(refresh_mysql(_mysql_context(FakeMySqlEngine(refuse=message))))))


@pytest.mark.parametrize("message", [ERROR, MYSQL_ERROR], ids=["string", "hash-comment"])
def test_mysql_failed_section(message: str) -> None:
    engine = FakeMySqlEngine()
    engine.conn.fail("STATUS", message)
    _assert_scanned(repr(asyncio.run(refresh_mysql(_mysql_context(engine)))))


# derived: delete-the-control on the MySQL mode: the digit in LITERAL normalised away in either mode, so the first
# hash-comment case proved nothing. Letters only stay in the generic scan and go in the MySQL one
HASH_LITERAL = "hash-comment-letters"
HASH_ERROR = f"(driver.Error) {REASON}\n[SQL: SELECT 1 # {HASH_LITERAL}]"


def test_mysql_refused_engine_reads_the_block_as_mysql() -> None:
    shown = repr(asyncio.run(refresh_mysql(_mysql_context(FakeMySqlEngine(refuse=HASH_ERROR)))))
    assert REASON in shown
    assert HASH_LITERAL not in shown


def test_mysql_failed_section_reads_the_block_as_mysql() -> None:
    engine = FakeMySqlEngine()
    engine.conn.fail("STATUS", HASH_ERROR)
    shown = repr(asyncio.run(refresh_mysql(_mysql_context(engine))))
    assert REASON in shown
    assert HASH_LITERAL not in shown


def test_data_panel_warning() -> None:
    ctx = SimpleNamespace(masker=Masker(Exposure.MASKED, True, None))
    _assert_scanned(data._masked(ctx, f"Could not read a mapper (RuntimeError: {ERROR})"))  # type: ignore[arg-type]  # noqa: SLF001
