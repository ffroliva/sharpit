from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from sharpit.engine import sqla

pytestmark = pytest.mark.needs_sqlalchemy

PG_URL = os.environ.get("SHARPIT_TEST_POSTGRES_URL", "")
NEEDS_PG = pytest.mark.skipif(not PG_URL, reason="requires leased PostgreSQL via SHARPIT_TEST_POSTGRES_URL")


@dataclass
class _FakeDialect:
    name: str = "postgresql"
    is_async: bool = False


@dataclass
class _FakeScalarResult:
    value: Any = "on"

    def scalar(self) -> Any:
        return self.value


@dataclass
class _FakePgConn:
    in_tx: bool = True
    read_only_setting: str = "on"
    dialect: _FakeDialect = field(default_factory=_FakeDialect)
    queries: list[str] = field(default_factory=list)
    rolled_back: bool = False

    def in_transaction(self) -> bool:
        return self.in_tx

    def exec_driver_sql(self, sql: str) -> _FakeScalarResult:
        self.queries.append(sql)
        if "transaction_read_only" in sql:
            return _FakeScalarResult(self.read_only_setting)
        return _FakeScalarResult(1)

    def rollback(self) -> None:
        self.rolled_back = True

    def __enter__(self) -> _FakePgConn:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


@dataclass
class _FakePgEngine:
    conn: _FakePgConn = field(default_factory=_FakePgConn)
    dialect: _FakeDialect = field(default_factory=_FakeDialect)

    def connect(self) -> _FakePgConn:
        return self.conn


def test_default_path_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = sa.create_engine("sqlite://")
    calls: list[float] = []
    original = sqla.bounded

    def spy_bounded(conn: Any, fn: Any, timeout: float) -> Any:
        calls.append(timeout)
        return original(conn, fn, timeout)

    monkeypatch.setattr(sqla, "bounded", spy_bounded)
    result = asyncio.run(sqla.run_db_read(engine, lambda c: c.exec_driver_sql("SELECT 1").scalar(), 5.0))
    assert result == 1
    assert calls == [5.0]


def test_separate_wall_and_statement_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _FakePgEngine()
    wall_seen: list[float | None] = []
    stmt_seen: list[tuple[float, float]] = []
    original_timeout = asyncio.timeout

    @asynccontextmanager
    async def spy_timeout(delay: float | None):
        wall_seen.append(delay)
        async with original_timeout(delay):
            yield

    def spy_ro(conn: Any, fn: Any, statement_timeout: float, lock_timeout: float = 2.0) -> Any:
        stmt_seen.append((statement_timeout, lock_timeout))
        return fn(conn)

    monkeypatch.setattr(asyncio, "timeout", spy_timeout)
    monkeypatch.setattr(sqla, "bounded_read_only", spy_ro)
    result = asyncio.run(
        sqla.run_db_read(
            engine,
            lambda _c: "ok",
            5.0,
            wall_timeout=15.0,
            statement_timeout=5.0,
            read_only=True,
        )
    )
    assert result == "ok"
    assert wall_seen == [15.0]
    assert stmt_seen == [(5.0, 2.0)]


def test_read_only_order() -> None:
    # ported: PostgresHelpersTests.readOnlyTransactionPinRunsBeforeAnySavepoint
    conn = _FakePgConn()
    result = sqla.bounded_read_only(conn, lambda c: c.exec_driver_sql("SELECT 1").scalar(), 5.0)
    assert result == 1
    assert conn.queries == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = 5000",
        "SET LOCAL lock_timeout = 2000",
        "SELECT current_setting('transaction_read_only')",
        "SELECT 1",
    ]
    assert conn.rolled_back is True


def test_autocommit_fails_closed_without_catalog_sql() -> None:
    # ported: PostgresInsightServiceTests.aRefusedReadOnlyPinStopsTheReadBeforeCollectorsRun
    conn = _FakePgConn(in_tx=False)
    called = False

    def catalog_read(_c: Any) -> int:
        nonlocal called
        called = True
        return 1

    reason: str | None = None
    try:
        sqla.bounded_read_only(conn, catalog_read, 5.0)
    except sqla.ReadOnlyUnavailable as exc:
        reason = exc.reason

    assert reason == sqla.READ_ONLY_REFUSED
    assert called is False
    assert conn.rolled_back is True


def test_read_only_setting_off_fails_closed() -> None:
    # derived: SQLAlchemy 2 in_transaction() is True under AUTOCOMMIT
    conn = _FakePgConn(in_tx=True, read_only_setting="off")
    called = False

    def catalog_read(_c: Any) -> int:
        nonlocal called
        called = True
        return 1

    reason: str | None = None
    try:
        sqla.bounded_read_only(conn, catalog_read, 5.0)
    except sqla.ReadOnlyUnavailable as exc:
        reason = exc.reason

    assert reason == sqla.READ_ONLY_REFUSED
    assert called is False
    assert conn.rolled_back is True


def test_internal_marker_kept() -> None:
    engine = _FakePgEngine()
    seen = asyncio.run(sqla.run_db_read(engine, lambda _c: sqla.is_internal(), 5.0, read_only=True))
    assert seen is True


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


@NEEDS_PG
def test_read_only_wrapper_rejects_write() -> None:
    engine = sa.create_engine(_psycopg_url(PG_URL))
    try:
        failed = False
        try:
            asyncio.run(
                sqla.run_db_read(
                    engine,
                    lambda c: c.exec_driver_sql("CREATE TEMP TABLE sharpit_ro_probe (id int)"),
                    5.0,
                    read_only=True,
                )
            )
        except Exception as exc:  # noqa: BLE001
            failed = "read-only" in str(exc).lower() or "readonly" in str(exc).lower()
        assert failed is True

        probe = asyncio.run(
            sqla.run_db_read(
                engine,
                lambda c: c.exec_driver_sql("SELECT to_regclass('pg_temp.sharpit_ro_probe')").scalar(),
                5.0,
                read_only=True,
            )
        )
        assert probe is None
    finally:
        engine.dispose()


@NEEDS_PG
def test_autocommit_engine_is_unavailable() -> None:
    engine = sa.create_engine(_psycopg_url(PG_URL), isolation_level="AUTOCOMMIT")
    called = False

    def should_not_run(_c: Any) -> int:
        nonlocal called
        called = True
        return 1

    try:
        reason: str | None = None
        try:
            asyncio.run(sqla.run_db_read(engine, should_not_run, 5.0, read_only=True))
        except sqla.ReadOnlyUnavailable as exc:
            reason = exc.reason
        assert reason == sqla.READ_ONLY_REFUSED
        assert called is False
    finally:
        engine.dispose()


@NEEDS_PG
def test_async_engine_read_only() -> None:
    async def run() -> Any:
        engine = create_async_engine(_psycopg_url(PG_URL))
        try:
            return await sqla.run_db_read(
                engine,
                lambda c: c.exec_driver_sql("SELECT current_setting('transaction_read_only')").scalar(),
                5.0,
                read_only=True,
            )
        finally:
            await engine.dispose()

    assert asyncio.run(run()) == "on"
