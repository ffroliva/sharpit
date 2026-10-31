"""Dogfood (spec §15): the fastapi_sqla sample, migrated to 0002 by its own Alembic, drives every 0.2.0 panel."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.needs_sqlalchemy

pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")
pytest.importorskip("alembic")

from examples.fastapi_sqla.app import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

API = "/sharpit/api"
INI = Path(__file__).resolve().parent.parent / "examples" / "fastapi_sqla" / "alembic.ini"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    env = {**os.environ, "SHARPIT_SQLA_DB_DIR": str(db_dir)}
    cmd = [sys.executable, "-m", "alembic", "-c", str(INI), "upgrade", "0002"]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)  # the sample's own tooling
    assert proc.returncode == 0, proc.stderr
    app = create_app(db_dir=db_dir, show_banner=False)
    try:
        with TestClient(
            app, base_url="http://localhost", client=("127.0.0.1", 50000), raise_server_exceptions=False
        ) as test_client:
            yield test_client
    finally:
        app.state.sharpit.uninstall_capture()


def _request_entry(client: TestClient, path: str) -> dict[str, Any]:
    entries = client.get(f"{API}/activity", params={"type": "REQUEST"}).json()["entries"]
    return next(e for e in entries if e["path"] == path)


def test_n_plus_one_flagged(client: TestClient) -> None:
    assert client.get("/owners/n-plus-one").status_code == 200
    entry = _request_entry(client, "/owners/n-plus-one")
    assert entry["sqlNPlusOneSuspected"] is True
    profile = client.get(f"{API}/activity/request/{entry['id']}").json()
    assert any(g["potentialNPlusOne"] for g in profile["sqlGroups"])
    top = client.get(f"{API}/sql-trace").json()["topStatements"]
    assert any(g["potentialNPlusOne"] and "pets" in g["sql"] for g in top)


def test_one_pending_migration_after_refresh(client: TestClient) -> None:
    before = client.get(f"{API}/alembic/migrations").json()
    assert before["databases"][0]["currentVersion"] is None  # GET never connects
    report = client.post(f"{API}/alembic/refresh").json()
    database = report["databases"][0]
    assert (database["currentVersion"], database["applied"], database["pending"]) == ("0002", 2, 1)
    assert [m["version"] for m in database["migrations"] if m["state"] == "Pending"] == ["0003"]


def test_boom_grouped_with_count_two(client: TestClient) -> None:
    assert client.get("/boom").status_code == 500
    assert client.get("/boom").status_code == 500
    groups = [g for g in client.get(f"{API}/exceptions").json()["groups"] if g["exceptionClassName"] == "RuntimeError"]
    assert [(g["count"], g["lastRequestPath"]) for g in groups] == [(2, "/boom")]


def test_background_sql_marked_approximate(client: TestClient) -> None:
    assert client.get("/background").status_code == 200
    entry = _request_entry(client, "/background")
    profile = client.get(f"{API}/activity/request/{entry['id']}").json()
    assert profile["sqlCorrelationApproximate"] is True


def test_sleeper_task_in_threads(client: TestClient) -> None:
    assert client.get("/sleeper").status_code == 200
    tasks = client.get(f"{API}/threads").json()["tasks"]
    assert any(t["name"] == "sleeper" for t in tasks)


def test_rest_api_scan_flags_poor_design(client: TestClient) -> None:
    report = client.post(f"{API}/rest-api/scan").json()
    failed = {r["id"] for r in report["results"] if r["status"] == "FAILED"}
    assert {"RAPI-NAME-001", "RAPI-RESP-001"} <= failed


def test_health_runs_user_check_up(client: TestClient) -> None:
    assert client.post(f"{API}/health/check").status_code == 200
    tree = client.get(f"{API}/health").json()

    def walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
        yield node
        for child in node["components"]:
            yield from walk(child)

    assert [n["status"] for n in walk(tree) if n["name"] == "user"] == ["UP"]


def test_probe_reaches_app_not_sharpit(client: TestClient) -> None:
    owners = client.post(f"{API}/http-probe", json={"method": "GET", "path": "/owners"})
    assert owners.status_code == 200
    assert owners.json()["status"] == 200
    refused = client.post(f"{API}/http-probe", json={"method": "GET", "path": "/sharpit/api/panels"})
    assert refused.status_code in (400, 403)
