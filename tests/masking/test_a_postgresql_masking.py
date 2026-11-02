"""Lane A-postgresql masking corpus rows (spec §6.1 item 3): catalog text and driver errors never leak a secret."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from tests.engine.postgresql.fakes import FakePgEngine, FakeRegistry, default_rows

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.postgresql.service import refresh_postgresql
from sharpit.engine.context import SharpitContext
from sharpit.settings import load_settings

# the service reads nothing while sharpit reports SQLAlchemy 2 unavailable (finding 8), so these need it imported
pytestmark = pytest.mark.needs_sqlalchemy
pytest.importorskip("sqlalchemy")

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
STRIPE_KEY = "sk_live_" + "51HxQzLKbF2pWnQ8vT3uY6rE9iO0aS"
PASSWORD = "hunter2-correct-horse"


class _Introspector:
    def app_info(self) -> Any:
        return None

    def routes(self) -> list[Any]:
        return []

    def providers(self) -> list[Any]:
        return []


def _read(engine: FakePgEngine) -> str:
    ctx = SharpitContext(load_settings({"config_scan": False}, {}), ACTIVATION, _Introspector())
    ctx.capture.engine_registry = FakeRegistry(("primary", engine))  # type: ignore[assignment]
    return repr(asyncio.run(refresh_postgresql(ctx)))


def _session(query: str) -> dict[str, Any]:
    return {**default_rows("SESSIONS")[0], "query": query}


@pytest.mark.parametrize(
    "query",
    [
        f"update charges set key = '{STRIPE_KEY}' where id = 1",
        f"select set_config('app.key', E'{STRIPE_KEY}'x', false)",
        f"do $body$ begin perform '{STRIPE_KEY}'; end $body$",
        f"select 1 /* {STRIPE_KEY} */",
    ],
)
def test_pg_stat_activity_query_masks_a_stripe_key(query: str) -> None:
    engine = FakePgEngine()
    engine.conn.with_rows("SESSIONS", _session(query))
    assert STRIPE_KEY not in _read(engine)


def test_pg_stat_statements_query_masks_a_password() -> None:
    engine = FakePgEngine()
    engine.conn.with_rows("STATEMENTS", {"query_id": "1", "query": f"alter role app password '{PASSWORD}'", "calls": 1})
    shown = _read(engine)
    assert PASSWORD not in shown
    assert "alter role app password '******'" in shown


def test_pg_stat_statements_unquoted_password_pair_is_masked() -> None:
    engine = FakePgEngine()
    engine.conn.with_rows("STATEMENTS", {"query_id": "1", "query": f"set app.cfg to password={PASSWORD}", "calls": 1})
    assert PASSWORD not in _read(engine)


def test_a_driver_error_carrying_a_dsn_password_is_masked() -> None:
    engine = FakePgEngine()
    engine.conn.fail("INDEXES", f"connection to postgresql://app:{PASSWORD}@db:5432/app failed")
    shown = _read(engine)
    assert PASSWORD not in shown
    assert "Index usage statistics could not be read" in shown


def test_a_refused_connection_with_a_dsn_password_is_masked() -> None:
    assert PASSWORD not in _read(FakePgEngine(refuse=f"could not connect to postgresql://app:{PASSWORD}@db/app"))
