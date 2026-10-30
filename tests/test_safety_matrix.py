"""Spec §7.6 guard matrix, the inactive 404 matrix, forwarded-header spoofing and no-side-effects on every GET.

Each row is (path x peer x headers -> status) over a real ``install()``; the rulings in force are rows too: any
forwarded header voids the loopback and container-gateway grants, duplicate Host/Origin/Sec-Fetch-Site get 403, a
cross-site top-level navigation to the shell gets 403.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from pathlib import Path
from typing import Any

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
from sharpit.engine.panels import PANELS
from sharpit.engine.tools import TOOLS

LOCAL = ("127.0.0.1", 50000)
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
    install(app, enabled="ON", show_banner=False, **(REMOTE_ACCESS if remote_access else {}))
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


GATED = [(p.id, p.api_prefix + ("/flat" if p.id == "mappings" else "")) for p in PANELS if p.api_prefix]


@pytest.mark.parametrize(("panel", "sub_path"), GATED, ids=[g[0] for g in GATED])
def test_disabled_panel_denies_its_endpoints(panel: str, sub_path: str):
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, panels={panel: {"enabled": False}})
    resp = _client(app).get(f"/sharpit/api{sub_path}")
    env = panel.upper().replace("-", "_")
    assert (resp.status_code, resp.json()) == (
        403,
        _panel_denied(panel, f"Panel is disabled via SHARPIT_PANELS_{env}_ENABLED=false"),
    )


def test_ungated_paths_ignore_panel_flags():
    # §7.6: panels, overview and cli carry no panel gate (the overview and cli panels have no API prefix)
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, panels={p.id: {"enabled": False} for p in PANELS})
    client = _client(app)
    for path in ("/sharpit/api/panels", "/sharpit/api/overview", "/sharpit/api/cli", "/sharpit/"):
        assert client.get(path).status_code == 200, path


WRITES = [
    ("loggers", "/sharpit/api/loggers/sharpit.matrix", {"level": "DEBUG"}),
    ("vulnerabilities", "/sharpit/api/vulnerabilities/scan", None),
    ("mcp-server", "/sharpit/api/mcp-server/toggle", {"enabled": True}),
]


@pytest.mark.parametrize("scope", ["global", "panel"])
@pytest.mark.parametrize(("panel", "path", "body"), WRITES, ids=[w[0] for w in WRITES])
def test_read_only_denies_panel_actions(no_side_effects: SideEffectGuard, panel: str, path: str, body: Any, scope: str):
    no_side_effects.unblock_network()  # the Windows Proactor loop TestClient starts connects a self-pipe socketpair
    options: dict[str, Any] = {"read_only": True} if scope == "global" else {"panels": {panel: {"read_only": True}}}
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir), **options)
    with _client(app) as client:
        no_side_effects.block_network()
        resp = client.post(path, json=body)
    env = panel.upper().replace("-", "_")
    reason = (
        "sharpit is read-only via SHARPIT_READ_ONLY=true"
        if scope == "global"
        else f"Panel is read-only via SHARPIT_PANELS_{env}_READ_ONLY=true"
    )
    assert (resp.status_code, resp.json()) == (403, _panel_denied(panel, reason))


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
    for peer in (LOCAL, REMOTE):
        client = _client(app, peer)
        for path in INACTIVE_PATHS:
            for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
                for headers in ({}, {"Authorization": f"Bearer {TOKEN}"}, {"X-Forwarded-For": "127.0.0.1"}):
                    resp = client.request(method, path, headers=headers)
                    assert resp.status_code == 404, (peer, method, path, headers)
                    assert "content-security-policy" not in resp.headers
                    if method != "HEAD":
                        assert resp.json() == expected == {"detail": "Not Found"}


# --- no side effects on any GET, read from the sub-app's own route table -------------------------------------------


GET_PATHS = get_paths()


def test_get_route_table_is_complete():
    assert set(GET_PATHS) == {"/sharpit"} | {r[2] for r in ROWS if r[1] == "GET"}


@pytest.mark.parametrize("path", GET_PATHS)
def test_every_get_no_side_effects(no_side_effects: SideEffectGuard, path: str):
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(app) as client:
        no_side_effects.block_network()
        for query in ("", "?q=sharpit&offset=0&limit=5"):
            resp = client.get(path + query)
            assert resp.status_code in (200, 307, 404), resp.text
    assert no_side_effects.violations == []


MCP_TOOLS = [t.name for t in TOOLS if not t.action]


@pytest.mark.parametrize("tool", MCP_TOOLS)
def test_every_mcp_tool_no_side_effects(no_side_effects: SideEffectGuard, tool: str):
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()
    with _client(app) as client:
        no_side_effects.block_network()
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": {}}}
        result = client.post("/sharpit/api/mcp", json=call).json()["result"]
    assert result["isError"] is False, result
    assert no_side_effects.violations == []
