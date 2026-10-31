"""SQL Trace endpoints, MCP and CLI tools, and the listener wiring end to end (F3, spec §6.1 steps 4a/4b, §6.2, §7.3).

Derived cases (SQLAlchemy events have no BootUI oracle) unless a ``# ported:`` cite says otherwise.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

from examples.fastapi_sample.app import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from conftest import SideEffectGuard  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.sqltrace import ENTRY_KEYS, GROUP_KEYS, REPORT_KEYS, STATS_KEYS  # noqa: E402
from sharpit.engine.masking import MASK  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/sql-trace"
SENTINEL = "s3ntinel-hunter2"
ROOT = Path(__file__).resolve().parents[2]
_HANDLES: list[SharpitHandle] = []


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _install(app: FastAPI, **options: Any) -> SharpitHandle:
    handle = install(app, **{"enabled": "ON", "show_banner": False, "stream_max_seconds": 0.05, **options})
    _HANDLES.append(handle)
    return handle


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False)


def _db_app(engine: Any) -> FastAPI:
    app = FastAPI()

    @app.get("/users")
    def list_users() -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        with engine.connect() as conn:
            return {"n": conn.execute(sa.text("select 40 + 2")).scalar()}

    return app


def _request_id(client: TestClient, path: str) -> str:
    rows = client.get("/sharpit/api/http-exchanges").json()["exchanges"]
    return next(r["id"] for r in rows if r["path"] == path)


def test_request_statement_traced_with_request_id_and_call_site():
    engine = sa.create_engine("sqlite://")
    app = _db_app(engine)
    _install(app)
    client = _client(app)
    assert client.get("/users").json() == {"n": 42}
    report = client.get(API).json()
    entry = report["entries"][0]
    assert (entry["sql"], entry["traceId"]) == ("select ? + ?", _request_id(client, "/users"))
    assert re.fullmatch(r"test_sql_trace_api:list_users:\d+", entry["callSite"]), entry["callSite"]
    assert report["dataSources"] == ["sqlite+pysqlite:///"]  # discovered by engine_connect inside the request
    assert report["topStatements"][0]["callSites"] == [entry["callSite"]]


def test_engine_created_after_install_traced():
    app = FastAPI()
    _install(app)
    engines: list[Any] = []

    @app.get("/late")
    def late() -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        engines.append(sa.create_engine("sqlite://"))
        with engines[0].connect() as conn:
            return {"n": conn.execute(sa.text("select 1")).scalar()}

    client = _client(app)
    client.get("/late")
    assert [e["sql"] for e in client.get(API).json()["entries"]] == ["select ?"]


def test_two_apps_see_only_own_sql():
    engine = sa.create_engine("sqlite://")
    first, second = _db_app(engine), _db_app(engine)
    _install(first)
    _install(second)
    first_client, second_client = _client(first), _client(second)
    first_client.get("/users")
    assert len(first_client.get(API).json()["entries"]) == 1
    assert second_client.get(API).json()["entries"] == []
    second_client.get("/users")
    second_client.get("/users")
    assert len(first_client.get(API).json()["entries"]) == 1
    assert len(second_client.get(API).json()["entries"]) == 2


def test_call_site_off():
    app = _db_app(sa.create_engine("sqlite://"))
    _install(app, sql_trace_capture_call_site=False)
    client = _client(app)
    client.get("/users")
    entry = client.get(API).json()["entries"][0]
    assert entry["callSite"] is None
    assert client.get(API).json()["topStatements"][0]["callSites"] == []


def test_async_engine_traced_and_call_site_is_app(tmp_path: Path):
    asyncio_ext = pytest.importorskip("sqlalchemy.ext.asyncio")
    engine = asyncio_ext.create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'a.db'}", poolclass=sa.pool.NullPool)
    app = FastAPI()

    @app.get("/async-users")
    async def async_users() -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        async with asyncio_ext.AsyncSession(engine) as session:
            return {"n": (await session.execute(sa.text("select 6 * 7"))).scalar_one()}

    _install(app)
    with _client(app) as client:
        assert client.get("/async-users").json() == {"n": 42}
        entry = client.get(API).json()["entries"][0]
        assert entry["traceId"] == _request_id(client, "/async-users")  # the request id crossed into the greenlet
    assert re.fullmatch(r"test_sql_trace_api:async_users:\d+", entry["callSite"]), entry["callSite"]


def test_integrity_error_parameters_dropped():
    shared = {"poolclass": sa.pool.StaticPool, "connect_args": {"check_same_thread": False}}  # one in-memory database
    engine = sa.create_engine("sqlite://", **shared)
    with engine.begin() as conn:
        conn.execute(sa.text("create table creds (id integer primary key, secret text)"))
    app = FastAPI()

    @app.get("/dupe")
    def dupe() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        with engine.begin() as conn:
            for _ in range(2):
                conn.execute(sa.text("insert into creds (id, secret) values (1, :s)"), {"s": SENTINEL})
        return {}

    _install(app)
    client = _client(app)
    assert client.get("/dupe").status_code == 500
    report = client.get(API).json()
    failed = next(e for e in report["entries"] if not e["success"])
    assert "IntegrityError" in failed["errorMessage"] and f"[parameters: {MASK}]" in failed["errorMessage"]
    assert SENTINEL not in str(report)


def test_recording_toggle_and_bad_body_400():
    # ported: SqlTraceControllerSupport.recording (missing or null `enabled` flips the switch)
    app = FastAPI()
    _install(app)
    client = _client(app)
    assert client.post(f"{API}/recording", json={"enabled": False}).json()["capturing"] is False
    assert client.post(f"{API}/recording", content=b"").json()["capturing"] is True
    assert client.post(f"{API}/recording", json={"enabled": None}).json()["capturing"] is False
    assert client.post(f"{API}/recording", json={}).json()["capturing"] is True


@pytest.mark.parametrize("body", [b'{"enabled": "yes"}', b"not json", b"[true]", b'{"enabled": 1}'])
def test_recording_bad_body_400(body: bytes):
    app = FastAPI()
    _install(app)
    resp = _client(app).post(f"{API}/recording", content=body)
    assert (resp.status_code, resp.json()) == (
        400, {"error": "Request body must be a JSON object with a boolean or null 'enabled'"}
    )  # fmt: skip


def test_clear_returns_report():
    app = _db_app(sa.create_engine("sqlite://"))
    _install(app)
    client = _client(app)
    client.get("/users")
    cleared = client.post(f"{API}/clear").json()
    assert (cleared["entries"], cleared["totalCaptured"]) == ([], 1)


def test_insights_404():
    app = FastAPI()
    _install(app)
    resp = _client(app).get(f"{API}/insights")
    assert (resp.status_code, resp.json()) == (404, {"error": "Not Found"})


def test_recording_post_read_only_403():
    app = FastAPI()
    _install(app, panels={"sql-trace": {"read_only": True}})
    client = _client(app)
    for path in (f"{API}/recording", f"{API}/clear"):
        resp = client.post(path, json={"enabled": False})
        assert resp.status_code == 403 and resp.json()["reason"] == (
            "Panel is read-only via SHARPIT_PANELS_SQL_TRACE_READ_ONLY=true"
        )
    assert client.get(API).json()["capturing"] is True


def test_shape_keys_match_bootui():
    # ported: SqlTraceReport, SqlTraceEntryDto, SqlTraceGroupDto, SqlTraceStatsDto record components
    app = _db_app(sa.create_engine("sqlite://"))
    _install(app)
    client = _client(app)
    client.get("/users")
    report = client.get(API).json()
    assert tuple(report) == REPORT_KEYS == (
        "available", "unavailableReason", "capturing", "captureParameters", "bufferSize", "totalCaptured",
        "slowQueryThresholdMillis", "dataSources", "stats", "entries", "topStatements", "warnings",
    )  # fmt: skip
    assert tuple(report["stats"]) == STATS_KEYS == (
        "totalQueries", "totalDurationMillis", "maxDurationMillis", "avgDurationMillis", "slowQueries",
        "failedQueries", "batchExecutions", "selectCount", "insertCount", "updateCount", "deleteCount", "otherCount",
        "evicted",
    )  # fmt: skip
    assert tuple(report["entries"][0]) == ENTRY_KEYS == (
        "id", "timestamp", "sql", "statementType", "category", "durationMillis", "success", "errorMessage",
        "affectedRows", "batchSize", "connectionId", "thread", "slow", "parameters", "traceId", "callSite",
    )  # fmt: skip
    assert tuple(report["topStatements"][0]) == GROUP_KEYS == (
        "sql", "category", "executions", "totalDurationMillis", "maxDurationMillis", "potentialNPlusOne", "callSites",
    )  # fmt: skip
    assert (report["available"], report["unavailableReason"], report["bufferSize"]) == (True, None, 200)
    assert (report["slowQueryThresholdMillis"], report["captureParameters"]) == (100, False)


def test_sql_trace_enabled_false_attaches_nothing():
    sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    app = FastAPI()
    handle = _install(app, sql_trace_enabled=False)
    assert handle.context.capture.sql_trace is None
    attached = sqla.attached()
    assert not any(attached[e] for e in sqla.STATEMENT_EVENTS) and attached["engine_connect"]
    report = _client(app).get(API).json()
    assert (report["available"], report["unavailableReason"]) == (False, sqla.TRACING_DISABLED)
    panel = next(p for p in _client(app).get("/sharpit/api/panels").json()["panels"] if p["id"] == "sql-trace")
    assert (panel["available"], panel["unavailableReason"]) == (False, sqla.TRACING_DISABLED)


def test_panel_available_with_sqlalchemy_imported():
    app = FastAPI()
    _install(app)
    panel = next(p for p in _client(app).get("/sharpit/api/panels").json()["panels"] if p["id"] == "sql-trace")
    assert (panel["available"], panel["unavailableReason"]) == (True, None)


def test_lifespan_shutdown_removes_sql_listeners():
    sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    app = _db_app(sa.create_engine("sqlite://"))
    _install(app)
    with _client(app) as client:
        assert all(sqla.attached().values())
        client.get("/users")
    assert not any(sqla.attached().values())
    with _client(app) as client:  # a new startup attaches again
        assert all(sqla.attached().values())
        client.get("/users")
        assert len(client.get(API).json()["entries"]) == 2


def test_discovery_listener_skipped_when_db_panels_disabled():
    sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    app = FastAPI()
    _install(app, panels={p: {"enabled": False} for p in sqla.DISCOVERY_PANELS})
    attached = sqla.attached()
    assert attached["engine_connect"] is False and all(attached[e] for e in sqla.STATEMENT_EVENTS)


def test_no_lifespan_first_request_attaches_listeners(monkeypatch: pytest.MonkeyPatch):
    sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    engine = sa.create_engine("sqlite://")
    app = _db_app(engine)
    with monkeypatch.context() as hidden:
        hidden.delitem(sys.modules, "sqlalchemy")  # not imported yet when install() runs
        _install(app)
    assert not any(sqla.attached().values())
    client = _client(app)  # no lifespan: the first host request attaches
    client.get("/users")
    assert all(sqla.attached().values())
    assert [e["sql"] for e in client.get(API).json()["entries"]] == ["select ? + ?"]


def test_sqlalchemy_imported_in_lifespan_attached_at_startup():
    script = textwrap.dedent(
        """
        import sys
        from contextlib import asynccontextmanager

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import sharpit
        from sharpit.engine import sqla

        state = {}

        @asynccontextmanager
        async def lifespan(app):
            import sqlalchemy as sa

            state["engine"] = sa.create_engine("sqlite://")
            yield

        app = FastAPI(lifespan=lifespan)

        @app.get("/q")
        def q():
            import sqlalchemy as sa

            with state["engine"].connect() as conn:
                return {"n": conn.execute(sa.text("select 3")).scalar()}

        handle = sharpit.install(app, enabled="ON", show_banner=False)
        assert "sqlalchemy" not in sys.modules
        with TestClient(app) as client:
            assert all(sqla.attached().values()), sqla.attached()
            client.get("/q")
            entries = handle.context.capture.sql_trace.report([])["entries"]
            assert [e["sql"] for e in entries] == ["select ?"], entries
        assert not any(sqla.attached().values())
        print("ok")
        """
    )
    done = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert (done.returncode, done.stdout.strip()) == (0, "ok"), done.stderr


def _rpc(client: TestClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return client.post("/sharpit/api/mcp", json=call).json()


def test_get_sql_traces_mcp_no_side_effects(no_side_effects: SideEffectGuard):
    engine = sa.create_engine("sqlite://")
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON", engines=[engine])
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(app) as client:
        with engine.connect() as conn:
            conn.execute(sa.text("select 'for the agent'"))
        checkouts: list[object] = []

        def checkout(*args: object) -> None:
            checkouts.append(args)

        sa.event.listen(engine, "checkout", checkout)
        no_side_effects.block_network()
        result = _rpc(client, "get_sql_traces", {})["result"]
        sa.event.remove(engine, "checkout", checkout)
    assert result["isError"] is False
    assert [e["sql"] for e in result["structuredContent"]["entries"]] == ["select ?"]
    assert checkouts == []  # reading the trace never checks out a connection
    assert no_side_effects.violations == []


def test_sql_cli_tools_cli_only():
    app = _db_app(sa.create_engine("sqlite://"))
    _install(app, cli_enabled=True, mcp_enabled="ON")
    client = _client(app)
    client.get("/users")
    listed = client.post("/sharpit/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    names = [t["name"] for t in listed["result"]["tools"]]
    tools = ("clear_sql_traces", "pause_sql_trace_recording", "resume_sql_trace_recording")
    assert "get_sql_traces" in names and not set(tools) & set(names)
    paused = client.post("/sharpit/api/cli/tools/pause_sql_trace_recording", json={}).json()
    assert (paused["capturing"], len(paused["entries"])) == (False, 1)
    assert client.post("/sharpit/api/cli/tools/resume_sql_trace_recording", json={}).json()["capturing"] is True
    cleared = client.post("/sharpit/api/cli/tools/clear_sql_traces", json={}).json()
    assert (cleared["entries"], cleared["capturing"]) == ([], True)
