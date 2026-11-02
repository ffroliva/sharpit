"""Lane A-postgresql safety rows (spec §6.1 item 3, §6.4): the read is POST-only, read-only and never commits."""

from __future__ import annotations

import asyncio
from typing import Any

from tests.engine.postgresql.fakes import FakePgEngine, FakeRegistry

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.postgresql.service import postgresql_report, refresh_postgresql
from sharpit.engine.context import SharpitContext
from sharpit.settings import load_settings

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())


class _Introspector:
    def app_info(self) -> Any:
        return None

    def routes(self) -> list[Any]:
        return []

    def providers(self) -> list[Any]:
        return []


def _ctx(engine: FakePgEngine) -> SharpitContext:
    ctx = SharpitContext(load_settings({"config_scan": False}, {}), ACTIVATION, _Introspector())
    ctx.capture.engine_registry = FakeRegistry(("primary", engine))  # type: ignore[assignment]
    return ctx


def test_report_never_runs_sql() -> None:
    engine = FakePgEngine()
    postgresql_report(_ctx(engine))
    assert engine.connects == 0
    assert engine.conn.sql == []


def test_read_pins_read_only_first_and_rolls_back() -> None:
    engine = FakePgEngine()
    asyncio.run(refresh_postgresql(_ctx(engine)))
    assert engine.conn.sql[:4] == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = 5000",
        "SET LOCAL lock_timeout = 2000",
        "SELECT current_setting('transaction_read_only')",
    ]
    assert engine.conn.rolled_back == 1
    assert [sql for sql in engine.conn.sql if sql.lstrip().lower().startswith(("commit", "insert", "update"))] == []


def test_every_catalog_query_runs_in_its_own_savepoint() -> None:
    engine = FakePgEngine()
    asyncio.run(refresh_postgresql(_ctx(engine)))
    catalog = [sql for sql in engine.conn.sql if not sql.startswith(("SET ", "SELECT current_setting"))]
    assert len(catalog) >= 10
    assert engine.conn.savepoints == len(catalog)


def test_a_refused_pin_runs_no_catalog_sql() -> None:
    engine = FakePgEngine()
    engine.conn.read_only_setting = "off"
    report = asyncio.run(refresh_postgresql(_ctx(engine)))
    assert report["status"] == "ERROR"
    assert engine.conn.savepoints == 0
