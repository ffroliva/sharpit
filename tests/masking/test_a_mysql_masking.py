"""Lane A-mysql masking corpus rows: catalog text and driver errors never leak a secret."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from tests.engine.collectors.mysql.fakes import FakeMySqlEngine, FakeRegistry

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.mysql.service import refresh_mysql
from sharpit.engine.context import SharpitContext
from sharpit.settings import load_settings

pytestmark = pytest.mark.needs_sqlalchemy
pytest.importorskip("sqlalchemy")

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
PASSWORD = "hunter2-correct-horse"


class _Introspector:
    def app_info(self) -> Any:
        return None

    def routes(self) -> list[Any]:
        return []

    def providers(self) -> list[Any]:
        return []


def _ctx(engine: FakeMySqlEngine) -> SharpitContext:
    ctx = SharpitContext(load_settings({"config_scan": False}, {}), ACTIVATION, _Introspector())
    ctx.capture.engine_registry = FakeRegistry(("primary", engine))  # type: ignore[assignment]
    return ctx


def test_driver_error_dsn_password_masked() -> None:
    engine = FakeMySqlEngine(refuse=f"could not connect to mysql://app:{PASSWORD}@db:3306/app")
    report = asyncio.run(refresh_mysql(_ctx(engine)))
    shown = repr(report)
    assert PASSWORD not in shown
    assert "could not connect to mysql" in shown
