"""The shared SQL event path (spec 0.3.0 §8.1): routing to console contexts, the session sink, failure isolation.

Every case is derived: the routing rules moved out of ``sqla`` unchanged (they had no BootUI oracle).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.correlation import INTERNAL, REQUEST, TEST, RequestInfo  # noqa: E402
from sharpit.engine.sources import dispatch  # noqa: E402
from sharpit.engine.sources.dispatch import SqlEvent  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

_HANDLES: list[SharpitHandle] = []


class FakeSink:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sql: list[tuple[SqlEvent, tuple[str, int, str] | None]] = []

    def on_sql(self, event: SqlEvent, test: tuple[str, int, str] | None) -> None:
        self.sql.append((event, test))
        if self.fail:
            raise RuntimeError("sink broke")

    def on_exception(self, exc: BaseException, source: str, test: tuple[str, int, str] | None) -> None:
        del exc, source, test

    def on_escaped(self, exc: BaseException) -> None:
        del exc

    def register_app(self, app: object) -> None:
        del app


@pytest.fixture(autouse=True)
def _clean_slate() -> Iterator[None]:
    sqla.detach_all()
    dispatch.set_session_sink(None)
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()
    dispatch.set_session_sink(None)
    sqla.detach_session()
    sqla.detach_all()


def _install(**options: Any) -> SharpitHandle:
    handle = install(FastAPI(), **{"enabled": "ON", "show_banner": False, **options})
    _HANDLES.append(handle)
    return handle


def _sql(handle: SharpitHandle) -> list[str]:
    recorder = handle.context.capture.sql_trace
    assert recorder is not None
    return [e["sql"] for e in recorder.report([])["entries"]]


def _event(sql: str = "select 1", **fields: Any) -> SqlEvent:
    values: dict[str, Any] = {
        "source": "sqlite3", "sql": sql, "parameters": None, "executemany": False, "batch_size": None,
        "started_ns": 0, "duration_ns": 1000, "rowcount": 1, "error": None, "connection_id": None, "engine": None,
    }  # fmt: skip
    return SqlEvent(**{**values, **fields})


def _request(handle: SharpitHandle) -> RequestInfo:
    return RequestInfo("r1", handle.context.context_id, "GET", "/x", None, 0, None)


def test_emit_routes_to_request_context():
    first, second = _install(), _install()
    token = REQUEST.set(_request(second))
    try:
        dispatch.emit(_event("select 'request'"))
    finally:
        REQUEST.reset(token)
    assert _sql(second) == ["select ?"]
    assert _sql(first) == []


def test_emit_outside_request_uses_engine_holder():
    engine = sa.create_engine("sqlite://")
    holder, other = _install(engines=[engine]), _install()
    dispatch.emit(_event("select 'held'", engine=engine))
    assert _sql(holder) == ["select ?"]
    assert _sql(other) == []


def test_emit_single_context_fallback():
    only = _install()
    dispatch.emit(_event("select 'only'"))
    assert _sql(only) == ["select ?"]
    _install()
    dispatch.emit(_event("select 'two contexts'"))  # no engine, two contexts: nobody owns it
    assert _sql(only) == ["select ?"]


def test_emit_internal_skipped():
    handle = _install()
    token = INTERNAL.set(True)
    try:
        dispatch.emit(_event("select 'internal'"))
    finally:
        INTERNAL.reset(token)
    assert _sql(handle) == []
    dispatch.emit(_event("select 'visible'"))
    assert _sql(handle) == ["select ?"]


def test_emit_calls_session_sink_with_test_tag():
    sink = FakeSink()
    dispatch.set_session_sink(sink)
    token = TEST.set(("tests/test_a.py::test_one", 1, "call"))
    try:
        dispatch.emit(_event("select 'tagged'"))
    finally:
        TEST.reset(token)
    dispatch.emit(_event("select 'untagged'"))
    assert [test for _, test in sink.sql] == [("tests/test_a.py::test_one", 1, "call"), None]
    assert dispatch.session_sink() is sink


def test_emit_without_sink_no_error():
    handle = _install()
    assert dispatch.session_sink() is None
    dispatch.emit(_event("select 'no sink'"))
    assert _sql(handle) == ["select ?"]


def test_emit_never_raises(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    handle = _install()
    recorder = handle.context.capture.sql_trace
    assert recorder is not None

    def broken(*_a: object, **_k: object) -> None:
        raise RuntimeError("recorder broke")

    monkeypatch.setattr(recorder, "record", broken)
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        dispatch.emit(_event())
        dispatch.emit(_event())
    warnings = [r for r in caplog.records if "sql statement" in r.getMessage()]
    assert len(warnings) == 1


def test_sink_raises_query_unaffected(caplog: pytest.LogCaptureFixture):
    sink = FakeSink(fail=True)
    dispatch.set_session_sink(sink)
    assert sqla.attach_session() is True
    engine = sa.create_engine("sqlite://")
    with caplog.at_level(logging.WARNING, logger="sharpit"), engine.connect() as conn:
        assert conn.execute(sa.text("select 41 + 1")).scalar() == 42
    assert len(sink.sql) == 1


def test_sqla_listener_feeds_sink_without_context():
    sink = FakeSink()
    dispatch.set_session_sink(sink)
    assert sqla.attach_session() is True
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn:
        conn.execute(sa.text("select 1"))
    assert [e.source for e, _ in sink.sql] == ["sqlalchemy"]
    assert dispatch.engine_drivers() == {"pysqlite"}


def test_context_removal_keeps_session_listeners():
    dispatch.set_session_sink(FakeSink())
    assert sqla.attach_session() is True
    handle = _install()
    assert all(sqla.attached().values())
    sqla.remove(handle.context)  # an app's lifespan shutdown
    assert all(sqla.attached()[e] for e in sqla.STATEMENT_EVENTS)
    sqla.detach_session()
    assert not any(sqla.attached()[e] for e in sqla.STATEMENT_EVENTS)
