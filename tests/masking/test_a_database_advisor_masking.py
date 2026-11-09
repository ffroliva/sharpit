"""Secrets in a driver error never reach database-advisor output (0.5.0 scenario row 8; AGENTS.md safety model 3)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from tests.engine.postgresql.fakes import FakeRegistry

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.database_advisor.report import DatabaseAdvisorService, run_scan
from sharpit.engine.context import SharpitContext
from sharpit.settings import load_settings

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())


class _Introspector:
    def app_info(self) -> Any:
        return None

    def routes(self) -> list[Any]:
        return []

    def providers(self) -> list[Any]:
        return []


def _scan_failing_with(error: Exception, tmp_path: Any) -> dict[str, Any]:
    def refuse() -> Any:
        raise error

    engine = sa.create_engine("sqlite://", creator=refuse)
    ctx = SharpitContext(
        load_settings({"config_scan": False, "state_dir": str(tmp_path)}, {}), ACTIVATION, _Introspector()
    )
    ctx.capture.engine_registry = FakeRegistry(("db", engine))  # type: ignore[assignment]
    service = DatabaseAdvisorService(_store(tmp_path), ctx.masker, max_retained=100)
    return asyncio.run(run_scan(ctx, service))


def _store(tmp_path: Any) -> Any:
    from sharpit.engine.advisors.dismissals import DismissalStore

    return DismissalStore(tmp_path)


def test_driver_error_dsn_password_masked(tmp_path: Any) -> None:
    report = _scan_failing_with(OSError('could not connect to "postgresql://app:dsn-pw-1@db:5432/app"'), tmp_path)

    assert [d["status"] for d in report.get("dataSources", [])] == ["FAILED"]
    assert "dsn-pw-1" not in json.dumps(report)


def test_statement_text_masked(tmp_path: Any) -> None:
    # a driver error carries the statement on the lines after its message: none of it is kept
    error = OSError("syntax error at or near SELECT\n[SQL: SELECT * FROM users WHERE api_key = 'stmt-secret-2']")

    report = _scan_failing_with(error, tmp_path)

    assert [d["status"] for d in report.get("dataSources", [])] == ["FAILED"]
    assert "stmt-secret-2" not in json.dumps(report)
