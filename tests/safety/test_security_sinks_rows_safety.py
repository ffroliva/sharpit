"""The Side Effects read surfaces preserve the request-value masking boundary."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI, Request
from sharpit import install
from sharpit.engine.collectors.sideeffects.agent_report import no_match_line
from sharpit.engine.guard import MESSAGE_CROSS_SITE, MESSAGE_FORWARDED_SOURCE
from sharpit.engine.sensors import audit
from sharpit.fastapi.adapter import SharpitHandle

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api"
CANARY = "cnry7Q4x"
SHORT = "abcd"
SECRET_NAME = "AKIAIOSFODNN7EXAMPLE"
SENSORS = (
    "network",
    "files",
    "processes",
    "environment",
    "thread-activity",
    "thread-locals",
    "resources",
    "blocking",
    "security-sinks",
)
EXPOSURES = ("MASKED", "METADATA_ONLY", "FULL")


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


def _app(tmp_path: Path, hook: Hook, exposure: str, *, state_dir: str | None = None) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        state_dir=state_dir or str(tmp_path / "state"),
        expose_values=exposure,
        mcp_enabled="ON",
        cli_enabled=True,
        agent_sensors=("processes", "files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )

    @app.get("/work")
    def work(request: Request) -> str:
        value = request.query_params.get(SECRET_NAME)
        if value is None:
            value = request.query_params["file"]
        hook.fire("open", f"reports/{value}.csv", "r", 0)
        hook.fire("subprocess.Popen", None, [value, f"--input={value}"], None, None)
        return "ok"

    return app, handle


def _rpc(client: TestClient, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return client.post(f"{API}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).json()


def _outputs(client: TestClient) -> list[Any]:
    outputs: list[Any] = [client.get(f"{API}/side-effects").json()]
    for sensor in SENSORS:
        outputs.extend(
            client.get(f"{API}/side-effects/sensor?sensor={sensor}&offset={offset}&limit=500").json()
            for offset in (0, 500)
        )
    outputs.extend(
        _rpc(client, "tools/call", {"name": "get_side_effects", "arguments": args})
        for args in ({}, *({"query": sensor} for sensor in SENSORS), {"query": "file"})
    )
    outputs.extend(
        client.post(f"{API}/cli/tools/get_side_effects", json=args).json()
        for args in ({}, *({"query": sensor} for sensor in SENSORS), {"query": "file"})
    )
    return outputs


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _strip_report_echo(report: dict[str, Any]) -> dict[str, Any]:
    assert report["query"] == CANARY
    assert no_match_line(CANARY) in report["limitations"]
    cleaned = dict(report)
    cleaned["query"] = "<caller query>"
    cleaned["limitations"] = [
        "<caller query limitation>" if line == no_match_line(CANARY) else line for line in report["limitations"]
    ]
    return cleaned


def _without_query_echo(answer: dict[str, Any], *, mcp: bool = False) -> dict[str, Any]:
    if not mcp:
        return _strip_report_echo(answer)
    cleaned = dict(answer)
    result = dict(cleaned["result"])
    result["structuredContent"] = _strip_report_echo(result["structuredContent"])
    content = []
    for block in result.get("content", []):
        item = dict(block)
        text = item.get("text")
        if isinstance(text, str):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(decoded, dict) and "query" in decoded and "limitations" in decoded:
                    item["text"] = _json(_strip_report_echo(decoded))
        content.append(item)
    result["content"] = content
    cleaned["result"] = result
    return cleaned


@pytest.mark.parametrize("exposure", EXPOSURES)
def test_a_seeded_value_and_the_hashes_reach_no_side_effects_output_at_any_exposure(
    tmp_path: Path, hook: Hook, exposure: str
) -> None:
    app, handle = _app(tmp_path, hook, exposure)
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        assert client.get(f"/work?{SECRET_NAME}={CANARY}&file={CANARY}").status_code == 200
        assert client.get(f"/work?{SECRET_NAME}={CANARY}x&file={CANARY}x").status_code == 200
        assert client.get(f"/work?{SECRET_NAME}={SHORT}&file={SHORT}").status_code == 200
        assert client.get(f"/work?{SECRET_NAME}={SHORT}x&file={SHORT}x").status_code == 200
        lane = handle.context.capture.sensors
        assert lane is not None
        hashes = {
            str(row[key])
            for row in lane.rows._rings["security-sinks"]  # pyright: ignore[reportPrivateUsage]
            for key in ("rawHash", "redactedHash")
            if row.get(key) is not None
        }
        assert hashes
        outputs = _outputs(client)
        asked = _rpc(client, "tools/call", {"name": "get_side_effects", "arguments": {"query": CANARY}})
        asked_cli = client.post(f"{API}/cli/tools/get_side_effects", json={"query": CANARY}).json()
    assert asked["result"]["structuredContent"]["matched"] == 0
    assert asked_cli["matched"] == 0
    # get_side_effects echoes its own query and no-match line; strip only those exact echoes.
    asked = _without_query_echo(asked, mcp=True)
    asked_cli = _without_query_echo(asked_cli)
    serialized = [_json(output) for output in (*outputs, asked, asked_cli)]
    assert all(CANARY not in output for output in serialized)
    assert all(SHORT not in output for output in serialized)
    assert all(SECRET_NAME not in output for output in serialized)
    assert all("rawHash" not in output and "redactedHash" not in output for output in serialized)
    assert all(value not in output for output in serialized for value in hashes)


def test_no_seeded_value_reaches_any_report_or_row_even_a_four_character_one(tmp_path: Path, hook: Hook) -> None:
    # adapted from: SecuritySinksServiceTests.noSeededValueReachesAnyReportOrRowEvenAFourCharacterOne
    app, handle = _app(tmp_path, hook, "FULL")
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        client.get(f"/work?{SECRET_NAME}={SHORT}&file={SHORT}")
        client.get(f"/work?{SECRET_NAME}={SHORT}x&file={SHORT}x")
        outputs = _outputs(client)
    handle.uninstall_capture()
    assert all(SHORT not in _json(output) for output in outputs)


def test_side_effects_reads_have_no_side_effects(no_side_effects: SideEffectGuard, hook: Hook) -> None:
    app, handle = _app(no_side_effects.state_dir.parent, hook, "MASKED", state_dir=str(no_side_effects.state_dir))
    no_side_effects.rebaseline()
    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        client.get(f"/work?{SECRET_NAME}={CANARY}&file={CANARY}")
        client.get(f"/work?{SECRET_NAME}={CANARY}x&file={CANARY}x")
        no_side_effects.block_network()
        _outputs(client)
    handle.uninstall_capture()
    assert no_side_effects.violations == []


@pytest.mark.parametrize(
    ("headers", "reason"),
    (
        ({"Sec-Fetch-Site": "cross-site"}, MESSAGE_CROSS_SITE),
        ({"Origin": "https://outside.example"}, MESSAGE_CROSS_SITE),
        ({"X-Forwarded-For": "203.0.113.9"}, MESSAGE_FORWARDED_SOURCE),
    ),
    ids=("cross-site", "foreign-origin", "forwarded"),
)
def test_a_cross_site_or_forwarded_read_of_side_effects_rows_is_refused(
    tmp_path: Path, hook: Hook, headers: dict[str, str], reason: str
) -> None:
    app, handle = _app(tmp_path, hook, "MASKED")
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        client.get(f"/work?{SECRET_NAME}={CANARY}&file={CANARY}")
        client.get(f"/work?{SECRET_NAME}={CANARY}x&file={CANARY}x")
        report = client.get(f"{API}/side-effects", headers=headers)
        rows = client.get(f"{API}/side-effects/sensor?sensor=files", headers=headers)
    handle.uninstall_capture()
    assert report.status_code == 403
    assert report.json() == {"error": reason}
    assert rows.status_code == 403
    assert rows.json() == {"error": reason}
    assert CANARY not in report.text + rows.text
