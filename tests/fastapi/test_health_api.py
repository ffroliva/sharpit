"""Health endpoints (F8, spec §7.8, §14.1): GET shows the cached run, POST check runs under single-flight."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.health import OPERATION, health_service
from sharpit.engine.sqla import SHARED_CONNECTION_REFUSED
from sharpit.fastapi.adapter import SharpitHandle

LOCAL = ("127.0.0.1", 50000)
URL = "/sharpit/api/health"
CHECK = "/sharpit/api/health/check"


def _client(**options: Any) -> tuple[TestClient, SharpitHandle]:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, **options)
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False), handle


def _health_threads() -> set[int]:
    return {t.ident or 0 for t in threading.enumerate() if t.name.startswith("sharpit-health")}


def test_timed_out_check_holds_single_flight():
    gate, started = threading.Event(), threading.Event()

    def stuck() -> bool:
        started.set()
        return gate.wait(5)

    client, _handle = _client(health_timeout=0.1, health_checks={"stuck": stuck})
    try:
        first = client.post(CHECK)
        part = next(c for c in first.json()["components"] if c["name"] == "stuck")
        assert (part["status"], part["details"]["error"]) == ("DOWN", "timed out after 0.1s; still running")
        assert started.is_set()
        busy = client.post(CHECK)  # the check's thread still runs: health-check stays busy until it returns
        assert busy.status_code == 409
        assert busy.json()["activeOperation"] == OPERATION
    finally:
        gate.set()
    for _ in range(200):
        resp = client.post(CHECK)
        if resp.status_code == 200:
            assert resp.json()["status"] == "UP"
            break
        threading.Event().wait(0.02)
    else:
        pytest.fail("single-flight was never released")


def test_executor_created_on_first_check_only():
    before = _health_threads()
    client, handle = _client(health_checks={"ok": lambda: True})
    assert client.get(URL).status_code == 200
    service = health_service(handle.context)
    assert service._executor is None
    assert _health_threads() <= before
    assert client.post(CHECK).status_code == 200
    assert service._executor is not None
    assert _health_threads() - before


def _open_host_transaction(engine: Any) -> tuple[Any, Any]:
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE t (x INTEGER)")
    host = engine.connect()
    transaction = host.begin()
    host.exec_driver_sql("INSERT INTO t VALUES (1)")
    return host, transaction


def _committed_rows(engine: Any, host: Any, transaction: Any) -> int:
    transaction.commit()
    host.close()
    with engine.connect() as conn:
        return conn.exec_driver_sql("SELECT count(*) FROM t").scalar()


# derived: release council probe p1b_e2e.py: the ping's checkin rolled the host's open transaction back
def test_check_on_a_sharing_pool_keeps_the_hosts_open_transaction():
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    client, _handle = _client(engines=[engine])
    host, transaction = _open_host_transaction(engine)

    assert client.post(CHECK).status_code == 200

    assert _committed_rows(engine, host, transaction) == 1


# derived: release council fix round 2: a skipped ping says nothing about the database, so never DOWN
@pytest.mark.parametrize("pool", ["StaticPool", "SingletonThreadPool", "AssertionPool"])
def test_check_on_a_sharing_pool_is_unknown_with_its_reason(pool: str):
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine("sqlite://", poolclass=getattr(sa.pool, pool), connect_args={"check_same_thread": False})
    client, _handle = _client(engines=[engine])

    db = next(c for c in client.post(CHECK).json()["components"] if c["name"] == "db")

    (ping,) = db["components"]
    assert (ping["status"], ping["details"].get("error")) == ("UNKNOWN", SHARED_CONNECTION_REFUSED)
