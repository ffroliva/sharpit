from __future__ import annotations

import gc
import inspect
import logging
import sqlite3
import sys
import threading
import types
from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine.capture.correlation import REQUEST, RequestInfo  # noqa: E402
from sharpit.engine.capture.exceptions import ExceptionStore  # noqa: E402
from sharpit.engine.capture.logtail import SharpitLogHandler  # noqa: E402
from sharpit.engine.capture.traces import SpanBuffer, span_buffer  # noqa: E402
from sharpit.engine.capture.transactions import TransactionRecorder  # noqa: E402
from sharpit.engine.context import SharpitContext, application_family  # noqa: E402
from sharpit.engine.masking import Exposure, Masker  # noqa: E402
from sharpit.engine.probe import run_probe  # noqa: E402
from sharpit.engine.sources import dispatch, sqlite  # noqa: E402
from sharpit.engine.sources.dispatch import SqlEvent  # noqa: E402
from sharpit.engine.sqla.inspect import EngineRegistry  # noqa: E402
from sharpit.engine.sqltext import Dialect  # noqa: E402
from sharpit.fastapi.capture import wiring_of  # noqa: E402

_HANDLES: list[Any] = []


@pytest.fixture(autouse=True)
def _cleanup_handles() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _install(app: FastAPI, **kwargs: Any) -> Any:
    handle = install(app, enabled="ON", show_banner=False, sql_trace_enabled=False, **kwargs)
    _HANDLES.append(handle)
    return handle


def _install_default(app: FastAPI, **kwargs: Any) -> Any:
    handle = install(app, enabled="ON", show_banner=False, **kwargs)
    _HANDLES.append(handle)
    return handle


def _engine(url: str) -> Any:
    if url.startswith("postgresql+"):
        return sa.create_engine(url, module=types.SimpleNamespace(paramstyle="format", __version__="1.30.5"))
    return sa.create_engine(url)


def _registry() -> EngineRegistry:
    return EngineRegistry(Masker(Exposure.MASKED, True))


def _family(registry: EngineRegistry) -> Dialect | None:
    return registry.family()


def _application_family(ctx: SharpitContext) -> Dialect | None:
    return application_family(ctx)


def test_a_collected_engine_leaves_the_family() -> None:
    registry = _registry()
    postgres = _engine("postgresql+pg8000://db/app")
    sqlite = _engine("sqlite://")
    registry.add(postgres)
    registry.add(sqlite)
    assert _family(registry) is None
    del postgres
    gc.collect()
    assert _family(registry) is Dialect.SQLITE


def test_a_replacement_engine_invalidates_the_same_count_cache() -> None:
    registry = _registry()
    postgres = _engine("postgresql+pg8000://db/app")
    registry.add(postgres)
    assert _family(registry) is Dialect.POSTGRESQL
    del postgres
    gc.collect()
    sqlite_engine = _engine("sqlite://")
    registry.add(sqlite_engine)
    assert _family(registry) is Dialect.SQLITE


def test_the_family_follows_a_replaced_dialect() -> None:
    registry = _registry()
    engine = _engine("postgresql+pg8000://db/app")
    registry.add(engine)
    assert _family(registry) is Dialect.POSTGRESQL
    engine.dialect = _engine("sqlite://").dialect
    assert _family(registry) is Dialect.SQLITE


def test_the_family_follows_a_changed_dialect_name() -> None:
    registry = _registry()
    engine = _engine("postgresql+pg8000://db/app")
    registry.add(engine)
    assert _family(registry) is Dialect.POSTGRESQL
    engine.dialect.name = "sqlite"
    assert _family(registry) is Dialect.SQLITE


def test_a_replaced_dialect_of_another_family_hides() -> None:
    registry = _registry()
    first = _engine("postgresql+pg8000://db/app")
    second = _engine("postgresql+pg8000://db/other")
    registry.add(first)
    registry.add(second)
    assert _family(registry) is Dialect.POSTGRESQL
    second.dialect = _engine("sqlite://").dialect
    assert _family(registry) is None


def test_a_changed_name_outside_the_table_hides() -> None:
    registry = _registry()
    engine = _engine("postgresql+pg8000://db/app")
    registry.add(engine)
    engine.dialect.name = "cockroachdb"
    assert _family(registry) is None


def test_family_reader_does_not_wait_for_registry_writer_lock() -> None:
    registry = _registry()
    engine = _engine("sqlite://")
    registry.add(engine)
    held = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def writer() -> None:
        with registry._lock:  # noqa: SLF001 - hold the writer lock while a separate reader runs
            held.set()
            release.wait(1)

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    assert held.wait(0.25)

    def read_snapshot() -> None:
        registry.family()
        registry.engines()
        registry.holds(engine)
        registry.has_engines()
        finished.set()

    reader = threading.Thread(target=read_snapshot, daemon=True)
    reader.start()
    try:
        assert finished.wait(0.25)
    finally:
        release.set()
    thread.join(1)
    reader.join(1)


def test_log_finalizer_does_not_deadlock_with_registry_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine("postgresql+pg8000://db/app")
    handle = _install_default(FastAPI(), engines=[engine])
    registry = handle.context.capture.engine_registry
    assert registry is not None
    log_handler = wiring_of(handle.context).log_handler
    assert log_handler is not None
    handle.context.capture.raw_sqlite_seen = True
    locked = threading.Event()
    read_started = threading.Event()
    finish = threading.Event()
    completed = threading.Event()
    released_by_main = threading.Event()
    registry_lock = threading.Lock()
    monkeypatch.setattr(registry, "_lock", registry_lock)
    original_engines = registry.engines

    def engines() -> list[tuple[str, Any]]:
        read_started.set()
        return original_engines()

    monkeypatch.setattr(registry, "engines", engines)
    logger = logging.getLogger("host.application-family-deadlock")

    def log(message: str) -> None:
        record = logger.makeRecord(logger.name, logging.WARNING, __file__, 1, message, (), None)
        log_handler.handle(record)

    class Finalized:
        def __del__(self) -> None:
            log("finalizer logs")

    def writer() -> None:
        registry_lock.acquire()
        locked.set()
        finish.wait(1)
        gc.collect()
        if not released_by_main.is_set():
            registry_lock.release()

    def reader() -> None:
        log("host line")
        completed.set()

    def garbage() -> None:
        item = Finalized()
        item.cycle = item

    garbage()
    writer_thread = threading.Thread(target=writer, daemon=True)
    writer_thread.start()
    assert locked.wait(0.25)
    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()
    read_started.wait(0.25)
    finish.set()
    reader_thread.join(0.5)
    writer_thread.join(0.5)
    deadlocked = reader_thread.is_alive() or writer_thread.is_alive()
    if deadlocked:
        released_by_main.set()
        registry_lock.release()  # let both daemon workers unwind before the expected-red assertion
        reader_thread.join(0.5)
        writer_thread.join(0.5)
    assert not deadlocked
    assert completed.is_set()


def test_step_two_reads_no_module_table(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoContains(dict[str, object]):
        def __contains__(self, key: object) -> bool:
            raise AssertionError(f"module table read: {key}")

    registry = _registry()
    registry.add(_engine("postgresql+pg8000://db/app"))
    monkeypatch.setattr(sys, "modules", NoContains(sys.modules))
    assert _family(registry) is Dialect.POSTGRESQL


def test_a_seeded_engine_counts_before_a_connect() -> None:
    engine = _engine("postgresql+pg8000://db/app")
    handle = _install(FastAPI(), engines=[engine])
    assert _application_family(handle.context) is Dialect.POSTGRESQL


def test_an_engine_created_later_counts() -> None:
    handle = _install(FastAPI())
    engine = _engine("sqlite://")
    with engine.connect():
        pass
    assert _application_family(handle.context) is Dialect.SQLITE


def test_two_contexts_keep_their_own_family() -> None:
    postgres = _engine("postgresql+pg8000://db/app")
    sqlite = _engine("sqlite://")
    first = _install(FastAPI(), engines=[postgres])
    second = _install(FastAPI(), engines=[sqlite])
    assert _application_family(first.context) is Dialect.POSTGRESQL
    assert _application_family(second.context) is Dialect.SQLITE


def test_a_record_before_a_connect_is_counted() -> None:
    engine = _engine("postgresql+pg8000://db/app")
    handle = _install(FastAPI(), engines=[engine])
    registry = handle.context.capture.engine_registry
    assert registry is not None
    assert _family(registry) is Dialect.POSTGRESQL


def test_resolving_a_dialect_has_no_side_effects(no_side_effects: Any) -> None:
    app = FastAPI()
    engine = _engine("postgresql+pg8000://db/app")
    handle = _install(app, engines=[engine])
    assert _application_family(handle.context) is Dialect.POSTGRESQL
    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        client.get("/sharpit/api/health")
        no_side_effects.block_network()
        no_side_effects.rebaseline()
        assert client.get("/sharpit/api/health").status_code == 200
        assert (
            client.post(
                "/sharpit/api/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            ).status_code
            == 200
        )
    assert no_side_effects.violations == []


def test_a_postgresql_only_host_with_sharpit_imported_is_one_family() -> None:
    engine = _engine("postgresql+pg8000://db/app")
    handle = _install(FastAPI(), engines=[engine])
    assert "sqlite3" in sys.modules
    assert _application_family(handle.context) is Dialect.POSTGRESQL


def test_default_install_without_engines_has_no_family_until_raw_sql_runs() -> None:
    handle = _install_default(FastAPI())
    assert handle.context.settings.sql_trace_enabled is True
    assert sqlite.is_attached() is True
    assert _application_family(handle.context) is None
    with sqlite3.connect(":memory:") as connection:
        connection.execute("select 1")
    assert _application_family(handle.context) is Dialect.SQLITE


def test_default_install_with_idle_raw_hook_keeps_its_engine_family() -> None:
    engine = _engine("postgresql+pg8000://db/app")
    handle = _install_default(FastAPI(), engines=[engine])
    assert handle.context.settings.sql_trace_enabled is True
    assert sqlite.is_attached() is True
    assert _application_family(handle.context) is Dialect.POSTGRESQL


def test_a_seen_raw_sqlite_statement_conflicts_with_a_database_family() -> None:
    engine = _engine("postgresql+pg8000://db/app")
    handle = _install_default(FastAPI(), engines=[engine])
    assert _application_family(handle.context) is Dialect.POSTGRESQL
    with sqlite3.connect(":memory:") as connection:
        connection.execute("select 1")
    assert _application_family(handle.context) is None


def test_a_statement_reads_its_own_connection_over_the_application(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round 5's rule for the hot path: a statement that proves its family never reads the registry."""
    handle = _install_default(FastAPI(), engines=[_engine("postgresql+pg8000://db/app")])
    recorder = handle.context.capture.sql_trace
    assert recorder is not None
    seen: list[Dialect] = []
    monkeypatch.setattr(recorder, "record", lambda _sql, **fields: seen.append(fields["dialect"]))
    event = SqlEvent(
        "sqlalchemy",
        "select 1",
        None,
        False,
        None,
        0,
        1,
        -1,
        None,
        "db",
        _engine("mysql+pymysql://db/app"),
        Dialect.MYSQL_FAMILY,
    )
    dispatch._record(event, [handle.context])  # noqa: SLF001
    assert seen == [Dialect.MYSQL_FAMILY]


def test_a_statement_on_a_connection_older_than_the_engine_dialect_hides(monkeypatch: pytest.MonkeyPatch) -> None:
    """The listener reads the connection, ``event_dialect`` the engine: two holders, or the check agrees with itself."""
    engine = _engine("sqlite://")
    handle = _install_default(FastAPI(), engines=[engine])
    recorder = handle.context.capture.sql_trace
    assert recorder is not None
    seen: list[Dialect] = []
    monkeypatch.setattr(recorder, "record", lambda _sql, **fields: seen.append(fields["dialect"]))
    with engine.connect() as connection:
        connection.exec_driver_sql("select 1")
        engine.dialect = _engine("mysql+pymysql://db/app").dialect
        connection.exec_driver_sql("select 2")
    assert seen == [Dialect.SQLITE, Dialect.UNSUPPORTED]


def test_a_raw_source_does_not_resolve_a_mixed_registry() -> None:
    postgres = _engine("postgresql+pg8000://db/app")
    local = _engine("sqlite://")
    handle = _install_default(FastAPI(), engines=[postgres, local])
    with sqlite3.connect(":memory:") as connection:
        connection.execute("select 1")
    assert _application_family(handle.context) is None


def test_raw_sqlite_is_seen_while_recording_is_paused() -> None:
    handle = _install_default(FastAPI())
    recorder = handle.context.capture.sql_trace
    assert recorder is not None
    recorder.set_recording(False)
    with sqlite3.connect(":memory:") as connection:
        connection.execute("select 1")
    assert handle.context.capture.raw_sqlite_seen is True
    # With sql_trace_sqlite3_enabled=False, no raw hook is installed and nothing is seen.


def test_raw_sqlite_is_not_seen_when_its_source_is_disabled() -> None:
    handle = _install_default(FastAPI(), sql_trace_sqlite3_enabled=False)
    dispatch.recording(None, "sqlite3")
    assert handle.context.capture.raw_sqlite_seen is False


def test_raw_sqlite_seen_respects_request_context() -> None:
    first = _install_default(FastAPI())
    second = _install_default(FastAPI())
    token = REQUEST.set(RequestInfo("request", "another-context", "GET", "/", None, 0, None))
    try:
        dispatch.recording(None, "sqlite3")
    finally:
        REQUEST.reset(token)
    assert first.context.capture.raw_sqlite_seen is False
    assert second.context.capture.raw_sqlite_seen is False


def test_raw_sqlite_is_seen_by_both_installs_outside_a_request() -> None:
    first = _install_default(FastAPI())
    second = _install_default(FastAPI())
    with sqlite3.connect(":memory:") as connection:
        connection.execute("select 1")
    assert first.context.capture.raw_sqlite_seen is True
    assert second.context.capture.raw_sqlite_seen is True


@pytest.mark.parametrize(
    "constructor",
    [ExceptionStore.__init__, SharpitLogHandler.__init__, TransactionRecorder.__init__, run_probe],
    ids=["exceptions", "log-tail", "transactions", "probe"],
)
def test_each_output_surface_requires_an_application_family(constructor: Any) -> None:
    assert inspect.signature(constructor).parameters["application"].default is inspect.Parameter.empty


def test_install_wires_the_application_family_to_capture_stores() -> None:
    engine = _engine("postgresql+pg8000://db/app")
    handle = _install_default(FastAPI(), engines=[engine])
    exceptions = handle.context.capture.exceptions
    assert exceptions is not None
    assert exceptions.application() is Dialect.POSTGRESQL
    wiring = wiring_of(handle.context)
    assert wiring is not None
    assert wiring.log_handler is not None
    assert wiring.log_handler.application() is Dialect.POSTGRESQL
    transactions = handle.context.capture.transactions
    assert transactions is not None
    assert transactions._application() is Dialect.POSTGRESQL  # noqa: SLF001


def test_span_buffer_requires_an_application_family() -> None:
    parameters = inspect.signature(SpanBuffer.__init__).parameters
    assert "application" in parameters
    assert parameters["application"].default is inspect.Parameter.empty


def test_installed_span_buffer_uses_the_application_family() -> None:
    engine = _engine("postgresql+pg8000://db/app")
    handle = _install_default(FastAPI(), engines=[engine])
    buffer = span_buffer(handle.context)
    application = getattr(buffer, "application", None)
    assert callable(application)
    assert application() is Dialect.POSTGRESQL
