from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.fastapi.capture import wiring_of


def _client(**options: object) -> TestClient:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, **options)
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), follow_redirects=False)


def test_low_footprint_toggle_refused_read_only() -> None:
    # ported: McpDispatcherTests.lowFootprintUsesLiveMemoryPolicyForAllControlsWithoutInvokingRefusedActions
    response = _client(panels={"live-memory": {"read_only": True}}).post("/sharpit/api/low-footprint/enable")
    assert response.status_code == 403
    assert response.json()["reason"] == "Panel is read-only via SHARPIT_PANELS_LIVE_MEMORY_READ_ONLY=true"


def test_low_footprint_route_obeys_authentication_guard() -> None:
    app = FastAPI()
    install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        authentication_token="a" * 32,
        allow_non_localhost=True,
    )
    client = TestClient(app, base_url="http://localhost", client=("10.0.0.5", 50000))
    response = client.get("/sharpit/api/low-footprint")
    assert response.status_code == 401


def test_low_footprint_status_has_bootui_dto_keys(no_side_effects: SideEffectGuard) -> None:
    no_side_effects.unblock_network()
    with _client(state_dir=str(no_side_effects.state_dir)) as client:
        no_side_effects.block_network()
        response = client.get("/sharpit/api/low-footprint")
    assert response.status_code == 200
    assert set(response.json()) == {"active", "sinceEpochMillis", "agentAttached", "components", "warnings", "offload"}
    assert no_side_effects.violations == []


def test_enabling_low_footprint_clears_each_capture_panel_feed() -> None:
    from sharpit.engine.capture.traces import span_buffer
    from sharpit.engine.sqltext import Dialect

    app = FastAPI()
    app.add_api_route("/seed", lambda: {"ok": True})
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        panels={
            name: {"enabled": True}
            for name in (
                "activity",
                "exceptions",
                "http-exchanges",
                "log-tail",
                "security-logs",
                "sql-trace",
                "traces",
                "transactions",
            )
        },
    )
    ctx = handle.context
    ctx.capture.security_logs.add("TEST", None, {}, None)
    ctx.capture.log_tail.append(
        {
            "timestamp": "now",
            "level": "INFO",
            "logger": "test",
            "message": "entry",
            "thread": "test",
            "messageOmitted": False,
        }
    )
    ctx.capture.exceptions.record(ValueError("entry"), "test", None, "test")
    ctx.capture.sql_trace.record(
        "SELECT 1", duration_ns=1_000, thread="test", connection_id=None, dialect=Dialect.SQLITE
    )
    ctx.capture.transactions.begin(1, parent=None, method="test", thread="test", trace_id=None, connection_id=None)
    span_buffer(ctx).add(object())

    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        client.get("/seed")
        enabled = client.post("/sharpit/api/low-footprint/enable")

        assert enabled.status_code == 200
        assert client.get("/sharpit/api/http-exchanges").json()["total"] == 0
        assert client.get("/sharpit/api/activity").json()["entries"] == []
        assert client.get("/sharpit/api/security-logs").json()["events"] == []
        assert client.get("/sharpit/api/log-tail/recent").json() == []
        assert client.get("/sharpit/api/sql-trace/insights").json()["window"]["retainedStatements"] == 0
        assert client.get("/sharpit/api/traces").json()["retained"] == 0
        assert client.get("/sharpit/api/transactions").json()["entries"] == []


def test_free_on_idle_suspends_and_resumes_capture_in_lifespan(monkeypatch) -> None:
    import sharpit.fastapi.install as install_module

    now = [10.0]
    monkeypatch.setattr(install_module, "_clock", lambda: now[0])
    app = FastAPI()
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        free_on_idle_enabled=True,
        free_on_idle_timeout="50ms",
    )
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        assert "sharpit-free-on-idle" in {thread.name for thread in threading.enumerate()}
        now[0] += 1
        threading.Event().wait(0.08)
        wiring = wiring_of(handle.context)
        assert wiring is not None
        assert wiring.suspended_hooks
        denied = client.get("/sharpit/api/low-footprint", headers={"Sec-Fetch-Site": "cross-site"})
        assert denied.status_code == 403
        assert wiring.suspended_hooks
        assert client.get("/sharpit/api/low-footprint").json()["active"] is False
        assert wiring.suspended_hooks == set()
    assert "sharpit-free-on-idle" not in {thread.name for thread in threading.enumerate()}


def test_free_on_idle_disabled_starts_no_thread() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, free_on_idle_enabled=False)
    with TestClient(app):
        before = {thread.ident for thread in threading.enumerate()}
        threading.Event().wait(0.04)
        assert {thread.ident for thread in threading.enumerate()} == before
