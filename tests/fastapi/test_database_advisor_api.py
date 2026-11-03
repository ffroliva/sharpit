"""``database-advisor`` panel routes and tools (0.5.0 plan A-dbadv-1 Tasks 1 and 4; WAVE-A §4).

``GET {api}/database-advisor`` serves the last scan (initially ``NOT_SCANNED``) and never connects; ``POST .../scan``
reads every registered engine through ``run_db_read(read_only=True)`` and evaluates the rules;
``GET .../rules/{id}/violations`` pages the retained details. MCP lists the two reads; the scan is CLI-only (§14).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.engine.postgresql.fakes import FakePgEngine, FakeRegistry

import golden
from fastapi import FastAPI
from sharpit import install
from sharpit.engine import sqla
from sharpit.engine.collectors.database_advisor.report import OPERATION
from sharpit.engine.singleflight import SingleFlight

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")
StaticPool = pytest.importorskip("sqlalchemy.pool").StaticPool

LOCAL = ("127.0.0.1", 50000)
URL = "/sharpit/api/database-advisor"
SCAN = f"{URL}/scan"


def _sqlite(*ddl: str) -> Any:
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        for statement in ddl:
            conn.exec_driver_sql(statement)
    return engine


def _client(*engines: tuple[str, Any], **options: Any) -> tuple[TestClient, Any]:
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **options})
    handle.context.capture.engine_registry = FakeRegistry(*engines)
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False), handle.context


def _ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return response.json()


def _mcp(client: TestClient, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, **({"params": params} if params else {})}
    response = client.post("/sharpit/api/mcp", content=json.dumps(body), headers={"content-type": "application/json"})
    return response.json()


def test_report_golden_parity() -> None:
    client, _ = _client()
    report = _ok(client.get(URL))

    golden.assert_parity("database-advisor", "report", report)
    golden.assert_enum_values("database-advisor", "report", report)


def test_post_scan_golden_parity() -> None:
    folder = golden.ROOT / "database-advisor"
    if not (folder / "scanned.captured.json").is_file() or not (folder / "violations.captured.json").is_file():
        pytest.skip("post-scan golden absent (G0)")
    client, _ = _client(("db", _sqlite("CREATE TABLE audit_log (at TEXT)")))
    scanned = client.post(SCAN).json()
    rule = scanned["results"][0]["id"]
    page = client.get(f"{URL}/rules/{rule}/violations", params={"scanId": scanned["violationDetails"]["scanId"]})

    golden.assert_parity("database-advisor", "scanned", scanned)
    golden.assert_enum_values("database-advisor", "scanned", scanned)
    golden.assert_parity("database-advisor", "violations", page.json())


def test_scan_reports_schema_findings_on_sqlite() -> None:
    engine = _sqlite("CREATE TABLE audit_log (at TEXT)", "CREATE TABLE orders (id INTEGER PRIMARY KEY)")
    client, _ = _client(("db", engine))

    report = _ok(client.post(SCAN))

    assert report["scan"]["status"] == "SCANNED"
    assert report["dataSourceNames"] == ["db"]
    assert report["tablesAnalyzed"] == 2
    assert [r["id"] for r in report["results"]] == ["DB-SCHEMA-001"]
    assert client.get(URL).json() == report


def test_get_before_a_scan_never_connects() -> None:
    engine = FakePgEngine()
    client, _ = _client(("primary", engine))

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json()["scan"]["status"] == "NOT_SCANNED"
    assert engine.connects == 0


def test_dbadv_read_uses_verified_read_only_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # PLAN Review Focus 1: the scan reads through bounded_read_only, never bounded()
    calls: list[str] = []
    real = sqla.readonly.bounded_read_only
    monkeypatch.setattr(sqla.readonly, "bounded", lambda *a, **k: calls.append("bounded"))
    monkeypatch.setattr(sqla.readonly, "bounded_read_only", lambda *a, **k: calls.append("ro") or real(*a, **k))
    client, _ = _client(("db", _sqlite("CREATE TABLE orders (id INTEGER PRIMARY KEY)")))

    report = _ok(client.post(SCAN))

    assert calls == ["ro"]
    assert [d["status"] for d in report["dataSources"]] == ["AVAILABLE"]


def test_autocommit_engine_is_unavailable() -> None:
    # scenario row 22: an engine sharpit cannot pin read-only is reported, and no catalog statement runs
    engine = FakePgEngine()
    engine.conn.connection = type("Conn", (), {"dbapi_connection": type("Dbapi", (), {"autocommit": True})()})()
    client, _ = _client(("primary", engine))

    report = _ok(client.post(SCAN))

    assert [(d["status"], d["message"]) for d in report["dataSources"]] == [("FAILED", sqla.READ_ONLY_REFUSED)]
    assert report["scan"]["status"] == "ERROR"
    assert [s for s in engine.conn.sql if not s.startswith(("SET ", "SELECT current_setting"))] == []


@pytest.mark.parametrize("options", [{"read_only": True}, {"panels": {"database-advisor": {"read_only": True}}}])
def test_read_only_blocks_scan(options: dict[str, Any]) -> None:
    engine = FakePgEngine()
    client, _ = _client(("primary", engine), **options)

    assert client.get(URL).status_code == 200
    assert client.post(SCAN).status_code == 403
    assert engine.connects == 0


def test_inactive_database_advisor_paths_404() -> None:
    app = FastAPI()
    install(app, enabled="OFF", show_banner=False, config_scan=False)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    statuses = [
        client.get(URL).status_code,
        client.post(SCAN).status_code,
        client.get(f"{URL}/rules/DB-SCHEMA-001/violations").status_code,
    ]

    assert statuses == [404, 404, 404]


def test_disabled_panel_is_403() -> None:
    client, _ = _client(panels={"database-advisor": {"enabled": False}})

    assert [client.get(URL).status_code, client.post(SCAN).status_code] == [403, 403]


def test_concurrent_scan_409() -> None:
    client, ctx = _client()
    release = ctx.lazy(f"singleflight:{OPERATION}", SingleFlight).try_acquire("other")

    response = client.post(SCAN)
    assert release is not None
    release()

    assert response.status_code == 409
    assert response.json()["operation"] == OPERATION


def test_mcp_tools_list_has_only_get() -> None:
    client, _ = _client(mcp_enabled="ON")

    names = [t["name"] for t in _mcp(client, "tools/list")["result"]["tools"] if "database_advisor" in t["name"]]

    assert sorted(names) == ["get_database_advisor_report", "get_database_advisor_rule_violations"]


def test_cli_scan_and_commands() -> None:
    from sharpit.engine import tools

    client, _ = _client(("db", _sqlite("CREATE TABLE audit_log (at TEXT)")))
    response = client.post("/sharpit/api/cli/tools/database_advisor_scan", content=b"{}")

    assert response.status_code == 200
    assert client.get(URL).json()["scan"]["status"] == "SCANNED"
    assert {
        k: tools.COMMANDS.get(k)
        for k in ("database_advisor_scan", "get_database_advisor_report", "get_database_advisor_rule_violations")
    } == {
        "database_advisor_scan": "db scan",
        "get_database_advisor_report": "db report",
        "get_database_advisor_rule_violations": "db violations",
    }


def test_changes_and_rule_detail_routes() -> None:
    # BootUI 2.2.0 DatabaseAdvisorController has no changes or rule-detail route: changes ride in
    # violationDetails.changes and a rule's detail is its violations page. Built exactly as the controller does.
    client, _ = _client(("db", _sqlite("CREATE TABLE audit_log (at TEXT)")))
    scanned = _ok(client.post(SCAN))
    scan_id = scanned["violationDetails"]["scanId"]

    page = client.get(f"{URL}/rules/DB-SCHEMA-001/violations", params={"scanId": scan_id, "offset": 0, "limit": 5})
    missing = client.get(f"{URL}/rules/DB-SCHEMA-001/violations")
    absent = [client.get(f"{URL}/{suffix}").status_code for suffix in ("changes", "rules/DB-SCHEMA-001")]

    assert page.status_code == 200
    assert page.json()["page"]["returned"] == 1
    assert missing.status_code == 400
    assert missing.json() == {"error": "Advisor scan ID must not be blank."}
    assert "changes" in scanned["violationDetails"]
    assert absent == [404, 404]


def test_query_string_secret_never_read_or_emitted() -> None:
    # spec §5.8: ?password=x&sslpassword=y&token=z: no value in the report or in MCP output
    url = "postgresql+psycopg://app@localhost/app?password=qs-x1&sslpassword=qs-y2&token=qs-z3"
    pytest.importorskip("psycopg")

    def refuse() -> Any:
        raise OSError("no server in this test")

    engine = sa.create_engine(url, creator=refuse)
    client, _ = _client(("primary", engine), mcp_enabled="ON")

    response = client.post(SCAN)
    scanned = response.text
    called = _mcp(client, "tools/call", {"name": "get_database_advisor_report", "arguments": {}})

    assert response.status_code == 200
    assert "qs-" not in scanned
    assert "qs-" not in json.dumps(called)
    assert "dataSourceNames" in json.dumps(called)
