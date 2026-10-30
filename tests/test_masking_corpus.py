"""Masking corpus (spec §7.7, §12): one sentinel planted in every way a secret reaches sharpit, then every route,
MCP tool and CLI tool is called, error paths and ``q`` probes included. The sentinel and the JWT must appear in no
response body, header, captured log record or stream.

Plants: ``API_TOKEN`` and ``DB_PASSWORD`` (sensitive names), userinfo in ``DATABASE_URL`` (harmless name), a JWT in
``FOO_VALUE`` (harmless name), the getenv default of ``JWT_SECRET``, a pydantic ``SecretStr`` field (the sample's
``Settings.api_token``) and a session middleware ``secret_key`` kwarg.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from examples.fastapi_sample.app import SignedSessionMiddleware, create_app
from fastapi.testclient import TestClient

from conftest import get_paths
from engine.vulns.vulnfakes import FakeOpener
from fastapi import FastAPI
from sharpit.engine.collectors.vulns.dismissals import DismissalStore
from sharpit.engine.collectors.vulns.epss import EpssClient
from sharpit.engine.collectors.vulns.inventory import Package
from sharpit.engine.collectors.vulns.osv import OsvClient
from sharpit.engine.collectors.vulns.service import OPERATION, VulnerabilityService
from sharpit.engine.masking import MASK
from sharpit.engine.mcp import PROMPTS
from sharpit.engine.singleflight import WaitTimeout
from sharpit.engine.tools import COMMANDS, TOOLS

SENTINEL = "S3NT1NEL9f3c"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz"
PROBES = ("S3NT1NEL", "9f3c")  # fragments: an echoed probe is not a leak, a matched secret would be
AUTH_TOKEN = "corpus-auth-token"  # distinct from the sentinel: it legitimately appears in Set-Cookie
LOCAL = ("127.0.0.1", 50000)
REMOTE = ("10.0.0.5", 50000)
API = "/sharpit/api"
RULE = quote("V-1::pypi:widget", safe="")


def _opener() -> FakeOpener:
    def reply(request: Any) -> tuple[int, str]:
        if request.full_url.endswith("/v1/querybatch"):
            return 200, '{"results": [{"vulns": [{"id": "V-1"}]}]}'
        if request.full_url.endswith("/v1/vulns/V-1"):
            return 200, '{"id": "V-1", "affected": [{"package": {"ecosystem": "PyPI", "name": "widget"}}]}'
        return 200, '{"data": []}'

    return FakeOpener(reply)


@pytest.fixture
def corpus_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],  # requested so install()'s own output is captured and checked by the test
) -> tuple[FastAPI, Any]:
    caplog.set_level(logging.DEBUG)  # before create_app(): anything install() logs is checked too
    for name, value in {
        "API_TOKEN": SENTINEL,
        "DB_PASSWORD": SENTINEL,
        "GREETING": SENTINEL,  # Settings.greeting: a SecretStr under a harmless name
        "DATABASE_URL": f"postgres://u:{SENTINEL}@h/db",
        "FOO_VALUE": JWT,
    }.items():
        monkeypatch.setenv(name, value)
    package = tmp_path / "pkgs" / "corpus_app"  # the getenv scan reads packages, never single modules
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(f'import os\n\nJWT_SECRET = os.getenv("JWT_SECRET", "{SENTINEL}")\n')
    monkeypatch.syspath_prepend(str(tmp_path / "pkgs"))
    state = tmp_path / "state"
    app = create_app(
        state_dir=str(state),
        config_scan="corpus_app,examples",  # first finding per key wins: the corpus default for JWT_SECRET
        allow_non_localhost=True,
        authentication_token=AUTH_TOKEN,
    )
    app.add_middleware(SignedSessionMiddleware, secret_key=SENTINEL)
    ctx = app.state.sharpit.context
    opener = _opener()
    service = VulnerabilityService(
        ctx.settings,
        OsvClient("http://osv.test", 2.0, opener),
        EpssClient("http://epss.test", 2.0, opener),
        lambda: [Package("widget", "1.0.0", None)],
        DismissalStore(state),
        ctx.single_flight,
    )
    assert ctx.lazy("vulnerabilities", lambda: service) is service
    return app, ctx


class Recorder:
    """Every response sharpit sends, as text: status line, headers and body."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.seen: list[str] = []
        self.statuses: set[int] = set()

    def __call__(self, method: str, path: str, **kw: Any) -> Any:
        resp = self.client.request(method, path, **kw)
        self.statuses.add(resp.status_code)
        self.seen.append(f"{method} {path} -> {resp.status_code}\n{resp.headers!r}\n{resp.text}")
        return resp

    def mcp(self, method: str, params: dict[str, Any] | None = None) -> Any:
        body = {"jsonrpc": "2.0", "id": 1, "method": method, **({"params": params} if params is not None else {})}
        return self("POST", f"{API}/mcp", json=body).json()


def _sweep(call: Recorder, ctx: Any) -> None:
    # every GET route from the sub-app's own route table, with q probes
    for probe in ("", *PROBES):
        query = f"?q={probe}&limit=500" if probe else ""
        for path in get_paths():
            call("GET", path + query)
        for path in (f"{API}/config", f"{API}/beans"):  # masking happens before filtering: no hit on a secret
            page = call("GET", f"{path}?q={probe}").json()["page"] if probe else None
            assert page is None or page["matched"] == 0, (path, probe, page)
    call("POST", f"{API}/auth/session")
    call("POST", f"{API}/vulnerabilities/scan")
    call("GET", f"{API}/vulnerabilities")
    call("POST", f"{API}/dismissed-rules/{RULE}")
    call("DELETE", f"{API}/dismissed-rules/{RULE}")
    call("POST", f"{API}/loggers/corpus.logger", json={"level": "NOPE"})  # 400: an invalid level changes nothing

    # error paths: 400, 401, 403, 404, 405, 409, 413
    call("GET", f"{API}/config?offset=-1")
    call("GET", f"{API}/beans?limit=x")
    call("POST", f"{API}/dismissed-rules/{quote('V-1::widget', safe='')}")
    call("POST", f"{API}/mcp-server/toggle", content=b"{not json", headers={"content-type": "application/json"})
    call.client.cookies.clear()
    remote = Recorder(TestClient(call.client.app, base_url="http://localhost", client=REMOTE))
    remote("GET", f"{API}/config")
    remote("POST", f"{API}/auth/session", headers={"Authorization": "Bearer wrong"})
    call.seen += remote.seen
    call.statuses |= remote.statuses
    call("GET", f"{API}/config", headers={"Origin": "http://evil.example"})
    call("GET", f"{API}/config", headers={"Host": "evil.example"})
    call("GET", f"{API}/nope")
    call("GET", f"{API}/mcp")
    call("POST", f"{API}/mcp", content=b"x" * (ctx.settings.mcp_max_payload_bytes + 1))
    release = threading.Event()
    with pytest.raises(WaitTimeout):  # hold the single-flight lock so the next scans are busy
        ctx.single_flight.run(OPERATION, lambda: release.wait(5), wait_timeout=0)
    try:
        call("POST", f"{API}/vulnerabilities/scan")
        call("POST", f"{API}/cli/tools/vulnerabilities_scan", json={})
    finally:
        release.set()

    # MCP: enabled in memory, every method, every tool, every prompt, error paths
    call("POST", f"{API}/mcp-server/toggle", json={"enabled": True})
    call.mcp("initialize", {"protocolVersion": "2025-06-18"})
    call.mcp("tools/list")
    call.mcp("prompts/list")
    for prompt in PROMPTS:
        call.mcp("prompts/get", {"name": prompt.name})
    for tool in TOOLS:
        call.mcp("tools/call", {"name": tool.name, "arguments": {}})
        if "query" in tool.input_schema["properties"]:
            for probe in PROBES:
                call.mcp("tools/call", {"name": tool.name, "arguments": {"query": probe, "limit": 500}})
        call.mcp("tools/call", {"name": tool.name, "arguments": {"bogus": True}})
    call.mcp("tools/call", {"name": "nope"})
    call.mcp("prompts/get", {"name": "nope"})
    call.mcp("nope/method")
    call("POST", f"{API}/mcp", content=b"{not json", headers={"content-type": "application/json"})

    # CLI: every tool, probes and error paths
    for name in COMMANDS:
        tool = next(t for t in TOOLS if t.name == name)
        call("POST", f"{API}/cli/tools/{name}", json={})
        if "query" in tool.input_schema["properties"]:
            for probe in PROBES:
                call("POST", f"{API}/cli/tools/{name}", json={"query": probe})
        call("POST", f"{API}/cli/tools/{name}", json={"bogus": True})
    call("POST", f"{API}/cli/tools/nope", json={})
    call("POST", f"{API}/cli/tools/get_config", content=b"[1]", headers={"content-type": "application/json"})


def test_sentinel_never_leaks(
    corpus_app: tuple[FastAPI, Any], caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
):
    app, ctx = corpus_app
    with TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False) as client:
        call = Recorder(client)
        _sweep(call, ctx)

        # the plants really reached sharpit (else the sweep proves nothing); recorded like every other response
        config = {p["name"]: p for p in call("GET", f"{API}/config?limit=500").json()["properties"]}
        for name in ("API_TOKEN", "DB_PASSWORD", "FOO_VALUE", "GREETING"):
            assert config[name]["masked"] is True, config[name]
        # GREETING's name and value look harmless: only the SecretStr type masks the value and the "hello" default
        assert config["GREETING"]["defaultValue"] == MASK
        assert config["DATABASE_URL"]["value"] != f"postgres://u:{SENTINEL}@h/db"
        suggestions = call("GET", f"{API}/config?q=jwt_secret").json()
        defaults = [p["defaultValue"] for p in suggestions["properties"] + suggestions["propertySuggestions"]]
        assert defaults and all(d == MASK for d in defaults), defaults
        beans = call("GET", f"{API}/beans?q=SignedSession&limit=500").json()["beans"]
        assert [b["type"] for b in beans] == ["examples.fastapi_sample.app:SignedSessionMiddleware"]
    assert {400, 401, 403, 404, 405, 409, 413} <= call.statuses, sorted(call.statuses)
    assert any("GET /sharpit/assets/app.js -> 404" in seen for seen in call.seen)  # the route-table sweep

    captured = capsys.readouterr()
    outputs = {
        "responses": "\n".join(call.seen),
        "log records": caplog.text + "\n".join(str(r.__dict__) for r in caplog.records),
        "stdout/stderr": captured.out + captured.err,
    }
    for where, text in outputs.items():
        assert SENTINEL not in text, where
        assert JWT not in text, where


def test_generated_token_printed_once_to_stderr_not_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
):
    caplog.set_level(logging.DEBUG)
    app = create_app(allow_non_localhost=True, state_dir=str(tmp_path))  # remote access, no token: one is generated
    token = app.state.sharpit.context.token
    assert token
    with TestClient(app, base_url="http://localhost", client=REMOTE) as client:
        assert client.post(f"{API}/auth/session", headers={"Authorization": f"Bearer {token}"}).status_code == 204
        assert client.get(f"{API}/overview").status_code == 200  # through the session cookie
        assert client.get(f"{API}/config?limit=500").status_code == 200
    captured = capsys.readouterr()
    assert captured.err.count(token) == 1
    assert token not in captured.out
    assert token not in caplog.text
    assert all(token not in str(r.__dict__) for r in caplog.records)


def test_configured_token_never_printed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
):
    caplog.set_level(logging.DEBUG)
    app = create_app(allow_non_localhost=True, authentication_token=AUTH_TOKEN, state_dir=str(tmp_path))
    bearer = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    with TestClient(app, base_url="http://localhost", client=REMOTE) as client:
        bodies = [client.get(f"{API}/{path}", headers=bearer).text for path in ("overview", "config?limit=500", "cli")]
    captured = capsys.readouterr()
    assert "sharpit active at /sharpit/" in captured.err  # the banner is printed, just without the token
    for text in (captured.out, captured.err, caplog.text, *bodies):
        assert AUTH_TOKEN not in text
