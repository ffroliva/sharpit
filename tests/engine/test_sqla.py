"""The SQLAlchemy bridge (spec §6.2): engine registry, statement routing, class-level listeners and ``run_db_read``.

Every case is derived (BootUI wraps a JDBC ``DataSource``; SQLAlchemy events have no BootUI oracle).
"""

from __future__ import annotations

import asyncio
import logging
import types
from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.correlation import INTERNAL  # noqa: E402
from sharpit.engine.capture.sqltrace import SqlTraceRecorder  # noqa: E402
from sharpit.engine.masking import Exposure, Masker  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

_HANDLES: list[SharpitHandle] = []


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _install(**options: Any) -> SharpitHandle:
    handle = install(FastAPI(), **{"enabled": "ON", "show_banner": False, **options})
    _HANDLES.append(handle)
    return handle


def _recorder(handle: SharpitHandle) -> SqlTraceRecorder:
    recorder = handle.context.capture.sql_trace
    assert recorder is not None
    return recorder


def _entries(handle: SharpitHandle) -> list[dict[str, Any]]:
    return _recorder(handle).report([])["entries"]


def test_engine_display_names():
    registry = sqla.EngineRegistry(Masker(Exposure.MASKED, True))
    driver = types.SimpleNamespace(paramstyle="format", __version__="1.30.5")  # pg8000 is not installed: never connects
    first = sa.create_engine("postgresql+pg8000://user:hunter2@db.example:5432/app?sslkey=secret", module=driver)
    second = sa.create_engine("postgresql+pg8000://other:pw@db.example:5432/app", module=driver)
    memory = sa.create_engine("sqlite://")
    asynchronous = pytest.importorskip("sqlalchemy.ext.asyncio").create_async_engine("sqlite+aiosqlite:///app.db")
    for engine in (first, second, first, memory, asynchronous, object()):
        registry.add(engine)
    assert [name for name, _ in registry.engines()] == [
        "postgresql+pg8000://db.example:5432/app",
        "postgresql+pg8000://db.example:5432/app#2",
        "sqlite+pysqlite:///",
        "sqlite+aiosqlite:///app.db",
    ]
    assert registry.holds(asynchronous.sync_engine)
    assert registry.holds(first)
    names = str([name for name, _ in registry.engines()])
    assert "hunter2" not in names
    assert "secret" not in names
    assert "user" not in names


def test_registry_holds_engines_weakly():
    registry = sqla.EngineRegistry(Masker(Exposure.MASKED, True))
    registry.add(sa.create_engine("sqlite://"))
    import gc

    gc.collect()
    assert registry.engines() == []


def test_install_seeds_registry_from_engines():
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine, object()])
    registry = handle.context.capture.engine_registry
    assert registry is not None
    assert registry.holds(engine)


def test_statement_outside_request_routed_by_registry():
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine])
    other = _install()
    with engine.connect() as conn:
        assert conn.execute(sa.text("select 41 + 1")).scalar() == 42
    assert [e["sql"] for e in _entries(handle)] == ["select ? + ?"]
    assert _entries(other) == []
    entry = _entries(handle)[0]
    assert (entry["category"], entry["statementType"], entry["success"], entry["traceId"]) == (
        "SELECT", "STATEMENT", True, None
    )  # fmt: skip
    assert entry["connectionId"] is not None
    assert int(entry["connectionId"], 16) > 0


def test_executemany_batch_size():
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine])
    with engine.begin() as conn:
        conn.execute(sa.text("create table t (n integer)"))
        conn.execute(sa.text("insert into t (n) values (:n)"), [{"n": 1}, {"n": 2}, {"n": 3}])
    entry = _entries(handle)[0]
    assert (entry["batchSize"], entry["statementType"], entry["category"], entry["affectedRows"]) == (
        3, "PREPARED", "INSERT", 3
    )  # fmt: skip


def test_positional_parameters_masked_by_bind_name():
    # sqlite is qmark: the DBAPI sees a tuple, so the bind names come back from the compiled statement
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine], sql_trace_capture_parameters=True)
    with engine.begin() as conn:
        conn.execute(sa.text("select :password as p, :n as n"), {"password": "hunter2-secret", "n": 7})
        conn.execute(sa.text("create table t (password text)"))
        conn.execute(sa.text("insert into t values (:password)"), [{"password": "a-secret"}, {"password": "b-secret"}])
    by_sql = {e["sql"]: e["parameters"] for e in _entries(handle)}
    assert by_sql["select ? as p, ? as n"] == ["password=******", "n=7"]
    assert by_sql["insert into t values (?)"] == ["password=******", "password=******"]


def test_insertmanyvalues_parameters_masked_by_bind_name():
    # a RETURNING executemany is sent as one "VALUES (?), (?)" statement: the bind names repeat per row
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine], sql_trace_capture_parameters=True)
    table = sa.Table(
        "u", sa.MetaData(), sa.Column("id", sa.Integer, primary_key=True), sa.Column("password", sa.String)
    )
    with engine.begin() as conn:
        table.create(conn)
        conn.execute(sa.insert(table).returning(table.c.id), [{"password": "a-secret"}, {"password": "b-secret"}])
    batched = next(e for e in _entries(handle) if "RETURNING" in e["sql"])
    assert batched["parameters"] == ["password=******", "password=******"]
    assert batched["batchSize"] == 2  # one per row, though the DBAPI got one flat batch


def test_expanding_in_parameters_masked_by_bind_name():
    # an expanding IN list renders one placeholder per value: the names must follow the values, not positiontup
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine], sql_trace_capture_parameters=True)
    statement = sa.text("select 1 where 1 in :a and 'x' = :password and 3 in :b").bindparams(
        sa.bindparam("a", expanding=True), sa.bindparam("b", expanding=True)
    )
    with engine.connect() as conn:
        conn.execute(statement, {"a": [1, 2], "password": "hunter2-xyz", "b": [3, 4]})
    parameters = _entries(handle)[0]["parameters"]
    assert "password=******" in parameters
    assert not any("hunter2" in p for p in parameters)
    assert sorted(parameters) == sorted(["a_1=1", "a_2=2", "password=******", "b_1=3", "b_2=4"])


def test_conn_info_fallback_without_request():
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine])
    with engine.connect() as conn:
        cursor = conn.connection.dbapi_connection.cursor()  # type: ignore[union-attr]
        sqla.before_cursor_execute(conn, cursor, "select 7", (), None, False)  # no execution context
        assert sqla.START_KEY in conn.info
        cursor.execute("select 7")
        sqla.after_cursor_execute(conn, cursor, "select 7", (), None, False)
        assert sqla.START_KEY not in conn.info  # read back with pop: never leaks into the next statement
    assert [e["sql"] for e in _entries(handle)] == ["select ?"]


def test_internal_statements_not_traced():
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine])
    token = INTERNAL.set(True)
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("select 1"))
    finally:
        INTERNAL.reset(token)
    assert _entries(handle) == []


def test_pause_returns_early_listeners_kept():
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine])
    _recorder(handle).set_recording(False)
    with engine.connect() as conn:
        conn.execute(sa.text("select 1"))
        assert not any(k == sqla.START_KEY for k in conn.info)  # returned before timing anything
    assert _entries(handle) == []
    assert all(sqla.attached().values())  # pausing never removes the listeners
    _recorder(handle).set_recording(True)
    with engine.connect() as conn:
        conn.execute(sa.text("select 1"))
    assert len(_entries(handle)) == 1


def test_sql_listener_failure_query_unchanged(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine])

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("recorder broke")

    monkeypatch.setattr(_recorder(handle), "record", boom)
    with caplog.at_level(logging.WARNING, logger="sharpit"), engine.begin() as conn:
        conn.execute(sa.text("create table t (id integer primary key)"))
        conn.execute(sa.text("insert into t (id) values (1)"))
        assert conn.execute(sa.text("select id from t")).scalars().all() == [1]
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(sa.text("insert into t (id) values (1)"))
    warnings = [r.getMessage() for r in caplog.records if r.name == "sharpit"]
    assert len(warnings) == 1, warnings
    assert "sql statement" in warnings[0], warnings
    assert "recorder broke" not in warnings[0], warnings


def test_failed_statement_recorded_with_error():
    engine = sa.create_engine("sqlite://")
    handle = _install(engines=[engine])
    with engine.connect() as conn, pytest.raises(sa.exc.OperationalError):
        conn.execute(sa.text("select * from missing_table"))
    entry = _entries(handle)[0]
    assert (entry["success"], entry["affectedRows"]) == (False, None)
    assert "no such table: missing_table" in entry["errorMessage"]


def test_detach_removes_listeners_only_when_last_context_leaves():
    sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    first, second = _install(), _install()
    assert all(sqla.attached().values())
    first.uninstall_capture()
    assert all(sqla.attached().values())  # the second context still traces
    second.uninstall_capture()
    assert not any(sqla.attached().values())


def test_run_db_read_sync_and_async_not_traced():
    engine = sa.create_engine("sqlite://")
    async_engine = pytest.importorskip("sqlalchemy.ext.asyncio").create_async_engine("sqlite+aiosqlite://")
    handle = _install(engines=[engine, async_engine])

    def read(conn: Any) -> int:
        assert INTERNAL.get() is True
        return conn.execute(sa.text("select 5")).scalar()

    async def main() -> tuple[int, int]:
        sync = await sqla.run_db_read(engine, read, 5.0)
        asynchronous = await sqla.run_db_read(async_engine.sync_engine, read, 5.0)
        await async_engine.dispose()
        return sync, asynchronous

    assert asyncio.run(main()) == (5, 5)
    assert _entries(handle) == []


def test_run_db_read_times_out():
    engine = sa.create_engine("sqlite://")

    def slow(_conn: Any) -> None:
        import time

        time.sleep(0.5)

    async def main() -> None:
        await sqla.run_db_read(engine, slow, 0.05)

    with pytest.raises(TimeoutError):
        asyncio.run(main())


def test_run_db_read_done_once_the_worker_thread_really_returns():
    # spec §7.6 / §7.8: single-flight is held until the read actually returns, not when the caller gives up
    import threading
    from concurrent.futures import ThreadPoolExecutor

    engine = sa.create_engine("sqlite://")
    gate, done = threading.Event(), threading.Event()

    def slow(_conn: Any) -> None:
        gate.wait(5)

    async def main() -> None:
        with ThreadPoolExecutor(1, thread_name_prefix="test-db-read") as executor:
            with pytest.raises(TimeoutError):
                await sqla.run_db_read(engine, slow, 0.05, executor=executor, done=done.set)
            assert not done.is_set()  # the caller gave up, the thread still runs
            gate.set()
            assert await asyncio.to_thread(done.wait, 5)

    asyncio.run(main())


def test_run_db_read_done_on_the_async_path():
    async_engine = pytest.importorskip("sqlalchemy.ext.asyncio").create_async_engine("sqlite+aiosqlite://")
    calls: list[int] = []

    async def main() -> int:
        try:
            return await sqla.run_db_read(
                async_engine.sync_engine,
                lambda c: c.exec_driver_sql("select 3").scalar(),
                5.0,
                done=lambda: calls.append(1),
            )
        finally:
            await async_engine.dispose()

    assert asyncio.run(main()) == 3
    assert calls == [1]


class _FakeConnection:
    """Records the statements sharpit sends around ``fn``; ``dialect.name`` picks the timeout syntax."""

    def __init__(self, dialect: str, *, is_mariadb: bool = False, fails: str = "") -> None:
        self.dialect = types.SimpleNamespace(name=dialect, is_mariadb=is_mariadb)
        self.sent: list[str] = []
        self.fails = fails
        self.invalidated = False

    def exec_driver_sql(self, sql: str) -> Any:
        if self.fails and sql.startswith(self.fails):
            raise RuntimeError(f"server refused {sql}")
        self.sent.append(sql)
        return types.SimpleNamespace(scalar=lambda: 7)

    def invalidate(self) -> None:
        self.invalidated = True


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [
        ("postgresql", ["SET LOCAL statement_timeout = 2500", "read"]),
        (
            "mysql",
            [
                "SELECT @@SESSION.max_execution_time",
                "SET SESSION max_execution_time = 2500",
                "read",
                "SET SESSION max_execution_time = 7",
            ],
        ),
        ("sqlite", ["read"]),  # sqlite's busy wait is the driver's own connect timeout
    ],
)
def test_statement_timeout_applied_inside_the_read(dialect: str, expected: list[str]):
    conn = _FakeConnection(dialect)
    assert sqla.bounded(conn, lambda c: c.sent.append("read") or 42, 2.5) == 42
    assert conn.sent == expected


def test_mariadb_through_a_mysql_url_uses_max_statement_time():
    # a mysql+pymysql:// engine on a MariaDB server keeps dialect.name "mysql"; MariaDB has no max_execution_time
    conn = _FakeConnection("mysql", is_mariadb=True, fails="SELECT @@SESSION.max_execution_time")
    assert sqla.bounded(conn, lambda c: c.sent.append("read") or 42, 2.5) == 42
    assert conn.sent == [
        "SELECT @@SESSION.max_statement_time",
        "SET SESSION max_statement_time = 2.5",
        "read",
        "SET SESSION max_statement_time = 7.0",
    ]


def test_read_runs_without_timeout_when_the_server_has_no_timeout_variable():
    # MySQL before 5.7.8 has no max_execution_time: the read still runs, only unbounded on the server
    conn = _FakeConnection("mysql", fails="SELECT @@SESSION.max_execution_time")
    assert sqla.bounded(conn, lambda c: c.sent.append("read") or 42, 2.5) == 42
    assert conn.sent == ["read"]


def test_failed_timeout_restore_invalidates_the_app_connection():
    # the connection goes back to the app's pool: never with sharpit's timeout still set on it
    conn = _FakeConnection("mysql", fails="SET SESSION max_execution_time = 7")
    with pytest.raises(RuntimeError):
        sqla.bounded(conn, lambda c: 42, 2.5)
    assert conn.invalidated
