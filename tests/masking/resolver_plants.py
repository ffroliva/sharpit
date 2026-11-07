"""A12 resolver cases and mutations, kept out of the package under test."""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable, Sequence
from types import SimpleNamespace
from typing import NamedTuple

import psycopg
import pymysql
import sqlalchemy as sa
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanContext, SpanKind, TraceFlags, TraceState
from opentelemetry.trace.status import Status, StatusCode
from sqlalchemy.exc import IntegrityError

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.traces import SpanDialectSource, span_buffer
from sharpit.engine.context import application_family
from sharpit.engine.sources import sqlite
from sharpit.engine.sources.dispatch import SqlEvent
from sharpit.engine.sources.sqlite import SQLiteDialectSource
from sharpit.engine.sqla.dialect_source import EngineDialectSource, ExceptionDialectSource
from sharpit.engine.sqltext import Dialect, DialectContext, DialectSource, resolve


class Plant(NamedTuple):
    module: str
    anchor: str
    replacement: str


class Input(NamedTuple):
    event: object
    sources: Sequence[DialectSource]
    context: DialectContext


class Row(NamedTuple):
    build: Callable[[], tuple[Input, ...]]
    wanted: Dialect
    plant: Plant


def _error(name: str, module: str) -> BaseException:
    return type(name, (Exception,), {"__module__": module})("database failure")


def _chain(*errors: BaseException) -> BaseException:
    for left, right in zip(errors, errors[1:], strict=False):
        left.__cause__ = right
    return errors[0]


def _input(event: object, sources: Sequence[DialectSource], app: Dialect | None = None):
    return Input(event, sources, DialectContext(lambda: app))


def _engine(url: str = "postgresql+pg8000://db/app") -> sa.Engine:
    options = (
        {"module": SimpleNamespace(paramstyle="format", __version__="1.30.5")} if url.startswith("postgresql") else {}
    )
    return sa.create_engine(url, **options)


def _sql_event(engine: sa.Engine, dialect: Dialect, error: BaseException | None = None) -> SqlEvent:
    return SqlEvent("sqlalchemy", "SELECT 1", None, False, None, 0, 1, -1, error, "connection", engine, dialect)


def _sqlalchemy_error(original: BaseException) -> IntegrityError:
    return IntegrityError("SELECT 1", {}, original)


def _readable_span(attributes: dict[str, object]) -> ReadableSpan:
    return ReadableSpan(
        "query",
        context=SpanContext(1, 1, False, TraceFlags(1), TraceState()),
        resource=Resource.create({"service.name": "app"}),
        attributes=attributes,
        kind=SpanKind.CLIENT,
        status=Status(StatusCode.ERROR, "query failed"),
        start_time=1,
        end_time=2,
    )


_TEXT_SOURCES: tuple[DialectSource, ...] = (
    EngineDialectSource(),
    ExceptionDialectSource(),
    SpanDialectSource(),
    SQLiteDialectSource(),
)


_DRIVER_NAMES = (
    "psycopg",
    "psycopg2",
    "asyncpg",
    "sqlalchemy.dialects.postgresql.asyncpg",
    "pymysql",
    "MySQLdb",
    "pg8000",
    "mysql",
    "mariadb",
    "asyncmy",
    "aiomysql",
    "sqlite3",
)


_TEXT_PLANT = Plant(
    "engine/sqltext/dialect.py",
    "    try:\n        proof: set[Dialect] = set()\n",
    "    try:\n"
    "        if isinstance(event, str) and any(name in event for name in _DRIVERS):\n"
    "            return next(family for name, family in _DRIVERS.items() if name in event)\n"
    "        proof: set[Dialect] = set()\n",
)
_LINE_PLANT = Plant(
    "engine/sqltext/dialect.py",
    "    try:\n        proof: set[Dialect] = set()\n",
    "    try:\n"
    "        if isinstance(event, str) and any(event.splitlines()[1].startswith(name) for name in _DRIVERS):\n"
    "            return next(family for name, family in _DRIVERS.items() if event.splitlines()[1].startswith(name))\n"
    "        proof: set[Dialect] = set()\n",
)
_ANCHOR_PLANT = Plant(
    "engine/sqltext/dialect.py",
    "    try:\n        proof: set[Dialect] = set()\n",
    "    try:\n"
    "        if isinstance(event, str) and event.startswith('(psycopg.errors.'):\n"
    "            return Dialect.POSTGRESQL\n"
    "        proof: set[Dialect] = set()\n",
)
_FIRST_FAMILY_PLANT = Plant(
    "engine/sqla/dialect_source.py",
    "if reading.stopped or reading.exhausted or len(reading.families) > 1:",
    "if reading.stopped or reading.exhausted:",
)
_FIRST_PROOF_PLANT = Plant(
    "engine/sqltext/dialect.py",
    "        if len(proof) > 1:\n            return Dialect.UNSUPPORTED",
    "        if len(proof) > 1:\n            return next(iter(proof))",
)
_SKIP_APPLICATION_PLANT = Plant(
    "engine/sqltext/dialect.py",
    "return family if application in (None, family) else Dialect.UNSUPPORTED",
    "return family",
)
_PASS_UNLISTED_PLANT = Plant(
    "engine/sqltext/dialect.py",
    "        elif _is_dbapi_error(current) and not _is_sqlalchemy_wrapper(current) "
    "and not _is_sqlalchemy_internal(current):\n"
    "            return ChainReading(frozenset(families), stopped=True, visited=visited)",
    "        elif False and _is_dbapi_error(current) and not _is_sqlalchemy_wrapper(current) "
    "and not _is_sqlalchemy_internal(current):\n"
    "            return ChainReading(frozenset(families), stopped=True, visited=visited)",
)
_UNMAPPED_PLANT = Plant(
    "engine/sqltext/dialect.py",
    "return None if name is None else _NAMES.get(name, Dialect.UNSUPPORTED)",
    "return None if name is None else _NAMES.get(name)",
)
_IGNORE_RAW_SQLITE_PLANT = Plant(
    "engine/context.py",
    "        return None\n    return family\n",
    "        return family\n    return family\n",
)
_SKIP_CONTEXT_PLANT = Plant(
    "engine/sqltext/dialect.py",
    "elif not suppressed and issubclass(type(context), BaseException):\n"
    '        pending.append(cast("BaseException", context))',
    "elif False and not suppressed and issubclass(type(context), BaseException):\n"
    '        pending.append(cast("BaseException", context))',
)
_IGNORE_BOUND_PLANT = Plant(
    "engine/sqla/dialect_source.py",
    "if reading.stopped or reading.exhausted or len(reading.families) > 1:",
    "if reading.stopped or len(reading.families) > 1:",
)


def _value_naming_a_driver():
    return tuple(_input(f"literal value contains {name}", _TEXT_SOURCES, None) for name in _DRIVER_NAMES)


def _multiline_driver_line():
    return (_input("val\npsycopg.errors.ProgrammingError: failed\n[SQL: SELECT 'x']", _TEXT_SOURCES, None),)


def _driver_shaped_trigger_value():
    return (_input(trigger_message('(psycopg.errors.SyntaxError) failed\n[SQL: SELECT "x"]'), _TEXT_SOURCES, None),)


def trigger_message(value: str) -> str:
    """``str(exc)`` of a live SQLite trigger that raises ``value``, a bound value, as its message."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        "CREATE TABLE input (value TEXT);"
        "CREATE TRIGGER deny BEFORE INSERT ON input BEGIN "
        + (
            "SELECT RAISE(FAIL, NEW.value); END;"
            if sqlite3.sqlite_version_info >= (3, 47, 0)
            else f"SELECT RAISE(FAIL, '{value}'); END;"
        )
    )
    try:
        connection.execute("INSERT INTO input VALUES (?)", (value,))
    except sqlite3.Error as exc:
        message = str(exc)
    else:
        raise AssertionError("SQLite trigger did not fail")
    finally:
        connection.close()
    return message


def _two_families_in_chain():
    postgres = psycopg.Error("database failure")
    postgres.__cause__ = sqlite3.IntegrityError("database failure")
    error = _sqlalchemy_error(postgres)
    return (_input(error, (ExceptionDialectSource(),), None),)


def _event_source_against_chain():
    engine = _engine()
    error = _sqlalchemy_error(pymysql.err.IntegrityError(1062, "database failure"))
    event = _sql_event(engine, Dialect.POSTGRESQL, error)
    return (_input(event, (EngineDialectSource(), ExceptionDialectSource()), None),)


def _event_source_against_application():
    engine = _engine("mysql+pymysql://db/app")
    event = _sql_event(engine, Dialect.MYSQL_FAMILY)
    return (_input(event, (EngineDialectSource(),), Dialect.POSTGRESQL),)


def _unlisted_driver_above_a_listed_one():
    error = _chain(_error("DatabaseError", "oracledb"), _error("Error", "sqlite3"))
    return (_input(error, (ExceptionDialectSource(),), None),)


def _unlisted_driver_in_a_single_family_app():
    return (_input(_error("Error", "pyodbc"), (ExceptionDialectSource(),), Dialect.POSTGRESQL),)


def _unmapped_name():
    error = _sqlalchemy_error(psycopg.Error("database failure"))
    engine_event = SimpleNamespace(dialect=SimpleNamespace(name="cockroachdb"), error=error)
    span = _readable_span({"db.system": "redis", "exception.message": str(error)})
    sources = (EngineDialectSource(), ExceptionDialectSource())
    span_sources = (SpanDialectSource(), ExceptionDialectSource())
    return (
        Input(engine_event, sources, DialectContext(lambda: None)),
        Input(
            SimpleNamespace(dialect=SimpleNamespace(name="mysql")),
            (EngineDialectSource(),),
            DialectContext(lambda: Dialect.POSTGRESQL),
        ),
        Input(span, span_sources, DialectContext(lambda: Dialect.POSTGRESQL)),
    )


def _two_seen_families():
    handle = install(FastAPI(), enabled="ON", show_banner=False, engines=[_engine()])
    try:
        with sqlite.sqlite3.connect(":memory:") as connection:
            connection.execute("select 1")
        return (Input(object(), (), DialectContext(lambda: application_family(handle.context))),)
    finally:
        handle.uninstall_capture()


def _walk_through_wrapper():
    driver = psycopg.Error("database failure")
    original = RuntimeError("outer wrapper")
    wrapped = _sqlalchemy_error(original)
    wrapped.__context__ = driver
    return (_input(wrapped, (ExceptionDialectSource(),), None),)


def _bound_reached():
    chain = [_error("Wrapper", "wrapper") for _ in range(32)]
    chain.append(_error("ProgrammingError", "psycopg.errors"))
    return (_input(_chain(*chain), (ExceptionDialectSource(),), Dialect.POSTGRESQL),)


_RAW_SQLITE_PLANT = _IGNORE_RAW_SQLITE_PLANT

A12_ROWS: dict[str, Row] = {
    "value_naming_a_driver": Row(_value_naming_a_driver, Dialect.UNSUPPORTED, _TEXT_PLANT),
    "multiline_driver_line": Row(_multiline_driver_line, Dialect.UNSUPPORTED, _LINE_PLANT),
    "driver_shaped_value_from_a_trigger": Row(_driver_shaped_trigger_value, Dialect.UNSUPPORTED, _ANCHOR_PLANT),
    "two_families_in_a_chain": Row(_two_families_in_chain, Dialect.UNSUPPORTED, _FIRST_FAMILY_PLANT),
    "event_source_against_the_chain": Row(_event_source_against_chain, Dialect.UNSUPPORTED, _FIRST_PROOF_PLANT),
    "event_source_against_the_application": Row(
        _event_source_against_application, Dialect.UNSUPPORTED, _SKIP_APPLICATION_PLANT
    ),
    "unlisted_driver_above_a_listed_one": Row(
        _unlisted_driver_above_a_listed_one, Dialect.UNSUPPORTED, _PASS_UNLISTED_PLANT
    ),
    "unlisted_driver_in_a_single_family_app": Row(
        _unlisted_driver_in_a_single_family_app, Dialect.UNSUPPORTED, _PASS_UNLISTED_PLANT
    ),
    "unmapped_name": Row(_unmapped_name, Dialect.UNSUPPORTED, _UNMAPPED_PLANT),
    "two_seen_families": Row(_two_seen_families, Dialect.UNSUPPORTED, _RAW_SQLITE_PLANT),
    "walk_through_a_wrapper": Row(_walk_through_wrapper, Dialect.POSTGRESQL, _SKIP_CONTEXT_PLANT),
    "bound_reached": Row(_bound_reached, Dialect.UNSUPPORTED, _IGNORE_BOUND_PLANT),
}


def evaluate(row_name: str) -> Dialect:
    row = A12_ROWS[row_name]
    return next((actual for case in row.build() if (actual := resolve(*case)) is not row.wanted), row.wanted)


def unseen_database_limit() -> Dialect:
    handle = install(FastAPI(), enabled="ON", show_banner=False, engines=[_engine()])
    try:
        event = _readable_span({"db.statement": "SELECT 1"})
        return resolve(event, (SpanDialectSource(),), DialectContext(span_buffer(handle.context).application))
    finally:
        handle.uninstall_capture()


if __name__ == "__main__":
    print(evaluate(sys.argv[1]).value)
