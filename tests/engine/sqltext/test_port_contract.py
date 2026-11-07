"""Dialect sources are local, defensive ports; # derived: BootUI has no dialect resolver."""

from __future__ import annotations

import builtins
import socket
import sys

import pytest

from sharpit.engine.capture.traces import SpanDialectSource
from sharpit.engine.sources.sqlite import SQLiteDialectSource
from sharpit.engine.sqla.dialect_source import EngineDialectSource, ExceptionDialectSource
from sharpit.engine.sqltext.dialect import Dialect, DialectContext, DialectSource

SOURCES: tuple[DialectSource, ...] = (
    EngineDialectSource(),
    ExceptionDialectSource(),
    SpanDialectSource(),
    SQLiteDialectSource(),
)


class Hostile:
    @property
    def dialect(self) -> object:
        raise RuntimeError("dialect property")

    @property
    def context(self) -> object:
        raise RuntimeError("context property")

    @property
    def engine(self) -> object:
        raise RuntimeError("engine property")

    @property
    def attributes(self) -> object:
        raise RuntimeError("attributes property")

    @property
    def source(self) -> object:
        raise RuntimeError("source property")

    @property
    def error(self) -> object:
        raise RuntimeError("error property")


@pytest.mark.parametrize("source", SOURCES, ids=[type(item).__name__ for item in SOURCES])
def test_each_dialect_source_is_local_and_defensive(source: DialectSource, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("source crossed a local boundary")

    monkeypatch.setattr(builtins, "open", fail)
    monkeypatch.setattr(socket, "socket", fail)
    before = set(sys.modules)
    result = source.dialect_of(Hostile(), DialectContext(lambda: None))
    after = set(sys.modules)

    if result is not None:
        assert isinstance(result, Dialect)
    assert not (after - before) & {"psycopg", "psycopg2", "asyncpg", "pymysql", "MySQLdb", "mysql", "mariadb"}
