"""``GET {api}/cli`` and ``POST {api}/cli/tools/{tool}`` (port of BootUI ``BootUiCliController``, ``CliService`` and
``CliOutcomes``; contract §11).

Ported: ``CliOutcomesTests`` mapping, one row per contract §11 outcome in ``test_cli_outcomes``. The vulnerabilities
service is seeded through ``ctx.lazy`` with a fake, so no row touches the network.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import __version__, install
from sharpit.engine.collectors.vulns.service import OPERATION
from sharpit.engine.singleflight import ActionBusy

LOCAL = ("127.0.0.1", 50000)
CLI_DISABLED = "sharpit CLI endpoint is disabled. Set SHARPIT_CLI_ENABLED=true to allow command-line access."


class FakeService:
    """``scan`` blocks until ``release`` (``busy=True``: raises ``ActionBusy``); ``report`` returns at once."""

    def __init__(self, busy: bool = False) -> None:
        self.busy = busy
        self.fail = False
        self.release = threading.Event()
        self.entered = threading.Event()
        self.workers: list[threading.Thread] = []

    def report(self) -> dict[str, Any]:
        return {"scan": {"status": "NOT_SCANNED"}}

    def scan(self) -> dict[str, Any]:
        if self.busy:
            raise ActionBusy(OPERATION, OPERATION)
        if self.fail:
            raise RuntimeError("secret detail")
        self.workers.append(threading.current_thread())
        self.entered.set()
        self.release.wait(5)
        return {"scan": {"status": "SCANNED"}}

    def join(self) -> None:
        self.release.set()
        for worker in self.workers:
            worker.join(5)
        assert not any(w.is_alive() for w in self.workers)


def _client(service: FakeService | None = None, **options: Any) -> TestClient:
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **options})
    fake = service or FakeService()
    assert handle.context.lazy("vulnerabilities", lambda: fake) is fake
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _post(client: TestClient, tool: str, body: Any = None) -> tuple[int, Any]:
    resp = client.post(f"/sharpit/api/cli/tools/{tool}", json=body)
    return resp.status_code, resp.json()


# (case, settings, tool, body, fake-service busy?, expected status, expected error or None for a 200 payload check)
CASES = [
    ("ok", {}, "get_overview", None, False, 200, None),
    ("ok-scan", {}, "vulnerabilities_scan", {}, False, 200, None),
    ("disabled", {"cli_enabled": False}, "get_overview", None, False, 503, CLI_DISABLED),
    ("unknown-tool", {}, "nope", None, False, 404, "Unknown tool: nope"),
    ("invalid-args", {}, "get_config", {"limit": 0}, False, 400, "Argument 'limit' must be at least 1"),
    ("unexpected-arg", {}, "get_config", {"q": "x"}, False, 400, "Unexpected tool argument: q"),
    ("non-object", {}, "get_config", [1], False, 400, "Tool arguments must be an object"),
    (
        "panel-disabled",
        {"panels": {"loggers": {"enabled": False}}},
        "get_loggers",
        None,
        False,
        403,
        "Panel is disabled via SHARPIT_PANELS_LOGGERS_ENABLED=false",
    ),
    (
        "panel-read-only",
        {"panels": {"vulnerabilities": {"read_only": True}}},
        "vulnerabilities_scan",
        None,
        False,
        403,
        "Panel is read-only via SHARPIT_PANELS_VULNERABILITIES_READ_ONLY=true",
    ),
    ("busy", {}, "vulnerabilities_scan", None, True, 409, str(ActionBusy(OPERATION, OPERATION))),
    ("capacity", {"cli_max_concurrent_calls": 1}, "get_overview", None, False, 429,
     "MCP server is at capacity; try again shortly."),
    ("timeout", {"cli_execution_timeout": "50ms"}, "vulnerabilities_scan", None, False, 504,
     "MCP tool execution timed out"),
    ("other", {}, "vulnerabilities_scan", None, False, 500, "Internal error"),
]  # fmt: skip


@pytest.mark.parametrize(("case", "options", "tool", "body", "busy", "status", "message"), CASES)
def test_cli_outcomes(
    case: str, options: dict[str, Any], tool: str, body: Any, busy: bool, status: int, message: str | None
):
    # ported: CliOutcomesTests (one row per contract §11 outcome)
    service = FakeService(busy=busy)
    if case == "ok-scan":
        service.release.set()
    service.fail = case == "other"
    client = _client(service, **options)
    holder: threading.Thread | None = None
    if case == "capacity":  # a scan holds the only CLI slot while the second call arrives
        holder = threading.Thread(target=lambda: client.post("/sharpit/api/cli/tools/vulnerabilities_scan"))
        holder.start()
        assert service.entered.wait(5)
    try:
        got_status, got = _post(client, tool, body)
    finally:
        service.join()
        if holder is not None:
            holder.join(5)
            assert not holder.is_alive()
    assert got_status == status, got
    if message is None:
        assert "error" not in got
    else:
        assert got == {"error": message}


def test_cli_status_shape_matches_contract():
    # ported: CliService.status / CliServerStatus (contract §11)
    body = _client().get("/sharpit/api/cli").json()
    assert list(body) == [
        "enabled", "serverName", "serverVersion", "endpoint", "maxResults", "callCount", "totalLatencyMillis",
        "capacityRefusals", "timeouts", "toolCount", "tools",
    ]  # fmt: skip
    assert (body["enabled"], body["serverName"], body["serverVersion"]) == (True, "sharpit", __version__)
    assert (body["endpoint"], body["maxResults"], body["toolCount"]) == ("/sharpit/api/cli", 200, 17)
    by_name = {t["name"]: t for t in body["tools"]}
    assert {n: t["command"] for n, t in by_name.items()} == {
        "get_overview": "overview",
        "get_config": "config",
        "get_mappings": "mappings",
        "get_loggers": "loggers",
        "get_beans": "beans",
        "get_http_exchanges": "http exchanges",
        "get_log_tail": "logs tail",
        "get_exceptions": "exceptions list",
        "get_exception_detail": "exceptions show",
        "clear_exceptions": "exceptions clear",
        "get_sql_traces": "sql traces",
        "clear_sql_traces": "sql clear",
        "pause_sql_trace_recording": "sql pause",
        "resume_sql_trace_recording": "sql resume",
        "get_live_activity": "activity",
        "get_vulnerabilities_report": "vulnerabilities report",
        "vulnerabilities_scan": "vulnerabilities scan",
    }
    assert list(by_name["get_config"]) == [
        "name", "command", "description", "panel", "action", "schema", "arguments", "panelEnabled", "panelReadOnly",
    ]  # fmt: skip
    assert (by_name["get_config"]["schema"], by_name["get_config"]["arguments"]) == ("QUERY_LIMIT", ["query", "limit"])
    assert (by_name["vulnerabilities_scan"]["schema"], by_name["vulnerabilities_scan"]["arguments"]) == ("NONE", [])
    assert (by_name["get_http_exchanges"]["schema"], by_name["get_http_exchanges"]["arguments"]) == ("LIMIT", ["limit"])
    assert by_name["vulnerabilities_scan"]["action"] is True


def test_cli_status_while_disabled_lists_nothing():
    # ported: CliService.status when disabled (no invocable tools)
    body = _client(cli_enabled=False).get("/sharpit/api/cli").json()
    assert (body["enabled"], body["toolCount"], body["tools"]) == (False, 0, [])


def test_cli_works_with_mcp_disabled():
    # new: brief ruling (CLI independent of MCP state, separate counters)
    client = _client(mcp_enabled="OFF")
    status, body = _post(client, "get_loggers", {"limit": 1})
    assert status == 200 and len(body["loggers"]) == 1
    assert client.get("/sharpit/api/cli").json()["callCount"] == 1
    assert client.get("/sharpit/api/mcp-server").json()["callCount"] == 0  # separate counters


def test_cli_scan_gated_by_read_only():
    # ported: CliService action gating (read-only refuses vulnerabilities scan)
    service = FakeService()
    status, body = _post(_client(service, read_only=True), "vulnerabilities_scan")
    assert (status, body) == (403, {"error": "sharpit is read-only via SHARPIT_READ_ONLY=true"})
    assert not service.entered.is_set()


def test_cli_body_is_bounded():
    # new: review ruling (bounded read; the CLI has no cap of its own, so the MCP payload cap applies)
    status, body = _post(_client(mcp_max_payload_bytes=16), "get_config", {"query": "x" * 100})
    assert (status, body) == (413, {"error": "Request payload exceeds limit"})
