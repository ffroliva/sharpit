"""Lane A-dbadv-1 safety rows (0.5.0 spec §4.4, §5.8): GET reads the cached report only; the scan is POST, CLI-only."""

from __future__ import annotations

from typing import Any

import pytest

from conftest import SideEffectGuard

pytestmark = pytest.mark.needs_sqlalchemy

# safety-matrix rows (tests/safety/README.md): read by the shared route-table tests while the flag is true
PANEL = "database-advisor"
GET_ROWS = ["/sharpit/api/database-advisor", "/sharpit/api/database-advisor/rules/{rule_id}/violations"]
WRITE_ROWS = [("POST", "/sharpit/api/database-advisor/scan")]
PATH_PARAMS = {"rule_id": "DB-SCHEMA-001"}
CLI_ACTIONS = ["database_advisor_scan"]


def _violations_args(ctx: Any) -> dict[str, Any]:
    """Scan one keyless table through the context's service, without a database: the facts are handed in."""
    from sharpit.engine.collectors.database_advisor.catalog import Source
    from sharpit.engine.tools04.database_advisor import database_advisor_service

    table = {
        "schema": None,
        "name": "audit_log",
        "truncated": False,
        "columns": [],
        "primaryKey": [],
        "foreignKeys": [],
        "indexes": [],
    }
    catalog = {
        "dialect": "sqlite",
        "tables": [table],
        "tableCount": 1,
        "truncated": False,
        "complete": True,
        "diagnostics": [],
        "server": {},
    }
    report = database_advisor_service(ctx).scan([Source("db", "sqlite", "pysqlite", "AVAILABLE", None, catalog)])
    return {"id": "DB-SCHEMA-001", "scanId": report["violationDetails"]["scanId"]}


TOOL_ARGS = {"get_database_advisor_rule_violations": lambda handle: _violations_args(handle.context)}
TOOL_SEEDS = {"get_database_advisor_rule_violations": _violations_args}


def test_database_advisor_get_no_side_effects(no_side_effects: SideEffectGuard) -> None:
    # a GET never connects, never runs SQL, even with a real engine registered
    sa = pytest.importorskip("sqlalchemy")
    from fastapi.testclient import TestClient
    from tests.engine.postgresql.fakes import FakeRegistry

    from fastapi import FastAPI
    from sharpit import install

    engine = sa.create_engine("postgresql+psycopg://app:secret@localhost:5432/app")
    seen: list[str] = []
    sa.event.listen(engine, "before_cursor_execute", lambda *a: seen.append(a[2]))
    sa.event.listen(engine, "checkout", lambda *_a: seen.append("<checkout>"))
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(no_side_effects.state_dir))
    handle.context.capture.engine_registry = FakeRegistry(("primary", engine))
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), follow_redirects=False)
    with client:
        client.get("/sharpit/api/panels")
        no_side_effects.block_network()
        no_side_effects.rebaseline()  # install() and the engine's dialect import are not the GET under test
        report = client.get("/sharpit/api/database-advisor")
        page = client.get("/sharpit/api/database-advisor/rules/DB-SCHEMA-001/violations", params={"scanId": "x"})

    assert report.status_code == 200
    assert page.status_code == 409
    assert no_side_effects.violations == []
    assert seen == []
