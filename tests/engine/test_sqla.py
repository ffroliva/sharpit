"""The SQLAlchemy bridge (spec §6.2): engine registry, statement routing, class-level listeners and ``run_db_read``.

Every case is derived (BootUI wraps a JDBC ``DataSource``; SQLAlchemy events have no BootUI oracle).
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.correlation import INTERNAL, REQUEST, TEST, RequestInfo  # noqa: E402
from sharpit.engine.capture.sqltrace import SqlTraceRecorder  # noqa: E402
from sharpit.engine.masking import Exposure, Masker  # noqa: E402
from sharpit.engine.sqla import orm as sqla_orm  # noqa: E402
from sharpit.engine.sqltext import Dialect  # noqa: E402
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


def test_session_capture_does_not_register_orm_execute_listener():
    assert not hasattr(sqla, "do_orm_execute"), "the SQLAlchemy bridge must not install an ORM execution hook"
    assert sqla.attach_session() is True
    sqla.detach_session()


@pytest.fixture
def session_key() -> Iterator[None]:
    """As a session's start does: a statement on SQLite has no group without it."""
    sqla.set_identity_key(b"k" * 32)
    yield
    sqla.set_identity_key(None)


def test_repeated_lazy_load_inspects_relationship_and_fingerprint_once(
    session_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the lazy-load budget (test_n_plus_one_overhead) pins the time; this pins the work behind it as a count
    orm = pytest.importorskip("sqlalchemy.orm")
    engine = sa.create_engine("sqlite://")
    Base = orm.declarative_base()

    class Parent(Base):
        __tablename__ = "repeat_parent"
        id = sa.Column(sa.Integer, primary_key=True)
        children = orm.relationship("Child")

    class Child(Base):
        __tablename__ = "repeat_child"
        id = sa.Column(sa.Integer, primary_key=True)
        parent_id = sa.Column(sa.Integer, sa.ForeignKey("repeat_parent.id"))

    Base.metadata.create_all(engine)
    with orm.Session(engine) as session:
        session.add_all(Parent(children=[Child()]) for _ in range(10))
        session.commit()
    _install(engines=[engine])

    calls = {"path": 0, "fingerprint": 0}
    path, fingerprint = sqla_orm._relationship_path, sqla_orm._masked_fingerprint

    def count_path(context: object) -> object:
        calls["path"] += 1
        return path(context)

    def count_fingerprint(statement: str, dialect: Dialect) -> str:
        calls["fingerprint"] += 1
        return fingerprint(statement, dialect)

    monkeypatch.setattr(sqla_orm, "_relationship_path", count_path)
    monkeypatch.setattr(sqla_orm, "_masked_fingerprint", count_fingerprint)
    tag = ("test_repeated_lazy_load_inspects_relationship_and_fingerprint_once", 1, "call")
    token = TEST.set(tag)
    try:
        assert sqla.attach_session() is True
        with orm.Session(engine) as session:
            parents = list(session.scalars(sa.select(Parent)))
            calls.update(path=0, fingerprint=0)  # the parent SELECT is not a lazy load
            for parent in parents:
                list(parent.children)
        groups = dict(sqla_orm._relationship_groups[tag])
        assert calls["path"] == 1, f"relationship path read {calls['path']} times for 10 identical lazy loads"
        assert calls["fingerprint"] == 1, f"statement fingerprinted {calls['fingerprint']} times for 10 lazy loads"
        assert list(groups.values()) == [("Parent.children", True)]
    finally:
        sqla.detach_session()
        TEST.reset(token)


def test_listener_failure_does_not_change_query_result(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = sa.create_engine("sqlite://")
    orm = pytest.importorskip("sqlalchemy.orm")
    Base = orm.declarative_base()

    class Parent(Base):
        __tablename__ = "orm_parent"
        id = sa.Column(sa.Integer, primary_key=True)
        children = orm.relationship("Child")

    class Child(Base):
        __tablename__ = "orm_child"
        id = sa.Column(sa.Integer, primary_key=True)
        parent_id = sa.Column(sa.Integer, sa.ForeignKey("orm_parent.id"))

    Base.metadata.create_all(engine)
    with orm.Session(engine) as session:
        session.add(Parent(children=[Child()]))
        session.commit()

    _install(engines=[engine])

    def fail() -> str | None:
        raise RuntimeError("frame inspection failed")

    monkeypatch.setattr(sqla_orm, "_first_application_location", fail)
    token = TEST.set(("test_listener_failure", 1, "call"))
    try:
        assert sqla.attach_session() is True
        with orm.Session(engine) as session:
            assert len(session.query(Parent).one().children) == 1
    finally:
        sqla.detach_session()
        TEST.reset(token)


def test_first_application_location_is_cached_per_relationship(monkeypatch: pytest.MonkeyPatch) -> None:
    orm = pytest.importorskip("sqlalchemy.orm")
    engine = sa.create_engine("sqlite://")
    Base = orm.declarative_base()

    class Parent(Base):
        __tablename__ = "location_parent"
        id = sa.Column(sa.Integer, primary_key=True)
        children = orm.relationship("Child")

    class Child(Base):
        __tablename__ = "location_child"
        id = sa.Column(sa.Integer, primary_key=True)
        parent_id = sa.Column(sa.Integer, sa.ForeignKey("location_parent.id"))

    Base.metadata.create_all(engine)
    with orm.Session(engine) as session:
        session.add_all(Parent(children=[Child()]) for _ in range(10))
        session.commit()
    _install(engines=[engine])

    original = sqla_orm._first_application_location
    calls = 0

    def count_location() -> str | None:
        nonlocal calls
        calls += 1
        return original()

    monkeypatch.setattr(sqla_orm, "_first_application_location", count_location)
    token = TEST.set(("test_first_application_location_is_cached_per_relationship", 1, "call"))
    try:
        assert sqla.attach_session() is True
        with orm.Session(engine) as session:
            for parent in session.scalars(sa.select(Parent)):
                list(parent.children)
        assert calls == 1, f"expected one source stack walk for one relationship, got {calls}"
    finally:
        sqla.detach_session()
        TEST.reset(token)


def test_relationship_facts_use_masked_statement_fingerprint() -> None:
    from sharpit.engine.capture.statement import masked_shape
    from sharpit.engine.testsession.sink import report_masker

    statement = "SELECT * FROM payments WHERE api_key = ?"
    tag = ("test_relationship_facts_use_masked_statement_fingerprint", 1, "call")
    context = types.SimpleNamespace(
        execution_options={sqla.RELATIONSHIP_KEY: ("Payment.refunds", True)},
        statement=statement,
    )
    token = TEST.set(tag)
    try:
        sqla_orm._record_relationship(context)
        masked_fingerprint = masked_shape(report_masker(), statement, Dialect.UNSUPPORTED).fingerprint
        assert sqla_orm._relationship_groups[tag].get(masked_fingerprint) == ("Payment.refunds", True)
    finally:
        sqla_orm._relationship_loads.pop(tag, None)
        sqla_orm._relationship_groups.pop(tag, None)
        sqla_orm._relationship_sites.pop(tag, None)
        TEST.reset(token)


# derived: release council fix round 2: the group key must equal the sink's, which reads the text as MySQL's
def test_relationship_facts_on_mysql_use_the_mysql_fingerprint() -> None:
    from sharpit.engine.capture.statement import masked_shape
    from sharpit.engine.testsession.sink import report_masker

    statement = "SELECT * FROM payments # password hunter2"
    tag = ("test_relationship_facts_on_mysql_use_the_mysql_fingerprint", 1, "call")
    context = types.SimpleNamespace(
        execution_options={sqla.RELATIONSHIP_KEY: ("Payment.refunds", True)},
        statement=statement,
        dialect=types.SimpleNamespace(name="mysql"),
    )
    token = TEST.set(tag)
    try:
        sqla_orm._record_relationship(context)
        masked_fingerprint = masked_shape(report_masker(), statement, Dialect.MYSQL_FAMILY).fingerprint
        assert sqla_orm._relationship_groups[tag].get(masked_fingerprint) == ("Payment.refunds", True)
    finally:
        sqla_orm._relationship_loads.pop(tag, None)
        sqla_orm._relationship_groups.pop(tag, None)
        sqla_orm._relationship_sites.pop(tag, None)
        sqla_orm._statement_sites.pop(tag, None)
        TEST.reset(token)


SQLITE_STATEMENT = 'SELECT "id" FROM "payments"'


@pytest.fixture
def relationship_tag(request: pytest.FixtureRequest) -> Iterator[tuple[str, int, str]]:
    tag = (request.node.name, 1, "call")
    token = TEST.set(tag)
    yield tag
    TEST.reset(token)
    sqla.set_identity_key(None)
    for store in (
        sqla_orm._relationship_loads,
        sqla_orm._relationship_groups,
        sqla_orm._relationship_sites,
        sqla_orm._statement_sites,
        sqla_orm._eager_relationship_batches,
    ):
        store.pop(tag, None)


def _sqlite_relationship_context() -> Any:
    return types.SimpleNamespace(
        execution_options={sqla.RELATIONSHIP_KEY: ("Payment.refunds", True)},
        statement=SQLITE_STATEMENT,
        dialect=types.SimpleNamespace(name="sqlite"),
    )


def test_a_sqlite_relationship_group_is_the_sinks_group(relationship_tag: tuple[str, int, str]) -> None:
    from sharpit.engine.capture.statement import masked_shape

    sqla.set_identity_key(b"k" * 32)
    sqla_orm._record_relationship(_sqlite_relationship_context())
    masker = Masker(Exposure.MASKED, True, identity_key=b"k" * 32)
    expected = masked_shape(masker, SQLITE_STATEMENT, Dialect.SQLITE).fingerprint
    assert list(sqla_orm._relationship_groups.get(relationship_tag, ())) == [expected]


def test_a_new_key_reaches_a_sqlite_statement_seen_before_it(relationship_tag: tuple[str, int, str]) -> None:
    sqla.set_identity_key(b"a" * 32)
    first = sqla_orm._masked_fingerprint(SQLITE_STATEMENT, Dialect.SQLITE)
    sqla.set_identity_key(b"b" * 32)
    assert sqla_orm._masked_fingerprint(SQLITE_STATEMENT, Dialect.SQLITE) != first


def test_a_keyless_sqlite_relationship_is_not_grouped(relationship_tag: tuple[str, int, str]) -> None:
    sqla_orm._record_relationship(_sqlite_relationship_context())
    assert relationship_tag not in sqla_orm._relationship_groups


def test_a_keyless_sqlite_eager_batch_is_not_counted(relationship_tag: tuple[str, int, str]) -> None:
    sqla_orm._count_eager_batch(relationship_tag, SQLITE_STATEMENT, Dialect.SQLITE)
    assert relationship_tag not in sqla_orm._eager_relationship_batches


MYSQL_STATEMENT = "SELECT * FROM payments # password hunter2"


def _mysql_fingerprint() -> str:
    from sharpit.engine.capture.statement import masked_shape
    from sharpit.engine.testsession.sink import report_masker

    return masked_shape(report_masker(), MYSQL_STATEMENT, Dialect.MYSQL_FAMILY).fingerprint


def _mysql_context(options: dict[str, Any]) -> Any:
    return types.SimpleNamespace(
        execution_options=options, statement=MYSQL_STATEMENT, dialect=types.SimpleNamespace(name="mysql")
    )


def _pop_facts(tag: tuple[str, int, str]) -> None:
    for store in (
        sqla_orm._relationship_groups,
        sqla_orm._relationship_sites,
        sqla_orm._eager_relationship_batches,
        sqla_orm._statement_sites,
        sqla_orm._lazy_seen,
    ):
        store.pop(tag, None)


# derived: Task 12 review: the statement-site key carries the dialect the phase's select counts were read with
def test_repeated_mysql_statement_site_lands_on_the_mysql_group() -> None:
    tag = ("test_repeated_mysql_statement_site_lands_on_the_mysql_group", 1, "call")
    group = _mysql_fingerprint()
    phase = types.SimpleNamespace(
        selects={group: 2},
        sql_of={},
        relationship_of={},
        relationship_sites={},
        relationship_loads={},
        statement_sites={},
    )
    test = types.SimpleNamespace(key=types.SimpleNamespace(node_id=tag[0], attempt=tag[1]), phases={"call": phase})
    token = TEST.set(tag)
    try:
        for _ in range(2):  # the first run names the statement, its first repeat records the site
            sqla_orm._record_relationship(_mysql_context({}))
        sqla.apply_relationship_facts(test)
        assert list(phase.statement_sites) == [group]
    finally:
        _pop_facts(tag)
        TEST.reset(token)


# derived: Task 12 review: an eager batch is subtracted from the group the sink counted, read as MySQL
def test_mysql_eager_batch_counts_on_the_mysql_group() -> None:
    tag = ("test_mysql_eager_batch_counts_on_the_mysql_group", 1, "call")
    token = TEST.set(tag)
    try:
        sqla_orm._record_relationship(_mysql_context({sqla.RELATIONSHIP_KEY: sqla_orm._EAGER_RELATIONSHIP_KEY}))
        assert sqla_orm._eager_relationship_batches[tag] == {_mysql_fingerprint(): 1}
    finally:
        _pop_facts(tag)
        TEST.reset(token)


# derived: release council fix round 2: the unbounded-read shape is shown in the report
def test_unbounded_read_shape_on_mysql_folds_the_comment() -> None:
    dialect = types.SimpleNamespace(name="mysql")
    context = types.SimpleNamespace(session=types.SimpleNamespace(bind=types.SimpleNamespace(dialect=dialect)))

    statement, _has_limit = sqla_orm._unbounded_read_statement_shape(context, "SELECT 1 # password hunter2")

    assert "hunter2" not in statement


def test_relationship_facts_tolerate_missing_call_phase() -> None:
    tag = ("test_relationship_facts_tolerate_missing_call_phase", 1, "call")
    sqla_orm._relationship_groups[tag] = {"statement-fingerprint": ("Player.performances", True)}
    test = types.SimpleNamespace(
        key=types.SimpleNamespace(node_id=tag[0], attempt=tag[1]),
        phases={},
    )
    try:
        missing_phase_guarded = True
        try:
            sqla.apply_relationship_facts(test)
        except KeyError:
            missing_phase_guarded = False
        assert missing_phase_guarded, "missing call phase must not raise KeyError"
    finally:
        sqla_orm._relationship_groups.pop(tag, None)


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
    # owner ruling 2026-11-07, structured driver codes: the class and its code, never the driver's text
    assert "sqlite3.OperationalError" in entry["errorMessage"]
    assert "SQLITE_ERROR" in entry["errorMessage"]
    assert "no such table" not in entry["errorMessage"]


def test_detach_removes_listeners_only_when_last_context_leaves():
    sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    first, second = _install(), _install()
    assert all(sqla.attached().values())
    first.uninstall_capture()
    assert all(sqla.attached().values())  # the second context still traces
    second.uninstall_capture()
    assert not any(sqla.attached().values())


def test_run_db_read_sync_and_async_not_traced(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'sync.db'}")
    asyncio_ext = pytest.importorskip("sqlalchemy.ext.asyncio")
    async_engine = asyncio_ext.create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'async.db'}")
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


def test_run_db_read_times_out(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'app.db'}")

    def slow(_conn: Any) -> None:
        import time

        time.sleep(0.5)

    async def main() -> None:
        await sqla.run_db_read(engine, slow, 0.05)

    with pytest.raises(TimeoutError):
        asyncio.run(main())


def test_run_db_read_done_once_the_worker_thread_really_returns(tmp_path: Path):
    # spec §7.6 / §7.8: single-flight is held until the read actually returns, not when the caller gives up
    import threading
    from concurrent.futures import ThreadPoolExecutor

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'app.db'}")
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


def test_run_db_read_done_on_the_async_path(tmp_path: Path):
    asyncio_ext = pytest.importorskip("sqlalchemy.ext.asyncio")
    async_engine = asyncio_ext.create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
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


class _Ctx:
    context_id = "feedc0de00000000"
    engines: tuple[()] = ()
    capture = types.SimpleNamespace(engine_registry=None)


def test_collected_context_detaches_listeners():
    """Review finding 6: a context dropped without ``remove`` must not keep the class-level listeners on."""
    sqla.detach_all()
    ctx = _Ctx()
    assert sqla.add(ctx, statements=True, discovery=False) is True  # type: ignore[arg-type]
    assert sqla.attached()["before_cursor_execute"] is True
    del ctx
    gc.collect()
    sqla.detach_session()  # any listener sync prunes the dead context
    assert not any(sqla.attached().values())


def _paging_request(request_id: str) -> RequestInfo:
    route = types.SimpleNamespace(
        path="/teams",
        dependant=types.SimpleNamespace(query_params=[types.SimpleNamespace(alias="limit")]),
    )
    return RequestInfo(
        request_id,
        "test-context",
        "GET",
        "/teams",
        None,
        0,
        None,
        scope={"route": route, "query_string": b"limit=2"},
    )


class _LoadContext:
    def __init__(self, statement: Any) -> None:
        self.query = statement
        self.compiled = types.SimpleNamespace(statement=statement)


def _load_context(statement: Any) -> Any:
    return _LoadContext(statement)


def _unbounded_test(node_id: str) -> Any:
    return types.SimpleNamespace(
        key=types.SimpleNamespace(node_id=node_id, attempt=1),
        budget=types.SimpleNamespace(unbounded_read_factor=2),
        phases={},
    )


def test_load_counts_are_per_statement():
    first = sa.select(sa.literal(1))
    second = sa.select(sa.literal(2))
    info = _paging_request("request-statement")
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-statement", 1, "call"))
    try:
        sqla_orm._mapper_load(types.SimpleNamespace(), _load_context(first))
        sqla_orm._mapper_load(types.SimpleNamespace(), _load_context(second))
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    assert len(info.loads) == 2
    assert sqla.apply_unbounded_read_facts(_unbounded_test("test-statement")) is False


def test_load_counts_keep_statement_identity_when_ids_are_reused(monkeypatch: pytest.MonkeyPatch):
    info = _paging_request("request-statement-identity")
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-statement-identity", 1, "call"))
    monkeypatch.setattr(sqla_orm, "id", lambda _context: 1, raising=False)
    try:
        sqla_orm._mapper_load(types.SimpleNamespace(), _load_context(sa.select(sa.literal(1))))
        sqla_orm._mapper_load(types.SimpleNamespace(), _load_context(sa.select(sa.literal(2))))
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    assert len(info.loads) == 2
    sqla_orm._unbounded_read_facts.pop(("test-statement-identity", 1, "call"), None)


def test_unbounded_read_facts_keep_request_identity_when_context_ids_are_reused_current(
    monkeypatch: pytest.MonkeyPatch,
):
    first = _paging_request("request-statement-identity-current-first")
    second = _paging_request("request-statement-identity-current-second")
    context = _load_context(sa.select(sa.literal(1)))
    tag = ("test-statement-identity-current", 1, "call")
    monkeypatch.setattr(sqla_orm, "id", lambda _context: 1, raising=False)
    test_token = TEST.set(tag)
    try:
        for info in (first, second):
            request_token = REQUEST.set(info)
            try:
                for _ in range(4):
                    sqla_orm._mapper_load(types.SimpleNamespace(), context)
            finally:
                REQUEST.reset(request_token)
    finally:
        TEST.reset(test_token)

    facts = sqla_orm._unbounded_read_facts.pop(tag, {})
    assert len(facts) == 2


def test_load_compiles_and_masks_statement_once(monkeypatch: pytest.MonkeyPatch):
    from sharpit.engine import sqltext

    calls = 0
    statement_shape = sqltext.statement_shape

    def counted_shape(masker: Any, statement: str, dialect: Dialect) -> Any:
        nonlocal calls
        calls += 1
        return statement_shape(masker, statement, dialect)

    monkeypatch.setattr(sqltext, "statement_shape", counted_shape)
    info = _paging_request("request-statement-shape")
    context = _load_context(sa.select(sa.literal(1)))
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-statement-shape", 1, "call"))
    try:
        for _ in range(50):
            sqla_orm._mapper_load(types.SimpleNamespace(), context)
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    assert calls == 1
    sqla_orm._unbounded_read_facts.pop(("test-statement-shape", 1, "call"), None)


def test_load_compiles_and_masks_statement_once_current(monkeypatch: pytest.MonkeyPatch):
    from sharpit.engine import sqltext

    calls = 0
    statement_shape = sqltext.statement_shape

    def counted_shape(masker: Any, statement: str, dialect: Dialect) -> Any:
        nonlocal calls
        calls += 1
        return statement_shape(masker, statement, dialect)

    monkeypatch.setattr(sqltext, "statement_shape", counted_shape)
    info = _paging_request("request-statement-shape-current")
    context = _load_context(sa.select(sa.literal(1)))
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-statement-shape-current", 1, "call"))
    try:
        for _ in range(50):
            sqla_orm._mapper_load(types.SimpleNamespace(), context)
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    assert calls == 1
    sqla_orm._unbounded_read_facts.pop(("test-statement-shape-current", 1, "call"), None)


@pytest.mark.parametrize("loader", ["selectin", "joined", "lazy"])
def test_relationship_rows_are_not_counted_as_parent_page_rows(loader: str):
    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Session, joinedload, relationship, selectinload

    class Base(sa.orm.DeclarativeBase):
        pass

    class Team(Base):
        __tablename__ = f"teams_{loader}"
        id = sa.Column(sa.Integer, primary_key=True)
        members = relationship("Member", back_populates="team")

    class Member(Base):
        __tablename__ = f"members_{loader}"
        id = sa.Column(sa.Integer, primary_key=True)
        team_id = sa.Column(ForeignKey(f"teams_{loader}.id"))
        team = relationship(Team, back_populates="members")

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(Team(members=[Member() for _ in range(4)]) for _ in range(5))
        session.commit()

    sqla.attach_session()
    info = _paging_request(f"request-relationship-{loader}")
    request_token = REQUEST.set(info)
    test_token = TEST.set((f"test-relationship-{loader}", 1, "call"))
    try:
        with Session(engine) as session:
            statement = sa.select(Team).limit(5)
            if loader == "selectin":
                statement = statement.options(selectinload(Team.members))
            elif loader == "joined":
                statement = statement.options(joinedload(Team.members))
            teams = session.scalars(statement).unique().all()
            if loader == "lazy":
                _ = [member for team in teams for member in team.members]
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)
        sqla.detach_session()

    facts = sqla_orm._unbounded_read_facts.pop((f"test-relationship-{loader}", 1, "call"), {})
    assert len(teams) == 5
    assert all(fact.entity == "Team" for fact in facts.values())
    assert sum(fact.loaded for fact in facts.values()) == 5


@pytest.mark.parametrize("loader", ["selectin", "joined", "lazy"])
def test_relationship_loads_do_not_create_unbounded_findings(loader: str):
    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Session, joinedload, relationship, selectinload

    from sharpit.engine.testsession.facts import TestFacts, TestKey
    from sharpit.engine.testsession.gates import Budget, evaluate_test

    class Base(sa.orm.DeclarativeBase):
        pass

    class Team(Base):
        __tablename__ = f"teams_gate_{loader}"
        id = sa.Column(sa.Integer, primary_key=True)
        members = relationship("Member", back_populates="team")

    class Member(Base):
        __tablename__ = f"members_gate_{loader}"
        id = sa.Column(sa.Integer, primary_key=True)
        team_id = sa.Column(ForeignKey(f"teams_gate_{loader}.id"))
        team = relationship(Team, back_populates="members")

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(Team(members=[Member() for _ in range(4)]) for _ in range(5))
        session.commit()

    sqla.attach_session()
    info = _paging_request(f"request-relationship-gate-{loader}")
    request_token = REQUEST.set(info)
    test_token = TEST.set((f"test-relationship-gate-{loader}", 1, "call"))
    try:
        with Session(engine) as session:
            statement = sa.select(Team).limit(5)
            if loader == "selectin":
                statement = statement.options(selectinload(Team.members))
            elif loader == "joined":
                statement = statement.options(joinedload(Team.members))
            teams = session.scalars(statement).unique().all()
            if loader == "lazy":
                _ = [member for team in teams for member in team.members]
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    test = _unbounded_test(f"test-relationship-gate-{loader}")
    missing_capture = sqla.apply_unbounded_read_facts(test)
    sqla.detach_session()
    facts = TestFacts(TestKey(f"test-relationship-gate-{loader}", "gw0", 1), test.phases)
    assert missing_capture is False
    assert len(teams) == 5
    assert not any(fact.entity == "Member" for fact in facts.phases["call"].unbounded_reads)
    assert evaluate_test(facts, Budget(None, False, 0), 5, ()) == []


@pytest.mark.parametrize("loader", ["selectin", "joined", "lazy"])
def test_relationship_loads_do_not_create_unbounded_findings_current(loader: str):
    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Session, joinedload, relationship, selectinload

    from sharpit.engine.testsession.facts import TestFacts, TestKey
    from sharpit.engine.testsession.gates import Budget, evaluate_test

    class Base(sa.orm.DeclarativeBase):
        pass

    class Team(Base):
        __tablename__ = f"teams_gate_current_{loader}"
        id = sa.Column(sa.Integer, primary_key=True)
        members = relationship("Member", back_populates="team")

    class Member(Base):
        __tablename__ = f"members_gate_current_{loader}"
        id = sa.Column(sa.Integer, primary_key=True)
        team_id = sa.Column(ForeignKey(f"teams_gate_current_{loader}.id"))
        team = relationship(Team, back_populates="members")

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(Team(members=[Member() for _ in range(4)]) for _ in range(5))
        session.commit()

    sqla.attach_session()
    info = _paging_request(f"request-relationship-gate-current-{loader}")
    request_token = REQUEST.set(info)
    test_token = TEST.set((f"test-relationship-gate-current-{loader}", 1, "call"))
    try:
        with Session(engine) as session:
            statement = sa.select(Team).limit(5)
            if loader == "selectin":
                statement = statement.options(selectinload(Team.members))
            elif loader == "joined":
                statement = statement.options(joinedload(Team.members))
            teams = session.scalars(statement).unique().all()
            if loader == "lazy":
                _ = [member for team in teams for member in team.members]
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    test = _unbounded_test(f"test-relationship-gate-current-{loader}")
    missing_capture = sqla.apply_unbounded_read_facts(test)
    sqla.detach_session()
    facts = TestFacts(TestKey(f"test-relationship-gate-current-{loader}", "gw0", 1), test.phases)
    assert missing_capture is False
    assert len(teams) == 5
    assert not any(fact.entity == "Member" for fact in facts.phases["call"].unbounded_reads)
    assert evaluate_test(facts, Budget(None, False, 0), 5, ()) == []


def test_load_counts_are_scoped_to_request():
    first_request = _paging_request("request-one")
    second_request = _paging_request("request-two")
    context = _load_context(sa.select(sa.literal(1)))
    test_token = TEST.set(("test-request-scope", 1, "call"))
    try:
        request_token = REQUEST.set(first_request)
        sqla_orm._mapper_load(types.SimpleNamespace(), context)
        REQUEST.reset(request_token)
        request_token = REQUEST.set(second_request)
        sqla_orm._mapper_load(types.SimpleNamespace(), context)
        REQUEST.reset(request_token)
    finally:
        TEST.reset(test_token)

    assert first_request.id != second_request.id
    assert len(first_request.loads) == 1
    assert len(second_request.loads) == 1
    assert sqla.apply_unbounded_read_facts(_unbounded_test("test-request-scope")) is False


def test_multiple_entities_count_separately():
    class Team:
        pass

    class Owner:
        pass

    info = _paging_request("request-entities")
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-entities", 1, "call"))
    try:
        context = _load_context(sa.select(sa.literal(1)))
        sqla_orm._mapper_load(Team(), context)
        sqla_orm._mapper_load(Owner(), context)
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    entities = {entity for by_entity in info.loads.values() for entity in by_entity}
    assert entities == {"Team", "Owner"}
    assert sqla.apply_unbounded_read_facts(_unbounded_test("test-entities")) is False


@pytest.mark.parametrize(
    "statement",
    [sa.select(sa.literal(1)).limit(5), sa.select(sa.literal(1)).fetch(5)],
    ids=["limit", "fetch"],
)
def test_select_with_limit_or_fetch_is_not_flagged(statement: Any):
    info = _paging_request("request-limited")
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-limited", 1, "call"))
    try:
        context = _load_context(statement)
        for _ in range(4):
            sqla_orm._mapper_load(types.SimpleNamespace(), context)
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    test = _unbounded_test("test-limited")
    assert sqla.apply_unbounded_read_facts(test) is False
    assert all(fact.has_limit for fact in test.phases["call"].unbounded_reads)


def test_non_paged_route_is_not_flagged():
    route = types.SimpleNamespace(
        path="/teams",
        dependant=types.SimpleNamespace(query_params=[types.SimpleNamespace(alias="search")]),
    )
    info = RequestInfo(
        "request-non-paged",
        "test-context",
        "GET",
        "/teams",
        None,
        0,
        None,
        scope={
            "route": route,
            "query_string": b"search=x",
        },
    )
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-non-paged", 1, "call"))
    try:
        sqla_orm._mapper_load(types.SimpleNamespace(), _load_context(sa.select(sa.literal(1))))
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    assert info.loads == {}
    assert ("test-non-paged", 1, "call") not in sqla_orm._unbounded_read_facts


def test_paging_route_without_bound_page_size_does_not_guess():
    route = types.SimpleNamespace(
        path="/teams",
        dependant=types.SimpleNamespace(query_params=[types.SimpleNamespace(alias="page")]),
    )
    info = RequestInfo(
        "request-no-page-size",
        "test-context",
        "GET",
        "/teams",
        None,
        0,
        None,
        scope={"route": route, "query_string": b"page=3"},
    )
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-no-page-size", 1, "call"))
    try:
        sqla_orm._mapper_load(types.SimpleNamespace(), _load_context(sa.select(sa.literal(1))))
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    assert info.loads == {}
    assert ("test-no-page-size", 1, "call") not in sqla_orm._unbounded_read_facts


def test_unbounded_read_fact_drops_sql_values():
    info = _paging_request("request-masked-sql")
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-masked-sql", 1, "call"))
    try:
        statement = sa.text("SELECT 'hunter2-secret' AS token")
        context = _load_context(statement)
        for _ in range(4):
            sqla_orm._mapper_load(types.SimpleNamespace(), context)
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)

    test = _unbounded_test("test-masked-sql")
    assert sqla.apply_unbounded_read_facts(test) is False
    payload = json.dumps([fact.to_json() for fact in test.phases["call"].unbounded_reads])
    assert "hunter2-secret" not in payload
    assert "parameters" not in payload


def test_listener_does_not_change_query_results():
    from sqlalchemy.orm import Session

    class Base(sa.orm.DeclarativeBase):
        pass

    class Record(Base):
        __tablename__ = "listener_results"
        id = sa.Column(sa.Integer, primary_key=True)

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sqla.attach_session()
    info = _paging_request("request-result")
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-query-result", 1, "call"))
    try:
        with Session(engine) as session:
            session.add_all([Record(), Record()])
            session.commit()
            result = session.scalars(sa.select(Record)).all()
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)
        sqla.detach_session()

    assert len(result) == 2
    assert [record.id for record in result] == [1, 2]


def test_mapper_load_listener_attaches_once_and_detaches():
    from sqlalchemy.orm import Session

    class Base(sa.orm.DeclarativeBase):
        pass

    class Record(Base):
        __tablename__ = "mapper_listener_lifecycle"
        id = sa.Column(sa.Integer, primary_key=True)

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Record())
        session.commit()

    sqla.detach_session()
    assert sqla.attach_session() is True
    assert sqla.attach_session() is True
    assert sa.event.contains(sa.orm.Mapper, "load", sqla_orm._mapper_load)
    info = _paging_request("request-listener-lifecycle")
    request_token = REQUEST.set(info)
    test_token = TEST.set(("test-listener-lifecycle", 1, "call"))
    try:
        with Session(engine) as session:
            rows = session.scalars(sa.select(Record)).all()
    finally:
        TEST.reset(test_token)
        REQUEST.reset(request_token)
        sqla.detach_session()

    loaded = sum(state["loaded"] for by_entity in info.loads.values() for state in by_entity.values())
    assert len(rows) == 1
    assert loaded == 1
    assert not sa.event.contains(sa.orm.Mapper, "load", sqla_orm._mapper_load)


def test_identity_map_hits_are_not_counted():
    from sqlalchemy.orm import Session

    class Base(sa.orm.DeclarativeBase):
        pass

    class Record(Base):
        __tablename__ = "identity_map_loads"
        id = sa.Column(sa.Integer, primary_key=True)

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sqla.attach_session()
    with Session(engine) as session:
        session.add_all([Record(), Record()])
        session.commit()
        info = _paging_request("request-identity-map")
        request_token = REQUEST.set(info)
        test_token = TEST.set(("test-identity-map", 1, "call"))
        try:
            first = session.scalars(sa.select(Record)).all()
            first_count = sum(state["loaded"] for by_entity in info.loads.values() for state in by_entity.values())
            second = session.scalars(sa.select(Record)).all()
            second_count = sum(state["loaded"] for by_entity in info.loads.values() for state in by_entity.values())
        finally:
            TEST.reset(test_token)
            REQUEST.reset(request_token)
            sqla.detach_session()

    assert len(first) == 2
    assert len(second) == 2
    assert first_count == 2
    assert second_count == first_count
