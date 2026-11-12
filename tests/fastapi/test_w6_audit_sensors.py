"""W6 lane S3 through ``install()``: the audit hook is armed only when configured, never by a read, and the sensors
follow the lifespan, the registry and the sensor-switch action (plan W6 scenarios 5, 6, 7).

The real hook cannot be removed, so each test swaps the process hub's ``add_hook`` for a recorder and fires the audit
events by hand.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.guard import PANEL_ACCESS_DENIED
from sharpit.engine.panels import read_only_reason
from sharpit.engine.sensors import audit
from sharpit.engine.tools import TOOLS, CallContext
from sharpit.fastapi.adapter import SharpitHandle

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api"
SWITCH = f"{API}/java-agent/sensors"


class Hook:
    def __init__(self) -> None:
        self.hooks: list[Any] = []

    def __call__(self, hook: Any) -> None:
        self.hooks.append(hook)

    def fire(self, event: str, *args: Any) -> None:
        for hook in self.hooks:
            hook(event, args)


@pytest.fixture
def hook(monkeypatch: pytest.MonkeyPatch) -> Iterator[Hook]:
    recorder = Hook()
    monkeypatch.setattr(audit.hub, "_add_hook", recorder)
    monkeypatch.setattr(audit.hub, "_installed", False)
    yield recorder
    audit.hub.release()


def _app(tmp_path: Path, **options: Any) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()
    handle = install(
        app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(tmp_path / "state"), **options
    )
    return app, handle


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL)


def _rows(handle: SharpitHandle, source: str) -> int:
    journal = handle.context.capture.journal
    assert journal is not None
    return len(journal.records(source))


def test_nothing_installs_the_hook_when_no_sensor_is_configured(tmp_path: Path, hook: Hook) -> None:
    app, handle = _app(tmp_path)
    with _client(app) as client:
        assert client.get(f"{API}/java-agent").status_code == 200
        assert client.get(f"{API}/side-effects").status_code == 200
    assert hook.hooks == []
    assert audit.hub.installed is False
    assert handle.context.capture.sensors is None


def test_a_configured_sensor_installs_one_hook_that_feeds_the_journal(tmp_path: Path, hook: Hook) -> None:
    app, handle = _app(tmp_path, agent_sensors=("processes", "files"))
    assert len(hook.hooks) == 1
    with _client(app):
        hook.fire("os.system", "backup --token hunter2")
        hook.fire("os.remove", "report.csv", None)
    assert _rows(handle, "processes") == 1
    assert _rows(handle, "files") == 1
    handle.uninstall_capture()


def test_a_sensor_configured_with_the_journal_off_builds_nothing(tmp_path: Path, hook: Hook) -> None:
    _, handle = _app(tmp_path, agent_sensors=("files",), runtime_journal_enabled=False)
    assert hook.hooks == []
    assert handle.context.capture.sensors is None


def test_the_lifespan_unbinds_the_sensors_at_shutdown_and_rebinds_at_startup(tmp_path: Path, hook: Hook) -> None:
    app, handle = _app(tmp_path, agent_sensors=("files",))
    with _client(app):
        hook.fire("os.remove", "a.txt", None)
    hook.fire("os.remove", "a.txt", None)  # after shutdown: the hook is still there, and inert
    assert _rows(handle, "files") == 1
    with _client(app):
        hook.fire("os.remove", "a.txt", None)
    assert _rows(handle, "files") == 2
    assert len(hook.hooks) == 1  # restarts never add a second dispatcher
    handle.uninstall_capture()


def test_uninstall_capture_leaves_the_hook_inert(tmp_path: Path, hook: Hook) -> None:
    _, handle = _app(tmp_path, agent_sensors=("files",))
    handle.uninstall_capture()
    hook.fire("os.remove", "a.txt", None)
    assert _rows(handle, "files") == 0
    assert len(hook.hooks) == 1


def test_suspending_the_registry_stops_recording_at_the_hook(tmp_path: Path, hook: Hook) -> None:
    app, handle = _app(tmp_path, agent_sensors=("processes",))
    with _client(app):
        handle.context.capture.hooks.suspend()
        hook.fire("os.system", "echo hi")
        assert _rows(handle, "processes") == 0
        handle.context.capture.hooks.resume()
        hook.fire("os.system", "echo hi")
        assert _rows(handle, "processes") == 1
    handle.uninstall_capture()


def test_the_switch_action_turns_the_files_sensor_off_and_on(
    tmp_path: Path, hook: Hook, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHARPIT_PANELS_JAVA_AGENT_READ_ONLY", "false")
    app, handle = _app(tmp_path, agent_sensors=("files",))
    with _client(app) as client:
        assert client.post(f"{SWITCH}/files", json={"enabled": False}).status_code == 200
        hook.fire("os.remove", "a.txt", None)
        assert _rows(handle, "files") == 0
        assert client.post(f"{SWITCH}/files", json={"enabled": True}).status_code == 200
        hook.fire("os.remove", "a.txt", None)
        assert _rows(handle, "files") == 1
    handle.uninstall_capture()


def test_a_switchable_sensor_that_is_not_configured_switches_on_once_the_lane_exists(
    tmp_path: Path, hook: Hook, monkeypatch: pytest.MonkeyPatch
) -> None:
    # BootUI's switchSensor only refuses when the agent is not armed: a sensor bootui.agent.sensors does not ask for
    # switches on all the same (toggle: configured false, enabled true, overridden true)
    monkeypatch.setenv("SHARPIT_PANELS_JAVA_AGENT_READ_ONLY", "false")
    app, handle = _app(tmp_path, agent_sensors=("processes",))
    with _client(app) as client:
        hook.fire("os.remove", "a.txt", None)
        assert _rows(handle, "files") == 0  # configured off: nothing recorded yet
        switched = client.post(f"{SWITCH}/files", json={"enabled": True})
        hook.fire("os.remove", "a.txt", None)
    assert switched.status_code == 200
    assert _rows(handle, "files") == 1
    assert len(hook.hooks) == 1
    handle.uninstall_capture()


def test_the_switch_is_not_armed_when_no_sensor_is_configured(tmp_path: Path, hook: Hook) -> None:
    app, handle = _app(tmp_path)
    with _client(app) as client:
        refused = client.post(f"{SWITCH}/files", json={"enabled": True})
    assert refused.status_code == 409
    assert "not armed" in refused.json()["error"]
    assert hook.hooks == []  # the switch never installs anything
    handle.uninstall_capture()


def test_a_switch_returns_the_report_a_read_returns_with_the_sensors_toggle(
    tmp_path: Path, hook: Hook, monkeypatch: pytest.MonkeyPatch
) -> None:
    # BootUI's switchSensor returns report(): the same DTO the GET answers, now with the switched toggle
    monkeypatch.setenv("SHARPIT_PANELS_JAVA_AGENT_READ_ONLY", "false")
    app, handle = _app(tmp_path, agent_sensors=("files",))
    with _client(app) as client:
        before = client.get(f"{API}/java-agent").json()["toggles"]
        switched = client.post(f"{SWITCH}/files", json={"enabled": False}).json()
        after = client.get(f"{API}/java-agent").json()
    handle.uninstall_capture()
    assert [(t["id"], t["configured"], t["enabled"], t["overridden"]) for t in before] == [("files", True, True, False)]
    assert [(t["id"], t["configured"], t["enabled"], t["overridden"]) for t in switched["toggles"]] == [
        ("files", True, False, True)
    ]
    assert after == switched


def test_a_copy_records_one_row_per_side_not_the_files_copyfile_opens(tmp_path: Path, hook: Hook) -> None:
    # BootUI hooks the copy once (copy from, copy to); the opens shutil makes inside it are the copy's own
    app, handle = _app(tmp_path, agent_sensors=("files",))
    source, target = tmp_path / "a.txt", tmp_path / "b.txt"
    source.write_text("x", encoding="utf-8")
    with _client(app):
        hook.fire("shutil.copyfile", str(source), str(target))
        hook.fire("open", str(source), "rb", 0)  # shutil's own inner opens, as the real hook would deliver them
        hook.fire("open", str(target), "wb", 0)
    kinds = [row["kind"] for row in handle.context.capture.journal.records("files")]  # pyright: ignore[reportOptionalMemberAccess]
    assert kinds == ["copy from", "copy to"]
    handle.uninstall_capture()


def test_a_read_only_panel_refuses_the_switch_and_nothing_changes(
    tmp_path: Path, hook: Hook, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHARPIT_PANELS_JAVA_AGENT_READ_ONLY", "true")
    app, handle = _app(tmp_path, agent_sensors=("files",))
    with _client(app) as client:
        resp = client.post(f"{SWITCH}/files", json={"enabled": False})
        hook.fire("os.remove", "a.txt", None)
    assert resp.status_code == 403
    assert resp.json() == {
        "error": PANEL_ACCESS_DENIED,
        "panel": "java-agent",
        "reason": read_only_reason("java-agent", False),
    }
    assert _rows(handle, "files") == 1  # still on
    handle.uninstall_capture()


def _call(handle: SharpitHandle, tool: str) -> None:
    handler = next(t for t in TOOLS if t.name == tool).handler
    handler(CallContext(handle.context, {}), {"id": "files"})


def test_the_mcp_disable_tool_switches_the_sensor_off(tmp_path: Path, hook: Hook) -> None:
    _, handle = _app(tmp_path, agent_sensors=("files",))
    hook.fire("os.remove", "a.txt", None)  # on at the start: one row before the switch
    _call(handle, "disable_agent_sensor")
    hook.fire("os.remove", "a.txt", None)
    assert _rows(handle, "files") == 1
    handle.uninstall_capture()


def test_the_mcp_enable_tool_switches_a_disabled_sensor_back_on(tmp_path: Path, hook: Hook) -> None:
    _, handle = _app(tmp_path, agent_sensors=("files",))
    hook.fire("os.remove", "a.txt", None)
    _call(handle, "disable_agent_sensor")
    hook.fire("os.remove", "a.txt", None)
    assert _rows(handle, "files") == 1  # off: the second event left no row
    _call(handle, "enable_agent_sensor")
    hook.fire("os.remove", "a.txt", None)
    assert _rows(handle, "files") == 2
    handle.uninstall_capture()


def test_a_read_never_switches_a_sensor_on(tmp_path: Path, hook: Hook, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHARPIT_PANELS_JAVA_AGENT_READ_ONLY", "false")
    app, handle = _app(tmp_path, agent_sensors=("files",))
    with _client(app) as client:
        client.post(f"{SWITCH}/files", json={"enabled": False})
        for path in ("/java-agent", "/side-effects", "/side-effects/sensor?sensor=files"):
            assert client.get(API + path).status_code == 200
        hook.fire("os.remove", "a.txt", None)
    assert _rows(handle, "files") == 0
    assert len(hook.hooks) == 1
    handle.uninstall_capture()


def test_the_wiring_does_not_touch_the_real_hook(hook: Hook) -> None:
    assert audit.hub._add_hook is hook  # pyright: ignore[reportPrivateUsage]
    assert sys.addaudithook is not hook
