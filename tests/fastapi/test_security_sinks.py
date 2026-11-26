"""Task 5: security-sinks setting, journal source, sensor lane and request-end lifecycle."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

from fastapi import BackgroundTasks, FastAPI
from sharpit import install
from sharpit.engine.guard import PANEL_ACCESS_DENIED
from sharpit.engine.panels import read_only_reason
from sharpit.engine.sensors import audit
from sharpit.fastapi.adapter import SharpitHandle

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api"
SWITCH = f"{API}/java-agent/sensors"
SECURITY_SINKS_OPT_IN_REASON = (
    "Off by default: its request-value matching, which also needs"
    " SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES=true, holds each request's query and path values in memory while it"
    " runs."
)


class Hook:
    def __init__(self, hooks: list[Any]) -> None:
        self.hooks = hooks

    def fire(self, event: str, *args: Any) -> None:
        for hook in self.hooks:
            hook(event, args)


@pytest.fixture
def hook(recorded_audit_hook: list[Any]) -> Iterator[Hook]:
    yield Hook(recorded_audit_hook)


def _app(tmp_path: Path, **options: Any) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()
    handle = install(
        app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(tmp_path / "state"), **options
    )
    return app, handle


def _client(app: FastAPI, *, raise_server_exceptions: bool = True) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=raise_server_exceptions)


def _rows(handle: SharpitHandle, source: str) -> tuple[dict[str, object], ...]:
    journal = handle.context.capture.journal
    assert journal is not None
    return journal.records(source)


def _held(handle: SharpitHandle) -> int:
    lane = handle.context.capture.sensors
    if lane is None:
        return 0
    sensor = cast("Any", lane)._sensors.get("security-sinks")
    if sensor is None:
        return 0
    return int(sensor.matcher._values.held())


def test_off_by_default_a_request_value_in_a_path_leaves_no_sink_row(tmp_path: Path, hook: Hook) -> None:
    app, handle = _app(tmp_path, agent_sensors=("processes", "files", "security-sinks"))

    @app.get("/read/{name}")
    def read_path(name: str) -> str:
        hook.fire("open", f"reports/{name}.csv", "r", 0)
        return name

    with _client(app) as client:
        assert client.get("/read/quarterly").status_code == 200
        toggles = client.get(f"{API}/java-agent").json()["toggles"]
    handle.uninstall_capture()
    assert _rows(handle, "security-sinks") == ()
    assert [r["target"] for r in _rows(handle, "files")] == ["./reports/quarterly.csv"]
    assert [t["id"] for t in toggles] == ["files"]


def test_an_endpoint_that_opens_a_requested_path_leaves_one_sink_row(tmp_path: Path, hook: Hook) -> None:
    app, handle = _app(
        tmp_path,
        agent_sensors=("processes", "files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )

    @app.get("/read/{name}")
    def read_path(name: str) -> str:
        hook.fire("open", f"reports/{name}.csv", "r", 0)
        return name

    with _client(app) as client:
        assert client.get("/read/quarterly").status_code == 200
        toggles = client.get(f"{API}/java-agent").json()["toggles"]
    handle.uninstall_capture()
    sink_rows = _rows(handle, "security-sinks")
    assert len(sink_rows) == 1
    assert sink_rows[0]["parameter"] == "name"
    assert sink_rows[0]["kind"] == "file-path"
    assert sink_rows[0]["target"] == "./reports/{name}.csv"
    assert [r["target"] for r in _rows(handle, "files")] == ["./reports/{name}.csv"]
    by_id = {t["id"]: t for t in toggles}
    assert "security-sinks" in by_id
    assert by_id["security-sinks"]["optInReason"] == SECURITY_SINKS_OPT_IN_REASON


@pytest.mark.parametrize("mode", ["normal", "exception", "disconnect", "stream"])
def test_values_are_gone_when_the_response_ends(tmp_path: Path, hook: Hook, mode: str) -> None:
    app, handle = _app(
        tmp_path,
        agent_sensors=("files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )
    during: list[int] = []

    @app.get("/work")
    async def work(q: str) -> Any:
        if mode == "stream":

            async def body() -> AsyncIterator[bytes]:
                hook.fire("open", f"reports/{q}.csv", "r", 0)
                during.append(_held(handle))
                yield b"chunk"

            return StreamingResponse(body(), media_type="text/plain")
        hook.fire("open", f"reports/{q}.csv", "r", 0)
        during.append(_held(handle))
        if mode == "exception":
            raise RuntimeError("boom")
        return "ok"

    if mode == "disconnect":
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/work",
            "raw_path": b"/work",
            "root_path": "",
            "query_string": b"q=quarterly",
            "headers": [(b"host", b"localhost")],
            "client": LOCAL,
            "server": ("localhost", 80),
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.disconnect"}

        async def send(_message: dict[str, Any]) -> None:
            return None

        asyncio.run(app(scope, receive, send))
    else:
        with _client(app, raise_server_exceptions=(mode != "exception")) as client:
            client.get("/work?q=quarterly")
    handle.uninstall_capture()
    assert during == [1]
    assert _held(handle) == 0


@pytest.mark.parametrize("how", ["switch", "pause", "suspend", "detach"])
def test_switching_the_sensor_off_wipes_held_values_at_once(
    tmp_path: Path, hook: Hook, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    monkeypatch.setenv("SHARPIT_PANELS_JAVA_AGENT_READ_ONLY", "false")
    app, handle = _app(
        tmp_path,
        agent_sensors=("files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )
    seen: list[tuple[int, int]] = []

    @app.get("/work")
    def work(q: str) -> str:
        hook.fire("open", f"reports/{q}.csv", "r", 0)
        before = _held(handle)
        lane = handle.context.capture.sensors
        assert lane is not None
        if how == "switch":
            lane.switch("security-sinks", False)
        elif how == "pause":
            lane.pause("security-sinks")
        elif how == "detach":
            lane.detach()
        else:
            for registered in handle.context.capture.hooks.hooks():
                if registered.name == "security-sinks":
                    registered.suspend()
        after = _held(handle)
        seen.append((before, after))
        return "ok"

    with _client(app) as client:
        assert client.get("/work?q=quarterly").status_code == 200
    handle.uninstall_capture()
    assert seen == [(1, 0)]
    assert _held(handle) == 0


def test_a_paused_sensor_checks_nothing(tmp_path: Path, hook: Hook) -> None:
    app, handle = _app(
        tmp_path,
        agent_sensors=("files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )
    during: list[int] = []

    @app.get("/read/{name}")
    def read_path(name: str) -> str:
        hook.fire("open", f"reports/{name}.csv", "r", 0)
        during.append(_held(handle))
        return name

    lane = handle.context.capture.sensors
    assert lane is not None
    assert "security-sinks" in lane.names
    lane.pause("security-sinks")
    with _client(app) as client:
        assert client.get("/read/quarterly").status_code == 200
    handle.uninstall_capture()
    assert during == [0]
    assert _held(handle) == 0
    assert _rows(handle, "security-sinks") == ()
    assert [r["target"] for r in _rows(handle, "files")] == ["./reports/quarterly.csv"]


def test_a_background_task_and_a_streamed_body_leave_no_sink_row(tmp_path: Path, hook: Hook) -> None:
    app, handle = _app(
        tmp_path,
        agent_sensors=("files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )

    @app.get("/bg/{name}")
    def with_bg(name: str, tasks: BackgroundTasks) -> str:
        tasks.add_task(hook.fire, "open", f"reports/{name}.csv", "r", 0)
        return "ok"

    @app.get("/stream/{name}")
    def with_stream(name: str) -> StreamingResponse:
        def body() -> Iterator[bytes]:
            hook.fire("open", f"reports/{name}.csv", "r", 0)
            yield b"ok"

        return StreamingResponse(body(), media_type="text/plain")

    with _client(app) as client:
        assert client.get("/bg/quarterly").status_code == 200
        assert client.get("/stream/quarterly").status_code == 200
    handle.uninstall_capture()
    assert _rows(handle, "security-sinks") == ()
    assert [r["target"] for r in _rows(handle, "files")] == ["./reports/{name}.csv", "./reports/{name}.csv"]


def test_a_read_only_panel_refuses_the_switch(tmp_path: Path, hook: Hook, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHARPIT_PANELS_JAVA_AGENT_READ_ONLY", "true")
    app, handle = _app(
        tmp_path,
        agent_sensors=("files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )

    @app.get("/read/{name}")
    def read_path(name: str) -> str:
        hook.fire("open", f"reports/{name}.csv", "r", 0)
        return name

    with _client(app) as client:
        resp = client.post(f"{SWITCH}/security-sinks", json={"enabled": False})
        assert client.get("/read/quarterly").status_code == 200
    handle.uninstall_capture()
    assert resp.status_code == 403
    assert resp.json() == {
        "error": PANEL_ACCESS_DENIED,
        "panel": "java-agent",
        "reason": read_only_reason("java-agent", False),
    }
    assert len(_rows(handle, "security-sinks")) == 1


def test_an_inactive_console_holds_no_request_values_and_installs_no_hook(tmp_path: Path, hook: Hook) -> None:
    app = FastAPI()

    @app.get("/read/{name}")
    def read_path(name: str) -> str:
        hook.fire("open", f"reports/{name}.csv", "r", 0)
        return name

    handle = install(
        app,
        enabled="OFF",
        show_banner=False,
        config_scan=False,
        state_dir=str(tmp_path / "state"),
        agent_sensors=("processes", "files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )
    with _client(app) as client:
        assert client.get("/read/quarterly").status_code == 200
    assert handle.context.capture.sensors is None
    assert audit.hub.installed is False
    assert hook.hooks == []


def test_a_middleware_that_copies_the_scope_degrades_without_error(tmp_path: Path, hook: Hook) -> None:
    app = FastAPI()

    @app.get("/read/{name}")
    def read_path(name: str, q: str) -> dict[str, str]:
        hook.fire("open", f"reports/{q}.csv", "r", 0)
        return {"name": name, "q": q}

    class CopyScopeMiddleware:
        def __init__(self, inner: Any) -> None:
            self.inner = inner

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            await self.inner(dict(scope), receive, send)

    app.add_middleware(CopyScopeMiddleware)
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        state_dir=str(tmp_path / "state"),
        agent_sensors=("files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )
    with _client(app) as client:
        resp = client.get("/read/quarterly?q=secret-report")
    handle.uninstall_capture()
    assert resp.status_code == 200
    assert resp.json() == {"name": "quarterly", "q": "secret-report"}
    assert [r["target"] for r in _rows(handle, "files")] == ["./reports/{q}.csv"]
    assert _rows(handle, "security-sinks") == ()
    assert _held(handle) == 0


def test_a_second_install_records_a_path_its_matcher_does_not_own(tmp_path: Path, hook: Hook) -> None:
    # scenario: plan-1 row 14
    app_a = FastAPI()
    app_b = FastAPI()
    handle_a = install(
        app_a,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        state_dir=str(tmp_path / "a"),
        agent_sensors=("files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )
    handle_b = install(
        app_b,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        state_dir=str(tmp_path / "b"),
        agent_sensors=("files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )

    @app_a.get("/read/{name}")
    def read_path(name: str) -> str:
        hook.fire("open", f"reports/{name}.csv", "r", 0)
        return name

    with _client(app_a) as client:
        assert client.get("/read/quarterly").status_code == 200
    lane_a = handle_a.context.capture.sensors
    lane_b = handle_b.context.capture.sensors
    assert lane_a is not None
    assert lane_b is not None
    assert _rows(handle_a, "files")[0]["target"] == "./reports/{name}.csv"
    assert _rows(handle_b, "files")[0]["target"] == "./reports/quarterly.csv"
    assert "reports/quarterly.csv" in lane_b._sensors["files"]._seen
    handle_a.uninstall_capture()
    handle_b.uninstall_capture()


def test_executor_and_raw_thread_file_events_are_recorded_without_redaction(tmp_path: Path, hook: Hook) -> None:
    # scenario: plan-1 row 15
    app, handle = _app(
        tmp_path,
        agent_sensors=("files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )

    @app.get("/work")
    async def work(q: str) -> str:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, hook.fire, "open", f"reports/{q}-executor.csv", "r", 0)
        thread = threading.Thread(target=hook.fire, args=("open", f"reports/{q}-thread.csv", "r", 0))
        thread.start()
        thread.join()
        return "ok"

    with _client(app) as client:
        assert client.get("/work?q=quarterly").status_code == 200
    handle.uninstall_capture()
    assert [row["target"] for row in _rows(handle, "files")] == [
        "./reports/quarterly-executor.csv",
        "./reports/quarterly-thread.csv",
    ]
    assert _rows(handle, "security-sinks") == ()


def test_enabling_security_sinks_without_request_value_setting_keeps_the_existing_refusal(
    tmp_path: Path, hook: Hook
) -> None:
    # scenario: plan-1 row 22
    app, handle = _app(tmp_path, agent_sensors=("files",))
    with _client(app) as client:
        response = client.post(
            f"{API}/cli/tools/enable_agent_sensor",
            json={"id": "security-sinks"},
        )
    handle.uninstall_capture()
    assert response.status_code == 409
    assert response.json() == {
        "error": "The sharpit agent is not armed for this application, so its sensors cannot be switched: "
        "This process runs without the sharpit agent. sharpit works without it; enable its sensors with"
        " SHARPIT_AGENT_SENSORS to add agent-based evidence."
    }


def test_security_sinks_alone_installs_an_inert_audit_hook(tmp_path: Path, hook: Hook) -> None:
    # scenario: plan-1 row 30
    app, handle = _app(
        tmp_path,
        agent_sensors=("security-sinks",),
        agent_security_sinks_request_values=True,
    )
    lane = handle.context.capture.sensors
    assert lane is not None
    assert lane.names == ("files", "security-sinks")
    assert lane.is_on("files") is False
    assert lane.is_on("security-sinks") is True
    assert audit.hub.installed is True
    assert len(hook.hooks) == 1
    hook.fire("open", "reports/quarterly.csv", "r", 0)
    assert _rows(handle, "files") == ()
    assert _rows(handle, "security-sinks") == ()
    handle.uninstall_capture()


def test_a_static_files_mount_holds_no_path_value_and_publishes_no_sink(
    tmp_path: Path, hook: Hook, monkeypatch: pytest.MonkeyPatch
) -> None:
    # scenario: plan-1 row 17: Starlette's Mount consumes {path}, so a StaticFiles request holds no path value
    monkeypatch.chdir(tmp_path)
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "quarterly.css").write_text("body {}")
    app, handle = _app(
        tmp_path,
        agent_sensors=("processes", "files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )

    class Opening(StaticFiles):
        async def get_response(self, path: str, scope: Any) -> Any:
            hook.fire("open", f"static/{path}", "r", 0)
            return await super().get_response(path, scope)

    app.mount("/static", Opening(directory="static"), name="static")
    with _client(app) as client:
        assert client.get("/static/quarterly.css").status_code == 200
    handle.uninstall_capture()
    assert [r["target"] for r in _rows(handle, "files")] == ["./static/quarterly.css"]
    assert _rows(handle, "security-sinks") == ()


def test_an_spa_catch_all_route_redacts_its_path_value(tmp_path: Path, hook: Hook) -> None:
    # scenario: plan-1 row 17: a catch-all route keeps {path}, so an owned open inside the endpoint is redacted
    app, handle = _app(
        tmp_path,
        agent_sensors=("processes", "files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )

    @app.get("/{path:path}")
    def catch_all(path: str) -> str:
        hook.fire("open", f"static/{path}", "r", 0)
        return path

    with _client(app) as client:
        assert client.get("/quarterly.css").status_code == 200
    handle.uninstall_capture()
    sink_rows = _rows(handle, "security-sinks")
    assert [r["target"] for r in _rows(handle, "files")] == ["./static/{path}"]
    assert [r["parameter"] for r in sink_rows] == ["path"]
