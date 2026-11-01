"""The raw sqlite3 source (spec 0.3.0 §8.2-8.4, hardening rows A2-A7).

Every case is derived: BootUI wraps a JDBC ``DataSource``, so there is no BootUI oracle for a driver swap.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import subprocess
import sys
import threading
import types
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from sharpit.engine import sqla
from sharpit.engine.capture.sqltrace import category_of
from sharpit.engine.sources import dispatch, sqlite
from sharpit.engine.sources.dispatch import SqlEvent

REAL_CONNECT = sqlite3.connect
HOLDER = "test"


class Sink:
    def __init__(self) -> None:
        self.events: list[SqlEvent] = []

    def on_sql(self, event: SqlEvent, test: tuple[str, int, str] | None) -> None:
        del test
        self.events.append(event)

    def on_exception(self, exc: BaseException, source: str, test: tuple[str, int, str] | None) -> None:
        del exc, source, test

    def on_escaped(self, exc: BaseException) -> None:
        del exc

    def register_app(self, app: object) -> None:
        del app


@pytest.fixture(autouse=True)
def _stdlib_restored() -> Iterator[None]:
    yield
    sqlite.detach_all()  # also drops the cached scan, so each test counts its own early connections
    sqlite3.connect = REAL_CONNECT  # a test that re-patched on purpose
    dispatch.set_session_sink(None)
    sqla.detach_session()


@pytest.fixture
def sink() -> Sink:
    sink = Sink()
    dispatch.set_session_sink(sink)
    return sink


@pytest.fixture
def conn(sink: Sink) -> Iterator[sqlite3.Connection]:
    assert sqlite.attach(HOLDER) is True
    connection = sqlite3.connect(":memory:")
    connection.execute("create table t (n integer)")
    sink.events.clear()
    yield connection
    connection.close()


def test_conn_execute_traced(conn: sqlite3.Connection, sink: Sink):
    conn.execute("insert into t values (?)", (5,))
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.source == "sqlite3"
    assert event.sql == "insert into t values (?)"
    assert event.parameters == (5,)
    assert event.rowcount == 1
    assert event.error is None
    assert event.connection_id == hex(id(conn))


def test_cursor_execute_traced(conn: sqlite3.Connection, sink: Sink):
    conn.cursor().execute("insert into t values (:n)", {"n": 6})
    assert [(e.source, e.sql, e.parameters) for e in sink.events] == [
        ("sqlite3", "insert into t values (:n)", {"n": 6})
    ]


def test_cursor_from_conn_execute_stays_traced(conn: sqlite3.Connection, sink: Sink):
    cur = conn.execute("insert into t values (1)")
    cur.execute("insert into t values (2)")
    assert [e.sql for e in sink.events] == ["insert into t values (1)", "insert into t values (2)"]


def test_executemany_one_event_batch_size(conn: sqlite3.Connection, sink: Sink):
    conn.executemany("insert into t values (?)", [(1,), (2,), (3,)])
    assert len(sink.events) == 1
    assert sink.events[0].executemany is True
    assert sink.events[0].batch_size == 3
    assert sink.events[0].rowcount == 3


def test_executescript_one_event_first_statement_category(conn: sqlite3.Connection, sink: Sink):
    script = "create table u (n integer); insert into u values (1);"
    conn.executescript(script)
    assert len(sink.events) == 1
    assert sink.events[0].sql == script
    assert category_of(sink.events[0].sql) == "DDL"
    assert sink.events[0].executemany is False


def test_executemany_generator_parameters(conn: sqlite3.Connection, sink: Sink):
    conn.executemany("insert into t values (?)", ((i,) for i in range(4)))
    assert conn.execute("select count(*) from t").fetchone() == (4,)
    assert sink.events[0].batch_size is None
    assert sink.events[0].executemany is True


def test_error_emitted_then_reraised_same_type(conn: sqlite3.Connection, sink: Sink):
    with pytest.raises(sqlite3.OperationalError, match="no such table") as caught:
        conn.execute("select * from missing")
    assert len(sink.events) == 1
    assert sink.events[0].error is caught.value
    assert sink.events[0].rowcount == -1


def test_caller_factory_subclass_traced(sink: Sink):
    class MyConnection(sqlite3.Connection):
        pass

    sqlite.attach(HOLDER)
    mine = sqlite3.connect(":memory:", factory=MyConnection)
    assert isinstance(mine, MyConnection)
    mine.execute("select 1")
    assert [e.sql for e in sink.events] == ["select 1"]
    mine.close()


def test_caller_factory_not_subclass_passed_through_with_limitation(sink: Sink):
    def factory(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        return sqlite3.Connection(*args, **kwargs)

    sqlite.attach(HOLDER)
    plain = sqlite3.connect(":memory:", factory=factory)
    plain.execute("select 1")
    assert sink.events == []
    assert any("factory" in line for line in sqlite.limitations())
    plain.close()


def test_caller_cursor_class_traced(conn: sqlite3.Connection, sink: Sink):
    class MyCursor(sqlite3.Cursor):
        pass

    cur = conn.cursor(MyCursor)
    assert isinstance(cur, MyCursor)
    cur.execute("select 1")
    assert [e.sql for e in sink.events] == ["select 1"]


def test_never_uses_trace_callback(monkeypatch: pytest.MonkeyPatch, sink: Sink):
    """A4: ``set_trace_callback`` expands bound values the masker cannot see, so it is never called."""
    calls: list[object] = []
    monkeypatch.setattr(sqlite.TracedConnection, "set_trace_callback", lambda *a: calls.append(a), raising=False)
    sqlite.attach(HOLDER)
    traced = sqlite3.connect(":memory:")
    traced.execute("select ?", ("sk_live_" + "a" * 24,))
    assert len(sink.events) == 1
    assert calls == []
    traced.close()


def test_attach_idempotent_detach_own_only(caplog: pytest.LogCaptureFixture):
    """A5: a second attach does nothing; detach restores only sharpit's own function."""
    assert sqlite.attach(HOLDER) is True
    patched = sqlite3.connect
    assert sqlite.attach(HOLDER) is False
    assert sqlite3.connect is patched

    def foreign(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        return patched(*args, **kwargs)

    sqlite3.connect = foreign
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        assert sqlite.detach(HOLDER) is False
    assert sqlite3.connect is foreign
    assert len([r for r in caplog.records if "sqlite3.connect" in r.getMessage()]) == 1
    assert sqlite.is_attached() is False


def test_detach_restores_stdlib_when_last_holder_leaves():
    sqlite.attach(HOLDER)
    sqlite.attach("other")
    assert sqlite.detach(HOLDER) is False
    assert sqlite.is_attached() is True
    assert sqlite.detach("other") is True
    assert sqlite3.connect is REAL_CONNECT


def test_inactive_attach_leaves_stdlib():
    """A2: nothing patched until something attaches."""
    assert sqlite3.connect is REAL_CONNECT
    assert sqlite.is_attached() is False
    assert sqlite.detach(HOLDER) is False
    assert sqlite3.connect is REAL_CONNECT


def test_cross_thread_still_raises_programming_error(sink: Sink):
    """A7: ``check_same_thread`` is untouched: the traced connection fails exactly like the stdlib one."""

    def use_from_thread(connection: sqlite3.Connection) -> str:
        found: list[str] = []

        def run() -> None:
            try:
                connection.execute("select 1")
            except sqlite3.ProgrammingError as exc:
                found.append(re.sub(r"\d+", "N", str(exc)))  # the thread ids differ

        thread = threading.Thread(target=run)
        thread.start()
        thread.join()
        return found[0] if found else ""

    stdlib = REAL_CONNECT(":memory:")
    expected = use_from_thread(stdlib)
    sqlite.attach(HOLDER)
    traced = sqlite3.connect(":memory:")
    assert expected.startswith("SQLite objects created in a thread")
    assert use_from_thread(traced) == expected
    assert sink.events == []


def test_sqlalchemy_sqlite_counted_once(sink: Sink):
    """Spec §8.3: SQLAlchemy opens SQLite through ``sqlite3.dbapi2.connect``, so it stays on its own source."""
    sa = pytest.importorskip("sqlalchemy")
    sqlite.attach(HOLDER)
    assert sqla.attach_session() is True
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(sa.text("select 1"))
    assert [e.source for e in sink.events] == ["sqlalchemy"]


def test_sqlalchemy_aiosqlite_counted_once(sink: Sink):
    pytest.importorskip("aiosqlite")
    sa = pytest.importorskip("sqlalchemy")
    from sqlalchemy.ext.asyncio import create_async_engine

    sqlite.attach(HOLDER)
    assert sqla.attach_session() is True

    async def run() -> None:
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.connect() as connection:
            await connection.execute(sa.text("select 1"))
        await engine.dispose()

    asyncio.run(run())
    assert [e.source for e in sink.events] == ["sqlalchemy"]


def _module_named(name: str) -> Callable[[], sqlite3.Connection]:
    namespace: dict[str, Any] = {"__name__": name}
    exec("import sqlite3\ndef open_():\n    return sqlite3.connect(':memory:')\n", namespace)  # noqa: S102
    return namespace["open_"]


@pytest.mark.parametrize("caller", ["coverage.sqlitedb", "_pytest.cacheprovider", "aiosqlite.core"])
def test_coverage_and_pytest_connections_untraced(caller: str, sink: Sink):
    sqlite.attach(HOLDER)
    untraced = _module_named(caller)()
    untraced.execute("select 1")
    assert type(untraced) is sqlite3.Connection
    assert sink.events == []
    untraced.close()


def test_preexisting_connections_counted():
    early = REAL_CONNECT(":memory:")
    sqlite.attach(HOLDER)
    assert sqlite.preexisting_connections() >= 1
    early.close()


def test_preexisting_count_excludes_coverage_owned_connection():
    """A coverage data file opened before attach is not an early application connection."""
    sqlite.attach(HOLDER)
    baseline = sqlite.preexisting_connections()
    sqlite.detach(HOLDER)
    namespace: dict[str, Any] = {"__name__": "coverage.sqlitedb"}
    exec(  # noqa: S102
        "import sqlite3\nclass SqliteDb:\n    def __init__(self):\n        self.con = sqlite3.connect(':memory:')\n",
        namespace,
    )
    owner = namespace["SqliteDb"]()
    sqlite.attach(HOLDER)
    assert sqlite.preexisting_connections() == baseline
    del owner


def test_early_alias_detected(monkeypatch: pytest.MonkeyPatch):
    early = types.ModuleType("early_alias_module")
    early.connect = REAL_CONNECT  # type: ignore[attr-defined]  # what `from sqlite3 import connect` binds
    early.dbapi2_connect = sqlite3.dbapi2.connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "early_alias_module", early)
    sqlite.attach(HOLDER)
    assert "early_alias_module.connect" in sqlite.early_aliases()
    assert "early_alias_module.dbapi2_connect" in sqlite.early_aliases()
    assert "sharpit.engine.sources.sqlite._real" not in sqlite.early_aliases()
    assert not any(alias.startswith(("sqlite3.", "_sqlite3.", "sqlalchemy.")) for alias in sqlite.early_aliases())


def test_traced_connection_survives_detach(sink: Sink):
    """A connection opened while attached keeps working after the patch is gone."""
    sqlite.attach(HOLDER)
    traced = sqlite3.connect(":memory:")
    sqlite.detach(HOLDER)
    assert traced.execute("select 7").fetchone() == (7,)
    traced.close()


class _Hostile:
    """A heap object whose ``__class__`` raises: ``isinstance`` on it runs this property."""

    @property
    def __class__(self) -> type:  # type: ignore[override]
        raise RuntimeError("hostile proxy")


def test_attach_survives_a_hostile_heap_object():
    """Review finding 2: counting pre-existing connections never makes attach raise or leaves half-attached state."""
    hostile = _Hostile()
    assert sqlite.attach(HOLDER) is True
    assert sqlite.is_attached() is True
    assert sqlite3.connect is not REAL_CONNECT
    assert sqlite.attach(HOLDER) is False
    assert sqlite.detach(HOLDER) is True
    assert sqlite3.connect is REAL_CONNECT
    del hostile


def test_attach_count_failure_falls_back_with_limitation(monkeypatch: pytest.MonkeyPatch):
    def boom() -> int:
        raise RuntimeError("heap walk failed")

    monkeypatch.setattr(sqlite, "_count_preexisting", boom)
    assert sqlite.attach(HOLDER) is True
    assert sqlite.preexisting_connections() == 0
    assert sqlite.COUNT_FAILED in sqlite.limitations()


def test_sqlalchemy_creator_connection_counted_once(sink: Sink):
    """Review finding 2: a ``creator`` calling ``sqlite3.connect`` inside SQLAlchemy stays the SQLAlchemy source."""
    sa = pytest.importorskip("sqlalchemy")
    from sqlalchemy.pool import StaticPool

    sqlite.attach(HOLDER)
    assert sqla.attach_session() is True
    engine = sa.create_engine(
        "sqlite://", creator=lambda: sqlite3.connect(":memory:", check_same_thread=False), poolclass=StaticPool
    )
    with engine.connect() as connection:
        for _ in range(3):
            connection.execute(sa.text("select 1"))
    assert [e.source for e in sink.events] == ["sqlalchemy"] * 3


def test_sharpit_imports_without_sqlite3():
    """Review finding 3: a Python without ``_sqlite3`` still imports sharpit and its pytest plugin."""
    code = (
        "import sys\n"
        "sys.modules['sqlite3'] = None\n"
        "sys.modules['_sqlite3'] = None\n"
        "import sharpit\n"
        "import sharpit.pytest_plugin\n"
        "from sharpit.engine.sources import sqlite\n"
        "assert sqlite.attach('x') is False\n"
        "assert sqlite.is_attached() is False\n"
        "assert sqlite.limitations() == ['sqlite3 is not available in this Python build']\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=False)  # noqa: S603
    assert done.stderr.strip().splitlines()[-1:] == []
    assert done.returncode == 0


def test_limitations_does_not_rescan_modules(monkeypatch: pytest.MonkeyPatch):
    """Review finding 5: the module scan runs at attach, not on every SQL Trace GET."""
    sqlite.detach_all()
    calls: list[int] = []
    real_scan = sqlite.early_aliases
    monkeypatch.setattr(sqlite, "early_aliases", lambda: calls.append(1) or real_scan())
    sqlite.attach(HOLDER)
    for _ in range(5):
        sqlite.limitations()
    assert len(calls) == 1
