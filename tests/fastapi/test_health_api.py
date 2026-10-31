"""Health endpoints (F8, spec §7.8, §14.1): GET shows the cached run, POST check runs under single-flight."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.health import OPERATION, health_service
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
