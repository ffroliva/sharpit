"""Alembic endpoints (F6, spec §7.6): GET shows the files and the cached read, only POST refresh reads the database.

Derived cases: BootUI's Flyway panel has the same DTO (``FlywayDatabaseDto``) but reads through Flyway's API.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.alembic import NEVER_RUNS, NO_ENGINE, NOT_READ, OPERATION

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")

LINEAR = Path(__file__).resolve().parents[1] / "fixtures" / "alembic" / "linear" / "alembic.ini"
LOCAL = ("127.0.0.1", 50000)
URL = "/sharpit/api/alembic/migrations"
REFRESH = "/sharpit/api/alembic/refresh"


def _client(engines: list[Any] | None = None, **options: Any) -> TestClient:
    app = FastAPI()
    settings = {"enabled": "ON", "show_banner": False, "alembic_config": str(LINEAR), **options}
    install(app, engines=engines or [], **settings)
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _engine(tmp_path: Path, *versions: str) -> Any:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        for version in versions:
            conn.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (version,))
    return engine


def _states(database: dict[str, Any]) -> list[tuple[str, str]]:
    return [(m["version"], m["state"]) for m in database["migrations"]]


def _checkouts(engine: Any) -> list[int]:
    calls: list[int] = []
    sa.event.listen(engine, "checkout", lambda *_a: calls.append(1))
    return calls


def test_get_never_connects(tmp_path: Path):
    engine = _engine(tmp_path, "b2")
    checkouts = _checkouts(engine)
    body = _client([engine]).get(URL).json()
    assert checkouts == []
    assert (body["alembicPresent"], body["total"], body["heads"]) == (True, 3, ["c3"])
    (database,) = body["databases"]
    assert (database["name"], database["checkedAt"], database["currentVersion"]) == (NOT_READ, None, None)
    assert {state for _v, state in _states(database)} == {"Unknown"}


def test_shape_matches_flyway_dto(tmp_path: Path):
    body = _client([_engine(tmp_path, "b2")]).get(URL).json()
    assert list(body) == ["alembicPresent", "configPath", "total", "heads", "databases"]
    (database,) = body["databases"]
    assert list(database) == [
        "name", "currentVersion", "applied", "pending", "total", "migrations", "migrateEnabled",
        "migrateDisabledReason", "cleanEnabled", "cleanDisabledReason", "checkedAt", "unavailableReason",
    ]  # fmt: skip
    assert list(database["migrations"][0]) == [
        "type", "version", "description", "script", "state", "installedBy", "installedOn", "installedRank",
        "executionTime", "checksum",
    ]  # fmt: skip
    assert (database["migrateEnabled"], database["cleanEnabled"]) == (False, False)
    assert database["migrateDisabledReason"] == database["cleanDisabledReason"] == NEVER_RUNS


def test_refresh_reads_sync_engine(tmp_path: Path):
    engine = _engine(tmp_path, "b2")
    client = _client([engine])
    resp = client.post(REFRESH)
    assert resp.status_code == 200
    (database,) = resp.json()["databases"]
    assert _states(database) == [("a1", "Success"), ("b2", "Success"), ("c3", "Pending")]
    assert (database["currentVersion"], database["applied"], database["pending"]) == ("b2", 2, 1)
    assert isinstance(database["checkedAt"], int) and database["unavailableReason"] is None
    assert client.get(URL).json()["databases"] == [database]  # the GET shows the cached read


def test_refresh_reads_aiosqlite(tmp_path: Path):
    pytest.importorskip("aiosqlite")
    _engine(tmp_path, "c3").dispose()
    asyncio_ext = pytest.importorskip("sqlalchemy.ext.asyncio")
    engine = asyncio_ext.create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    (database,) = _client([engine]).post(REFRESH).json()["databases"]
    assert database["unavailableReason"] is None, database
    assert _states(database) == [("a1", "Success"), ("b2", "Success"), ("c3", "Success")]


def test_missing_version_listed(tmp_path: Path):
    (database,) = _client([_engine(tmp_path, "zz9")]).post(REFRESH).json()["databases"]
    assert _states(database)[-1] == ("zz9", "Missing")
    assert {s for v, s in _states(database) if v != "zz9"} == {"Pending"}
    assert (database["applied"], database["pending"], database["total"]) == (1, 3, 4)


def test_not_managed_by_alembic(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'plain.db'}")
    (database,) = _client([engine]).post(REFRESH).json()["databases"]
    assert database["unavailableReason"] == "Not managed by Alembic: no alembic_version table"
    assert database["currentVersion"] is None and {s for _v, s in _states(database)} == {"Unknown"}


def test_no_engine_reason():
    (database,) = _client().post(REFRESH).json()["databases"]
    assert (database["name"], database["unavailableReason"]) == (NOT_READ, NO_ENGINE)


def test_no_config_unavailable(tmp_path: Path):
    client = _client(alembic_config=str(tmp_path / "alembic.ini"))
    body = client.get(URL).json()
    assert (body["alembicPresent"], body["databases"]) == (False, [])
    panel = next(p for p in client.get("/sharpit/api/panels").json()["panels"] if p["id"] == "alembic")
    assert panel["available"] is False and panel["unavailableReason"].startswith("No Alembic configuration")


def _slow_engine(tmp_path: Path, gate: threading.Event, started: threading.Event) -> Any:
    engine = _engine(tmp_path, "b2")

    @sa.event.listens_for(engine, "before_cursor_execute")
    def _hold(*_args: Any) -> None:
        started.set()
        gate.wait(5)

    return engine


def test_timed_out_read_holds_single_flight(tmp_path: Path):
    gate, started = threading.Event(), threading.Event()
    client = _client([_slow_engine(tmp_path, gate, started)], alembic_timeout=0.1)
    try:
        resp = client.post(REFRESH)
        (database,) = resp.json()["databases"]
        assert database["unavailableReason"] == "Reading the database version timed out after 0.1s"
        assert started.is_set()
        busy = client.post(REFRESH)  # the thread still runs: refresh stays busy until it returns
        assert busy.status_code == 409 and busy.json()["activeOperation"] == OPERATION
    finally:
        gate.set()
    for _ in range(200):
        if client.post(REFRESH).status_code == 200:
            break
        threading.Event().wait(0.02)
    else:
        pytest.fail("single-flight was never released")


def test_concurrent_refresh_409(tmp_path: Path):
    gate, started = threading.Event(), threading.Event()
    client = _client([_slow_engine(tmp_path, gate, started)])
    first = threading.Thread(target=client.post, args=(REFRESH,))
    first.start()
    try:
        assert started.wait(5)
        busy = client.post(REFRESH)
    finally:
        gate.set()
        first.join(5)
    assert busy.status_code == 409
    assert busy.json()["operation"] == OPERATION


@pytest.mark.parametrize("options", [{"read_only": True}, {"panels": {"alembic": {"read_only": True}}}])
def test_refresh_read_only_403(tmp_path: Path, options: dict[str, Any]):
    engine = _engine(tmp_path, "b2")
    checkouts = _checkouts(engine)
    client = _client([engine], **options)
    assert client.get(URL).status_code == 200
    assert client.post(REFRESH).status_code == 403
    assert checkouts == []
