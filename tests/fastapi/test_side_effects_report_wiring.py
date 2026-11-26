"""The Side Effects report as an installed console wires it: holder line, security-sinks coverage, start time."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.fastapi.adapter import SharpitHandle

SINKS = ("processes", "files", "security-sinks")
HOLDER = "Request-value matching: "


def _app(tmp_path: Path, **options: Any) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()
    handle = install(
        app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(tmp_path / "state"), **options
    )
    return app, handle


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def _report(handle: SharpitHandle) -> dict[str, Any]:
    return handle.context.capture.side_effects.report()


def _holder_line(handle: SharpitHandle) -> str | None:
    return next((line for line in _report(handle)["limitations"] if line.startswith(HOLDER)), None)


def test_the_holder_line_is_emitted_with_zero_counts_whenever_the_setting_is_on(
    tmp_path: Path, recorded_audit_hook: list[Any]
) -> None:
    _app_, handle = _app(tmp_path, agent_sensors=SINKS, agent_security_sinks_request_values=True)
    assert _holder_line(handle) == "Request-value matching: 0 requests held values, 0 sink checks ran."


def test_the_holder_line_reads_the_real_counters_of_the_request_value_holder(
    tmp_path: Path, recorded_audit_hook: list[Any]
) -> None:
    app, handle = _app(tmp_path, agent_sensors=SINKS, agent_security_sinks_request_values=True)

    @app.get("/read/{name}")
    def read_path(name: str) -> str:
        for hook in recorded_audit_hook:
            hook("open", (f"reports/{name}.csv", "r", 0))
        return name

    with _client(app) as client:
        assert client.get("/read/quarterly").status_code == 200
        line = _holder_line(handle)
    assert line is not None
    assert line.startswith("Request-value matching: 1 requests held values, ")
    assert " 0 sink checks ran" not in line


def test_no_holder_line_while_the_setting_is_off(tmp_path: Path, recorded_audit_hook: list[Any]) -> None:
    _app_, handle = _app(tmp_path, agent_sensors=("processes", "files"))
    assert _holder_line(handle) is None
