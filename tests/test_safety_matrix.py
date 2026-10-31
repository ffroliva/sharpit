"""Spec §7.6 guard matrix, the inactive 404 matrix, forwarded-header spoofing and no-side-effects on every GET.

Each row is (path x peer x headers -> status) over a real ``install()``; the rulings in force are rows too: any
forwarded header voids the loopback and container-gateway grants, duplicate Host/Origin/Sec-Fetch-Site get 403, a
cross-site top-level navigation to the shell gets 403.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from conftest import SideEffectGuard, get_paths
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.guard import (
    AUTHENTICATION_REQUIRED_MESSAGE,
    MESSAGE_CROSS_SITE,
    MESSAGE_DISALLOWED_HOST,
    MESSAGE_FORWARDED_SOURCE,
    MESSAGE_NON_LOOPBACK_SOURCE,
    PANEL_ACCESS_DENIED,
    SESSION_COOKIE,
)
from sharpit.engine.mcp import DISABLED_MESSAGE
from sharpit.engine.panels import PANELS, disabled_reason, read_only_reason
from sharpit.engine.tools import TOOLS
from sharpit.fastapi.adapter import SharpitHandle, SharpitMount

LOCAL = ("127.0.0.1", 50000)
GROUP_ID = "0123456789abcdef"  # conftest._PATH_PARAMS["id"]
REMOTE = ("10.0.0.5", 50000)
GATEWAY = "172.17.0.1"
TOKEN = "matrix-token"
EVIL = "http://evil.example"
PING = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
REMOTE_ACCESS = {"allow_non_localhost": True, "authentication_token": TOKEN}
FORWARDED = ({"Forwarded": "for=127.0.0.1"}, {"X-Forwarded-For": "127.0.0.1"}, {"X-Real-IP": "127.0.0.1"})

# (row, method, path, status once the guard lets it through, token required) -- spec §7.6, one entry per path class
ROWS = [
    ("bare", "GET", "/sharpit", 307, False),
    ("shell", "GET", "/sharpit/", 200, False),
    ("asset", "GET", "/sharpit/assets/app.js", 404, False),  # no built assets yet: the sub-app's own JSON 404
    ("session", "POST", "/sharpit/api/auth/session", 204, True),
    ("panels", "GET", "/sharpit/api/panels", 200, True),
    ("overview", "GET", "/sharpit/api/overview", 200, True),
    ("cli", "GET", "/sharpit/api/cli", 200, True),
    ("config", "GET", "/sharpit/api/config", 200, True),
    ("mappings", "GET", "/sharpit/api/mappings/flat", 200, True),
    ("loggers", "GET", "/sharpit/api/loggers", 200, True),
    ("beans", "GET", "/sharpit/api/beans", 200, True),
    ("http-exchanges", "GET", "/sharpit/api/http-exchanges", 200, True),
    ("exceptions", "GET", "/sharpit/api/exceptions", 200, True),
    ("exceptions-stream", "GET", "/sharpit/api/exceptions/stream", 200, True),
    ("exceptions-detail", "GET", f"/sharpit/api/exceptions/{GROUP_ID}", 404, True),  # no such group
    ("sql-trace", "GET", "/sharpit/api/sql-trace", 200, True),
    ("sql-trace-stream", "GET", "/sharpit/api/sql-trace/stream", 200, True),
    ("activity", "GET", "/sharpit/api/activity", 200, True),
    ("activity-stream", "GET", "/sharpit/api/activity/stream", 200, True),
    ("activity-request", "GET", f"/sharpit/api/activity/request/{GROUP_ID}", 200, True),  # available: false
    ("alembic", "GET", "/sharpit/api/alembic/migrations", 200, True),
    ("health", "GET", "/sharpit/api/health", 200, True),
    ("log-tail", "GET", "/sharpit/api/log-tail/recent", 200, True),
    ("log-tail-stream", "GET", "/sharpit/api/log-tail/stream", 200, True),
    ("vulnerabilities", "GET", "/sharpit/api/vulnerabilities", 200, True),
    ("mcp-server", "GET", "/sharpit/api/mcp-server", 200, True),
    ("dismissed-rules", "GET", "/sharpit/api/dismissed-rules", 200, True),
    ("mcp", "POST", "/sharpit/api/mcp", 200, True),
]

# (variant, peer, headers, remote access on?, outcome): "ok" = the row's status, "token" = 401 if the row needs a
# token else ok, or an int status / guard message
NAVIGATE = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
VARIANTS: list[tuple[str, tuple[str, int], dict[str, str], bool, str]] = [
    ("local", LOCAL, {}, False, "ok"),
    ("local-same-origin", LOCAL, {"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"}, False, "ok"),
    ("local-foreign-host", LOCAL, {"Host": "evil.example"}, False, MESSAGE_DISALLOWED_HOST),
    ("local-malformed-host", LOCAL, {"Host": "local host"}, False, MESSAGE_DISALLOWED_HOST),
    ("local-cross-origin", LOCAL, {"Origin": EVIL}, False, MESSAGE_CROSS_SITE),
    ("local-null-origin", LOCAL, {"Origin": "null"}, False, MESSAGE_CROSS_SITE),
    ("local-cross-site-navigation", LOCAL, NAVIGATE, False, MESSAGE_CROSS_SITE),
    *((f"local-{next(iter(h)).lower()}", LOCAL, h, False, MESSAGE_FORWARDED_SOURCE) for h in FORWARDED),
    ("remote-forwarded", REMOTE, {"X-Forwarded-For": "127.0.0.1"}, False, MESSAGE_FORWARDED_SOURCE),
    ("remote", REMOTE, {}, False, MESSAGE_NON_LOOPBACK_SOURCE),
    ("remote-bearer-without-remote-access", REMOTE, {"Authorization": f"Bearer {TOKEN}"}, False, "403-source"),
    ("remote-no-token", REMOTE, {}, True, "token"),
    ("remote-wrong-bearer", REMOTE, {"Authorization": "Bearer nope"}, True, "token"),
    ("remote-bearer", REMOTE, {"Authorization": f"Bearer {TOKEN}"}, True, "ok"),
    ("remote-cookie", REMOTE, {"Cookie": f"{SESSION_COOKIE}={TOKEN}"}, True, "ok"),
    ("remote-bearer-cross-origin", REMOTE, {"Authorization": f"Bearer {TOKEN}", "Origin": EVIL}, True, "403-cross"),
    ("local-xff-remote-access", LOCAL, {"X-Forwarded-For": "127.0.0.1"}, True, "token"),
    # Task P1 (stricter than BootUI, spec §14): on API paths a present Origin must be the request's own origin,
    # scheme + host + port; the shell and assets keep the host-only check (ruling 58)
    ("local-other-port-origin", LOCAL, {"Origin": "http://localhost:3000", "Sec-Fetch-Site": "same-site"}, False,
     "403-cross-api"),
    ("local-other-scheme-origin", LOCAL, {"Origin": "https://localhost"}, False, "403-cross-api"),
    ("local-same-origin-default-port", LOCAL, {"Origin": "http://localhost:80"}, False, "ok"),
    ("remote-bearer-other-port-origin", REMOTE, {"Authorization": f"Bearer {TOKEN}", "Origin": "http://localhost:3000"},
     True, "403-cross-api"),
]  # fmt: skip
_OUTCOME_ALIASES = {"403-source": MESSAGE_NON_LOOPBACK_SOURCE, "403-cross": MESSAGE_CROSS_SITE}


@functools.cache
def _app(remote_access: bool) -> FastAPI:
    app = FastAPI(title="matrix")
    # streams end after 0.05 s instead of 3 s, so the stream row costs no more than any other
    install(app, enabled="ON", show_banner=False, stream_max_seconds=0.05, **(REMOTE_ACCESS if remote_access else {}))
    return app


def _client(app: Any, peer: tuple[str, int] = LOCAL) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=peer, follow_redirects=False)


def _send(client: TestClient, method: str, path: str, headers: dict[str, str]) -> Any:
    return client.request(method, path, headers=headers, json=PING if method == "POST" else None)


@pytest.mark.parametrize(
    ("variant", "peer", "headers", "remote_access", "outcome"), VARIANTS, ids=[v[0] for v in VARIANTS]
)
@pytest.mark.parametrize(("row", "method", "path", "ok", "needs_token"), ROWS, ids=[r[0] for r in ROWS])
def test_guard_matrix(
    row: str,
    method: str,
    path: str,
    ok: int,
    needs_token: bool,
    variant: str,
    peer: tuple[str, int],
    headers: dict[str, str],
    remote_access: bool,
    outcome: str,
):
    resp = _send(_client(_app(remote_access), peer), method, path, headers)
    outcome = _OUTCOME_ALIASES.get(outcome, outcome)
    if outcome == "403-cross-api":  # every API row needs a token, so needs_token is "is an API path"
        outcome = MESSAGE_CROSS_SITE if needs_token else "ok"
    if outcome == "token":
        outcome = "401" if needs_token else "ok"
    if outcome == "ok":
        assert resp.status_code == ok, resp.text
    elif outcome == "401":
        assert (resp.status_code, resp.json()) == (401, {"error": AUTHENTICATION_REQUIRED_MESSAGE})
        assert resp.headers["www-authenticate"] == 'Bearer realm="sharpit"'
    else:
        assert (resp.status_code, resp.json()) == (403, {"error": outcome})
    assert resp.headers["x-content-type-options"] == "nosniff"  # security headers on denials and successes alike


def test_mcp_switch_is_the_only_gate_on_mcp():
    # §7.6: {api}/mcp has no panel gate; MCP off is an in-band JSON-RPC error, not a guard 403
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, read_only=True, panels={p.id: {"enabled": False} for p in PANELS})
    resp = _client(app).post("/sharpit/api/mcp", json=PING)
    assert resp.status_code == 200
    assert resp.json() == {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": DISABLED_MESSAGE}}
    on = FastAPI()
    install(on, enabled="ON", show_banner=False, read_only=True, mcp_enabled="ON")
    assert _client(on).post("/sharpit/api/mcp", json=PING).json() == {"jsonrpc": "2.0", "id": 1, "result": {}}


def _panel_denied(panel: str, reason: str) -> dict[str, str]:
    return {"error": PANEL_ACCESS_DENIED, "panel": panel, "reason": reason}


def _panel_routes(prefix: str) -> list[tuple[str, str]]:
    """The prefix itself (GET) plus every ROWS and WRITES route under it, stream routes included."""
    base = f"/sharpit/api{prefix}"
    known = [(r[1], r[2]) for r in ROWS] + [(w[1], w[2]) for w in WRITES]
    return sorted({("GET", base), *((m, p) for m, p in known if p == base or p.startswith(base + "/"))})


GATED = [(p.id, p.api_prefix) for p in PANELS if p.api_prefix]


@pytest.mark.parametrize(("panel", "prefix"), GATED, ids=[g[0] for g in GATED])
def test_disabled_panel_denies_its_endpoints(panel: str, prefix: str):
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, panels={panel: {"enabled": False}})
    client = _client(app)
    for method, path in _panel_routes(prefix):
        resp = client.request(method, path, json={} if method == "POST" else None)
        assert (resp.status_code, resp.json()) == (403, _panel_denied(panel, disabled_reason(panel))), (method, path)


# 0.2.0 MCP tools and their panels; each task adds the tools it builds
PANEL_TOOLS = [
    ("get_http_exchanges", "http-exchanges", {}),
    ("get_log_tail", "log-tail", {}),
    ("get_exceptions", "exceptions", {}),
    ("get_exception_detail", "exceptions", {"id": GROUP_ID}),
    ("get_sql_traces", "sql-trace", {}),
    ("get_live_activity", "activity", {}),
    ("get_alembic_migrations", "alembic", {}),
    ("get_health", "health", {}),
]


@pytest.mark.parametrize(("tool", "panel", "arguments"), PANEL_TOOLS, ids=[t[0] for t in PANEL_TOOLS])
def test_disabled_panel_mcp_tool_refused(tool: str, panel: str, arguments: dict[str, Any]):
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, mcp_enabled="ON", panels={panel: {"enabled": False}})
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    result = _client(app).post("/sharpit/api/mcp", json=call).json()["result"]
    assert result["isError"] is True and result["content"][0]["text"] == disabled_reason(panel)


# spec §7.4: a disabled source panel x every activity route and get_live_activity (what the source must not show)
ACTIVITY_SOURCES = [
    ("http-exchanges", None, None),
    ("exceptions", "exceptions", "EXCEPTION"),
    ("sql-trace", "sql", "SQL"),
]


@pytest.mark.parametrize(("panel", "source", "row_type"), ACTIVITY_SOURCES, ids=[s[0] for s in ACTIVITY_SOURCES])
def test_disabled_source_activity_routes(panel: str, source: str | None, row_type: str | None):
    app = FastAPI()
    app.get("/host", response_model=None)(lambda: {"secret": "x"})
    install(app, enabled="ON", show_banner=False, mcp_enabled="ON", stream_max_seconds=0.05,
            panels={panel: {"enabled": False}})  # fmt: skip
    client = _client(app)
    client.get("/host", headers={"x-api-key": "k"})
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_live_activity", "arguments": {}}}
    reports = [client.get("/sharpit/api/activity").json(), client.post("/sharpit/api/mcp", json=call).json()["result"]]
    reports[1] = reports[1]["structuredContent"]
    for report in reports:
        assert source not in report["sources"] and row_type not in report["typeCounts"]
    rid = next(e["id"] for e in reports[0]["entries"] if e["type"] == "REQUEST")
    profile = client.get(f"/sharpit/api/activity/request/{rid}").json()
    assert profile["available"] is True
    if panel == "http-exchanges":
        assert (profile["request"]["requestHeaders"], profile["request"]["responseHeaders"]) == ([], [])
    if panel == "exceptions":
        assert profile["exceptions"] == []
    if panel == "sql-trace":
        assert (profile["sql"], profile["sqlGroups"]) == ([], [])
    assert client.get("/sharpit/api/activity/stream").status_code == 200


def test_ungated_paths_ignore_panel_flags():
    # §7.6: panels, overview and cli carry no panel gate (the overview and cli panels have no API prefix)
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, panels={p.id: {"enabled": False} for p in PANELS})
    client = _client(app)
    for path in ("/sharpit/api/panels", "/sharpit/api/overview", "/sharpit/api/cli", "/sharpit/"):
        assert client.get(path).status_code == 200, path


# (panel, method, path, body): every state-changing panel route (test_write_route_table_is_complete keeps it whole)
WRITES = [
    ("loggers", "POST", "/sharpit/api/loggers/sharpit.matrix", {"level": "DEBUG"}),
    ("vulnerabilities", "POST", "/sharpit/api/vulnerabilities/scan", None),
    ("mcp-server", "POST", "/sharpit/api/mcp-server/toggle", {"enabled": True}),
    ("exceptions", "DELETE", "/sharpit/api/exceptions", None),
    ("exceptions", "POST", f"/sharpit/api/exceptions/{GROUP_ID}/status", {"status": "RESOLVED"}),
    ("sql-trace", "POST", "/sharpit/api/sql-trace/clear", None),
    ("sql-trace", "POST", "/sharpit/api/sql-trace/recording", {"enabled": False}),
    ("alembic", "POST", "/sharpit/api/alembic/refresh", None),
    ("health", "POST", "/sharpit/api/health/check", None),
]
# Not panel actions: the session login, MCP and CLI (own switches); dismissed-rules obeys only the global read-only
# flag (test_dismissed_rules_obey_global_read_only_only), so it has no panel-scope row here.
_NOT_PANEL_WRITES = ("/api/auth/session", "/api/mcp", "/api/cli/", "/api/dismissed-rules/")


@pytest.mark.parametrize("scope", ["global", "panel"])
@pytest.mark.parametrize(("panel", "method", "path", "body"), WRITES, ids=[f"{w[0]}-{w[1]}" for w in WRITES])
def test_read_only_denies_panel_actions(
    no_side_effects: SideEffectGuard, panel: str, method: str, path: str, body: Any, scope: str
):
    no_side_effects.unblock_network()  # the Windows Proactor loop TestClient starts connects a self-pipe socketpair
    options: dict[str, Any] = {"read_only": True} if scope == "global" else {"panels": {panel: {"read_only": True}}}
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir), **options)
    with _client(app) as client:
        no_side_effects.block_network()
        resp = client.request(method, path, json=body)
    env = panel.upper().replace("-", "_")
    reason = (
        "sharpit is read-only via SHARPIT_READ_ONLY=true"
        if scope == "global"
        else f"Panel is read-only via SHARPIT_PANELS_{env}_READ_ONLY=true"
    )
    assert (resp.status_code, resp.json()) == (403, _panel_denied(panel, reason))


def _write_routes() -> set[tuple[str, str]]:
    """(method, path format) of every POST/DELETE sub-app route, read from the sample app's own route table."""
    mount = next(r for r in create_app(show_banner=False).router.routes if isinstance(r, SharpitMount))
    found: set[tuple[str, str]] = set()
    for route in mount.routes:
        path = "/sharpit" + getattr(route, "path_format", "")
        if any(path == "/sharpit" + s or path.startswith("/sharpit" + s.rstrip("/") + "/") for s in _NOT_PANEL_WRITES):
            continue
        found |= {(m, path) for m in {"POST", "DELETE"} & set(getattr(route, "methods", None) or ())}
    return found


def test_write_route_table_is_complete():
    def shape(path: str) -> str:  # a concrete WRITES path back to its route's format
        return path.replace(GROUP_ID, "{id}").replace("sharpit.matrix", "{name}")

    assert _write_routes() == {(w[1], shape(w[2])) for w in WRITES}


def _seed_exceptions(handle: SharpitHandle) -> Callable[[], object]:
    """Record one exception (when the panel has a store) and return a probe of the store's state."""
    store = handle.context.capture.exceptions
    if store is None:
        return lambda: None
    try:
        raise RuntimeError("seeded")
    except RuntimeError as exc:
        store.record(exc, "log", None, "test")
    return lambda: store.report()["totalExceptions"]


def _seed_sql_trace(handle: SharpitHandle) -> Callable[[], object]:
    """Record one statement (when tracing is on) and return a probe of the recorder's state."""
    recorder = handle.context.capture.sql_trace
    if recorder is None:
        return lambda: None
    recorder.record("select 1", duration_ns=1, thread="test", connection_id=None)
    return lambda: (recorder.report([])["totalCaptured"], len(recorder.report([])["entries"]), recorder.recording)


# CLI-only action tools (never on MCP): (tool, panel, seed returning a state probe); Tasks 5 and 10 add theirs
CLI_ACTIONS: list[tuple[str, str, Callable[[SharpitHandle], Callable[[], object]]]] = [
    ("clear_exceptions", "exceptions", _seed_exceptions),
    ("clear_sql_traces", "sql-trace", _seed_sql_trace),
    ("pause_sql_trace_recording", "sql-trace", _seed_sql_trace),
    ("resume_sql_trace_recording", "sql-trace", _seed_sql_trace),
]
GATES: dict[str, Callable[[str], dict[str, Any]]] = {
    "panel-disabled": lambda panel: {"panels": {panel: {"enabled": False}}},
    "panel-read-only": lambda panel: {"panels": {panel: {"read_only": True}}},
    "global-read-only": lambda _panel: {"read_only": True},
}


@pytest.mark.parametrize("gate", list(GATES))
@pytest.mark.parametrize(("tool", "panel", "seed"), CLI_ACTIONS, ids=[a[0] for a in CLI_ACTIONS])
def test_cli_action_tools_gated(
    tool: str, panel: str, seed: Callable[[SharpitHandle], Callable[[], object]], gate: str
):
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, cli_enabled=True, mcp_enabled="ON", **GATES[gate](panel))
    try:
        probe = seed(handle)
        before = probe()
        client = _client(app)
        resp = client.post(f"/sharpit/api/cli/tools/{tool}", json={})
        if gate == "panel-disabled":
            reason = disabled_reason(panel)
        else:
            reason = read_only_reason(panel, gate == "global-read-only")
        assert (resp.status_code, resp.json()) == (403, {"error": reason})
        assert probe() == before
        listed = client.post("/sharpit/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
        assert tool not in [t["name"] for t in listed["result"]["tools"]]
    finally:
        handle.uninstall_capture()


def test_dismissed_rules_obey_global_read_only_only(tmp_path: Path):
    rule = "/sharpit/api/dismissed-rules/V-1%3A%3Apypi%3Awidget"
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, read_only=True, state_dir=str(tmp_path))
    client = _client(app)
    assert client.get("/sharpit/api/dismissed-rules").status_code == 200
    for method in ("POST", "DELETE"):
        resp = client.request(method, rule)
        reason = "sharpit is read-only via SHARPIT_READ_ONLY=true"
        assert (resp.status_code, resp.json()) == (403, _panel_denied("dismissed-rules", reason))
    assert list(tmp_path.iterdir()) == []
    panel_only = FastAPI()
    install(
        panel_only,
        enabled="ON",
        show_banner=False,
        state_dir=str(tmp_path),
        panels={"vulnerabilities": {"read_only": True}},
    )
    assert _client(panel_only).post(rule).status_code == 200  # a panel flag does not cover dismissed-rules


# --- Origin from another local port: browser "simple" requests (text/plain, no preflight) must not mutate -------


MUTATIONS = [
    ("/sharpit/api/mcp-server/toggle", b""),
    ("/sharpit/api/loggers/matrix.origin.probe", b'{"level": "DEBUG"}'),
    ("/sharpit/api/dismissed-rules/V-1%3A%3Apypi%3Awidget", b""),
]


@pytest.mark.parametrize(("path", "body"), MUTATIONS, ids=["mcp-server-toggle", "loggers", "dismissed-rules"])
def test_other_local_port_cannot_mutate(tmp_path: Path, path: str, body: bytes):
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, state_dir=str(tmp_path))
    client = _client(app)
    plain = {"Content-Type": "text/plain"}
    other_port = {**plain, "Origin": "http://localhost:3000", "Sec-Fetch-Site": "same-site"}
    resp = client.post(path, content=body, headers=other_port)
    assert (resp.status_code, resp.json()) == (403, {"error": MESSAGE_CROSS_SITE})
    assert list(tmp_path.iterdir()) == []  # no dismissal written
    assert logging.getLogger("matrix.origin.probe").level == logging.NOTSET
    assert client.get("/sharpit/api/mcp-server").json()["enabled"] is False
    # the page's own origin, and a client that sends no Origin (curl, the CLI, MCP clients), still work
    assert client.post(path, content=body, headers={**plain, "Origin": "http://localhost"}).status_code == 200
    assert client.post(path, content=body, headers=plain).status_code == 200
    logging.getLogger("matrix.origin.probe").setLevel(logging.NOTSET)


# --- container gateway: trusted until a forwarded header appears ------------------------------------------------


@pytest.mark.parametrize(("headers", "status"), [({}, 200), *((h, 403) for h in FORWARDED)])
def test_container_gateway_grant_voided_by_forwarded_headers(headers: dict[str, str], status: int):
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, trust_container_gateway="ON")
    assert handle.context.lazy("gateway", lambda: GATEWAY) == GATEWAY
    resp = _client(app, (GATEWAY, 50000)).get("/sharpit/api/overview", headers=headers)
    assert resp.status_code == status
    if status == 403:
        assert resp.json() == {"error": MESSAGE_FORWARDED_SOURCE}


# --- spoofed X-Forwarded-For behind uvicorn's proxy-headers middleware (FORWARDED_ALLOW_IPS=*) -------------------


@pytest.mark.parametrize("peer", [LOCAL, REMOTE], ids=["local-peer", "remote-peer"])
@pytest.mark.parametrize("path", ["/sharpit/", "/sharpit/api/overview", "/sharpit/api/auth/session"])
def test_spoofed_xff_is_never_loopback(peer: tuple[str, int], path: str):
    method = "POST" if path.endswith("session") else "GET"
    spoof = {"X-Forwarded-For": "127.0.0.1"}
    closed = ProxyHeadersMiddleware(_app(False), trusted_hosts="*")
    resp = _client(closed, peer).request(method, path, headers=spoof)
    assert (resp.status_code, resp.json()) == (403, {"error": MESSAGE_FORWARDED_SOURCE})
    remote = ProxyHeadersMiddleware(_app(True), trusted_hosts="*")
    resp = _client(remote, peer).request(method, path, headers=spoof)
    assert resp.status_code == (200 if path == "/sharpit/" else 401)  # untrusted: the API needs the token


@pytest.mark.parametrize(("proxy", "spoofed"), [("127.0.0.1", "127.0.0.1"), ("10.0.0.0/8", "10.0.0.7")])
@pytest.mark.parametrize("peer", [LOCAL, REMOTE], ids=["local-peer", "remote-peer"])
def test_spoofed_xff_into_a_trusted_proxy_range_needs_the_token(proxy: str, spoofed: str, peer: tuple[str, int]):
    # --forwarded-allow-ips='*' rewrites the peer to whatever X-Forwarded-For says, here an address in the range
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, trusted_proxies=[proxy], authentication_token=TOKEN)
    client = _client(ProxyHeadersMiddleware(app, trusted_hosts="*"), peer)
    spoof = {"X-Forwarded-For": spoofed}
    assert client.get("/sharpit/api/overview", headers=spoof).status_code == 401
    authed = {**spoof, "Authorization": f"Bearer {TOKEN}"}
    assert client.get("/sharpit/api/overview", headers=authed).status_code == 200


# --- duplicate headers (raw ASGI: httpx would merge them) -----------------------------------------------------------


def _raw_status(app: Any, headers: list[tuple[bytes, bytes]], path: str) -> int:
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
        "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"", "headers": headers,
        "client": LOCAL, "server": ("localhost", 80),
    }  # fmt: skip
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent[0]["status"]


DUPLICATES = [
    [(b"host", b"localhost"), (b"host", b"localhost")],
    [(b"host", b"localhost"), (b"origin", b"http://localhost"), (b"origin", b"http://localhost")],
    [(b"host", b"localhost"), (b"sec-fetch-site", b"same-origin"), (b"sec-fetch-site", b"same-origin")],
]


@pytest.mark.parametrize("headers", DUPLICATES, ids=["host", "origin", "sec-fetch-site"])
@pytest.mark.parametrize("path", ["/sharpit", "/sharpit/", "/sharpit/api/overview"])
def test_duplicate_guard_headers_are_403(headers: list[tuple[bytes, bytes]], path: str):
    assert _raw_status(_app(False), headers[:1], path) in (200, 307)
    assert _raw_status(_app(False), headers, path) == 403


# --- inactive: every path, method and header combination is the host's 404 ----------------------------------------


INACTIVE_PATHS = sorted(
    {r[2] for r in ROWS} | {"/sharpit/api", "/sharpit/api/nope", "/sharpit/api/cli/tools/get_overview"}
)


@pytest.mark.parametrize(
    ("options", "profiles"),
    [({"enabled": "OFF"}, None), ({}, None), ({}, "prod"), ({"enabled": "OFF"}, "dev")],
    ids=["off", "default", "prod-profile", "off-beats-dev-profile"],
)
def test_inactive_is_404_everywhere(options: dict[str, str], profiles: str | None, monkeypatch: pytest.MonkeyPatch):
    if profiles:
        monkeypatch.setenv("SHARPIT_PROFILES", profiles)
    app = FastAPI()
    install(app, **options)
    expected = _client(app).get("/not-sharpit").json()

    # 756 requests: one event loop for all of them (TestClient starts a thread per request, 13x slower on Windows)
    async def sweep() -> None:
        for peer in (LOCAL, REMOTE):
            transport = httpx.ASGITransport(app=app, client=peer)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                for path in INACTIVE_PATHS:
                    for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
                        for headers in ({}, {"Authorization": f"Bearer {TOKEN}"}, {"X-Forwarded-For": "127.0.0.1"}):
                            resp = await client.request(method, path, headers=headers)
                            assert resp.status_code == 404, (peer, method, path, headers)
                            assert "content-security-policy" not in resp.headers
                            if method != "HEAD":
                                assert resp.json() == expected == {"detail": "Not Found"}

    asyncio.run(sweep())


# --- no side effects on any GET, read from the sub-app's own route table -------------------------------------------


GET_PATHS = get_paths()


def test_get_route_table_is_complete():
    assert set(GET_PATHS) == {"/sharpit"} | {r[2] for r in ROWS if r[1] == "GET"}


ALEMBIC_INI = Path(__file__).resolve().parent / "fixtures" / "alembic" / "linear" / "alembic.ini"
# spec §7.6 / §7.8: with a registered engine, a health check and an Alembic config, a GET or an MCP tool still opens
# no database connection and runs no check (the plain app has none of them, so it cannot catch that)
SWEEPS = ["plain", pytest.param("sqla", marks=pytest.mark.needs_sqlalchemy)]


def _sweep_app(variant: str, state_dir: str, **options: Any) -> tuple[FastAPI, Callable[[], list[str]]]:
    """The sample app, and a probe of what ran: health checks called and database connections checked out."""
    if variant == "plain":
        return create_app(show_banner=False, state_dir=state_dir, **options), list
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine("sqlite://")
    ran: list[str] = []
    sa.event.listen(engine, "checkout", lambda *_a: ran.append("checkout"))
    app = create_app(
        show_banner=False, state_dir=state_dir, engines=[engine], alembic_config=str(ALEMBIC_INI),
        health_checks={"spy": lambda: ran.append("check") or True}, **options,
    )  # fmt: skip
    return app, lambda: ran


@pytest.mark.parametrize("variant", SWEEPS)
@pytest.mark.parametrize("path", GET_PATHS)
def test_every_get_no_side_effects(no_side_effects: SideEffectGuard, path: str, variant: str):
    state_dir = str(no_side_effects.state_dir)
    app, ran = _sweep_app(variant, state_dir, mcp_enabled="ON", stream_max_seconds=0.05)
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(app) as client:
        no_side_effects.block_network()
        for query in ("", "?q=sharpit&offset=0&limit=5"):
            resp = client.get(path + query)
            assert resp.status_code in (200, 307, 404), resp.text
    assert no_side_effects.violations == []
    assert ran() == []


MCP_TOOLS = [t.name for t in TOOLS if not t.action]


def _tool_arguments(tool: str, handle: SharpitHandle) -> dict[str, Any]:
    """A tool's required arguments: get_exception_detail gets the id of an exception recorded here."""
    if tool != "get_exception_detail":
        return {}
    _seed_exceptions(handle)
    store = handle.context.capture.exceptions
    assert store is not None
    return {"id": store.report()["groups"][0]["id"]}


@pytest.mark.parametrize("variant", SWEEPS)
@pytest.mark.parametrize("tool", MCP_TOOLS)
def test_every_mcp_tool_no_side_effects(no_side_effects: SideEffectGuard, tool: str, variant: str):
    app, ran = _sweep_app(variant, str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()
    with _client(app) as client:
        no_side_effects.block_network()
        arguments = _tool_arguments(tool, app.state.sharpit)
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        result = client.post("/sharpit/api/mcp", json=call).json()["result"]
    assert result["isError"] is False, result
    assert no_side_effects.violations == []
    assert ran() == []
