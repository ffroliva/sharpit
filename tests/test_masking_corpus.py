"""Masking corpus (spec §7.7, §12): one sentinel planted in every way a secret reaches sharpit, then every route,
MCP tool and CLI tool is called, error paths and ``q`` probes included. The sentinel and the JWT must appear in no
response body, header, captured log record or stream.

Plants: ``API_TOKEN``, ``DB_PASSWORD``, ``MAIL_PASS`` and ``PASS`` (sensitive names), userinfo in ``DATABASE_URL``
(harmless name), a JWT in ``FOO_VALUE`` (harmless name), a password-less DSN and connection-string credential segments
(harmless names), the getenv default of ``JWT_SECRET``, a pydantic ``SecretStr`` field (the sample's
``Settings.api_token``) and a session middleware ``secret_key`` kwarg.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from examples.fastapi_sample.app import SignedSessionMiddleware, create_app
from fastapi.testclient import TestClient
from starlette.requests import Request

from conftest import get_paths
from engine.vulns.vulnfakes import FakeOpener
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.collectors.vulns.epss import EpssClient
from sharpit.engine.collectors.vulns.inventory import Package
from sharpit.engine.collectors.vulns.osv import OsvClient
from sharpit.engine.collectors.vulns.service import OPERATION, VulnerabilityService
from sharpit.engine.masking import MASK
from sharpit.engine.mcp import PROMPTS
from sharpit.engine.tools import COMMANDS, TOOLS

SENTINEL = "S3NT1NEL9f3c"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz"
PROBES = ("S3NT1NEL", "9f3c")  # fragments: an echoed probe is not a leak, a matched secret would be
AUTH_TOKEN = "corpus-auth-token"  # distinct from the sentinel: it legitimately appears in Set-Cookie
LOCAL = ("127.0.0.1", 50000)
REMOTE = ("10.0.0.5", 50000)
API = "/sharpit/api"
RULE = quote("V-1::pypi:widget", safe="")
WIDENED = (
    "MAIL_PASS",
    "PASS",
    "PGPASS",
    "PGPASSFILE",
    "MONITORING_DSN",
    "SQL_CONN",
    "ODBC_CONN",
    "STORAGE_CONN",
    "BUS_CONN",
)


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
        # Task P1 widening: a `_PASS` name, a bare PASS, a password-less DSN and connection-string segments
        "MAIL_PASS": SENTINEL,
        "PASS": SENTINEL,
        "PGPASS": SENTINEL,  # review M1: libpq names
        "PGPASSFILE": SENTINEL,
        "MONITORING_DSN": f"https://{SENTINEL}@o1.ingest.sentry.io/1",
        "SQL_CONN": f"Server=db;Database=app;User Id=sa;Password={SENTINEL};",
        "ODBC_CONN": f"Driver=x;Server=db;Uid=sa;Pwd={SENTINEL}",
        "STORAGE_CONN": f"DefaultEndpointsProtocol=https;AccountName=a;AccountKey={SENTINEL};",
        "BUS_CONN": f"Endpoint=sb://ns.example/;SharedAccessKeyName=Root;SharedAccessKey={SENTINEL}",
    }.items():
        monkeypatch.setenv(name, value)
    package = tmp_path / "pkgs" / "corpus_app"  # the getenv scan reads packages, never single modules
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(f'import os\n\nJWT_SECRET = os.getenv("JWT_SECRET", "{SENTINEL}")\n')
    monkeypatch.syspath_prepend(str(tmp_path / "pkgs"))
    state = tmp_path / "state"
    versions = tmp_path / "alembic" / "versions"  # alembic_docstring: a revision's description is masked
    versions.mkdir(parents=True)
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = %(here)s/alembic\n", "utf-8")
    (versions / "r1.py").write_text(f'"""rotate password={SENTINEL}"""\n\nrevision = "r1"\n', "utf-8")

    def failing_check() -> bool:
        raise ConnectionError(f"cannot reach postgres://u:{SENTINEL}@h/db")

    app = create_app(
        state_dir=str(state),
        alembic_config=str(tmp_path / "alembic.ini"),
        health_checks={  # health details: nested keys, a DSN value and a raised message are masked
            "nested": lambda: {"status": "UP", "password": SENTINEL, "pool": {"dsn": f"postgres://u:{SENTINEL}@h/db"}},
            "failing": failing_check,
        },
        config_scan="corpus_app,examples",  # first finding per key wins: the corpus default for JWT_SECRET
        allow_non_localhost=True,
        authentication_token=AUTH_TOKEN,
        stream_max_seconds=0.05,  # the sweep GETs every stream route: each ends after 0.05 s, not 3 s
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
        for path in (
            f"{API}/config",
            f"{API}/beans",
            f"{API}/http-exchanges",
        ):  # masking happens before filtering: no hit on a secret
            page = call("GET", f"{path}?q={probe}").json()["page"] if probe else None
            assert page is None or page["matched"] == 0, (path, probe, page)
    call("POST", f"{API}/auth/session")
    call("POST", f"{API}/health/check")
    call("GET", f"{API}/health")
    call("POST", f"{API}/alembic/refresh")
    call("POST", f"{API}/vulnerabilities/scan")
    call("GET", f"{API}/vulnerabilities")
    scan_id = call("POST", f"{API}/rest-api/scan").json()["violationDetails"]["scanId"]
    call("GET", f"{API}/rest-api")
    for result in call("GET", f"{API}/rest-api").json()["results"]:
        call("GET", f"{API}/rest-api/rules/{result['id']}/violations?scanId={scan_id}&limit=1000")
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
    entered, release = threading.Event(), threading.Event()
    holder = threading.Thread(  # hold the single-flight lock so the next scans are busy
        target=ctx.single_flight.run, args=(OPERATION, lambda: entered.set() or release.wait(5))
    )
    holder.start()
    try:
        assert entered.wait(5)
        call("POST", f"{API}/vulnerabilities/scan")
        call("POST", f"{API}/cli/tools/vulnerabilities_scan", json={})
    finally:
        release.set()
        holder.join(5)

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


def _plant_host_requests(client: TestClient) -> None:
    # F1: the sentinel and the JWT in a host request's path, query and Authorization header (spec §7.1).
    # The test client's own httpx logger would echo the URL: that is the harness, not sharpit, so it is quiet here.
    httpx_logger = logging.getLogger("httpx")
    level = httpx_logger.level
    httpx_logger.setLevel(logging.WARNING)
    try:
        _send_plant(client)
    finally:
        httpx_logger.setLevel(level)


def _send_plant(client: TestClient) -> None:
    client.get(
        f"/reset/{JWT}?api_key={SENTINEL}&page=1&{JWT}",  # a bare part: masked by value
        headers={"Authorization": f"Bearer {SENTINEL}", "X-Note": JWT},  # harmless name: masked by value
    )


def test_http_exchanges_metadata_only_hides_values(tmp_path: Path):
    app = create_app(show_banner=False, state_dir=str(tmp_path), expose_values="METADATA_ONLY")
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        _plant_host_requests(client)
        report = client.get(f"{API}/http-exchanges").json()
    row = next(e for e in report["exchanges"] if e["path"].startswith("/reset/"))
    assert (row["query"], row["uri"]) == (None, f"/reset/{MASK}")
    assert all(h["values"] == [] for h in row["requestHeaders"] + row["responseHeaders"])
    assert SENTINEL not in str(report) and JWT not in str(report)


def test_probe_masking_corpus(tmp_path: Path):
    app = FastAPI()

    @app.get("/probe-json")
    def probe_json():
        from starlette.responses import JSONResponse

        return JSONResponse({"password": SENTINEL, "ok": True}, headers={"Set-Cookie": f"session={SENTINEL}"})

    @app.get("/probe-text")
    def probe_text():
        from starlette.responses import PlainTextResponse

        return PlainTextResponse(f"token={JWT}", headers={"Location": f"/redirect?token={SENTINEL}"})

    @app.get("/probe-tag")
    def probe_tag(request: Request):
        return {"tag": request.headers.get("x-sharpit-probe")}

    handle = install(app, enabled="ON", show_banner=False, state_dir=str(tmp_path), authentication_token=AUTH_TOKEN)
    try:
        with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
            results = [
                client.post(f"{API}/http-probe", json={"method": "GET", "path": path})
                for path in ("/probe-json", "/probe-text")
            ]
            forged_tag = client.post(
                f"{API}/http-probe",
                json={"method": "GET", "path": "/probe-tag", "headers": {"X-Sharpit-Probe": "forged"}},
            )
            exchange_rows = client.get(f"{API}/http-exchanges").json()["exchanges"]
    finally:
        handle.uninstall_capture()
    assert results[0].json()["body"] == f'{{"password":"{MASK}","ok":true}}'
    assert "Set-Cookie" not in results[0].text and "session=" not in results[0].text
    assert results[1].json()["body"] == f"token={MASK}"
    assert results[1].json()["headers"]["location"] == f"/redirect?token={MASK}"
    assert forged_tag.json()["body"] == '{"tag":"1"}'
    assert SENTINEL not in str(results) and JWT not in str(results)
    assert all(SENTINEL not in str(row) and JWT not in str(row) for row in exchange_rows)


def test_sentinel_never_leaks(
    corpus_app: tuple[FastAPI, Any], caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
):
    app, ctx = corpus_app
    with TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False) as client:
        call = Recorder(client)
        _plant_host_requests(client)
        _sweep(call, ctx)
        exchanges = call("GET", f"{API}/http-exchanges?limit=500").json()["exchanges"]
        planted = [e for e in exchanges if e["path"].startswith("/reset/")]
        assert (
            planted
            and planted[0]["path"] == f"/reset/{MASK}"
            and planted[0]["query"] == f"api_key={MASK}&page=1&{MASK}"
        )

        # the plants really reached sharpit (else the sweep proves nothing); recorded like every other response
        config = {p["name"]: p for p in call("GET", f"{API}/config?limit=500").json()["properties"]}
        for name in ("API_TOKEN", "DB_PASSWORD", "FOO_VALUE", "GREETING", *WIDENED):
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


def test_own_token_masked_with_mask_secrets_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # the final review's M6: SHARPIT_MASK_SECRETS=false must not show sharpit's own token in Config or get_config
    monkeypatch.setenv("SHARPIT_MASK_SECRETS", "false")
    monkeypatch.setenv("SHARPIT_AUTHENTICATION_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("TOKEN_COPY_FOR_TEST", AUTH_TOKEN)
    app = create_app(allow_non_localhost=True, state_dir=str(tmp_path))
    bearer = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    with TestClient(app, base_url="http://localhost", client=REMOTE) as client:
        config = client.get(f"{API}/config?limit=500", headers=bearer)
        tool = client.post(f"{API}/cli/tools/get_config", json={"query": "token"}, headers=bearer)
    assert config.status_code == tool.status_code == 200
    names = {p["name"] for p in config.json()["properties"]}
    assert {
        "SHARPIT_AUTHENTICATION_TOKEN",
        "TOKEN_COPY_FOR_TEST",
    } <= names  # listed, so the check below is meaningful
    assert "TOKEN_COPY_FOR_TEST" in tool.text
    for text in (config.text, tool.text):
        assert AUTH_TOKEN not in text


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


# F5: log messages the host app logs, masked before they reach the buffer (spec §7.5, §11)
LOG_CORPUS = [
    ("password_pair", "host.app", "login failed password=%s", (SENTINEL,), f"login failed password={MASK}"),
    ("jwt_value", "host.app", "user sent %s", (JWT,), f"user sent {MASK}"),
    ("prefixed_jwt_value", "host.app", "user sent %s", (f"refresh-{JWT}",), f"user sent refresh-{MASK}"),
    ("dsn_userinfo", "host.app", "connect %s failed", (f"postgres://u:{SENTINEL}@h/db",),
     "connect postgres://******@h/db failed"),
    ("dict_repr", "host.app", "kwargs=%r", ({"api_key": SENTINEL},), f"kwargs={{'api_key': '{MASK}'}}"),
    (
        "access_log_jwt_path",
        "uvicorn.access",
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", f"/reset/{JWT}", "1.1", 200),
        f'127.0.0.1:5000 - "GET /reset/{MASK} HTTP/1.1" 200',
    ),
    (
        "statement_error_parameters",
        "host.app",
        "%s",
        (f"(sqlite3.IntegrityError) failed\n[SQL: INSERT INTO u VALUES (?)]\n[parameters: ('{SENTINEL}',)]",),
        f"(sqlite3.IntegrityError) failed\n[SQL: INSERT INTO u VALUES (?)]\n[parameters: {MASK}]",
    ),
    ("sqlalchemy_echo_parameters", "sqlalchemy.engine.Engine", "[%s] %r", ("generated in 0.0001s", (SENTINEL,)), None),
]  # fmt: skip


@pytest.mark.parametrize(("row", "name", "msg", "args", "expected"), LOG_CORPUS, ids=[r[0] for r in LOG_CORPUS])
def test_log_tail_masks_messages(
    tmp_path: Path, row: str, name: str, msg: str, args: tuple[Any, ...], expected: str | None
):
    app = create_app(show_banner=False, state_dir=str(tmp_path), mcp_enabled="ON", stream_max_seconds=0.05)
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        logging.getLogger(name).warning(msg, *args)
        recent = client.get(f"{API}/log-tail/recent").json()
        stream = client.get(f"{API}/log-tail/stream").text
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_log_tail", "arguments": {}}}
        mcp = client.post(f"{API}/mcp", json=call).text
        cli = client.post(f"{API}/cli/tools/get_log_tail", json={}).text
    lines = [line["message"] for line in recent if line["logger"] == name]
    assert lines == ([] if expected is None else [expected]), row
    for where, text in {"recent": str(recent), "stream": stream, "mcp": mcp, "cli": cli}.items():
        assert SENTINEL not in text and JWT not in text, (row, where)


# F2: exception messages and cause messages the host app raises, masked at capture (spec §7.2, §7.7)
def test_exceptions_mask_messages(tmp_path: Path):
    app = create_app(show_banner=False, state_dir=str(tmp_path), mcp_enabled="ON", stream_max_seconds=0.05)

    @app.get("/corpus-fail")
    def corpus_fail() -> None:  # pyright: ignore[reportUnusedFunction]
        try:
            raise ValueError(f"token {JWT}")
        except ValueError as cause:
            raise RuntimeError(f"login failed password={SENTINEL}") from cause

    app.router.routes.insert(1, app.router.routes.pop())  # ahead of the sample's catch-all /{path:path}
    with TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False) as client:
        assert client.get("/corpus-fail").status_code == 500
        listed = client.get(f"{API}/exceptions").json()
        group = next(g for g in listed["groups"] if g["lastRequestPath"] == "/corpus-fail")
        detail = client.get(f"{API}/exceptions/{group['id']}").json()
        stream = client.get(f"{API}/exceptions/stream").text
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
        mcp = [
            client.post(f"{API}/mcp", json={**call, "params": {"name": n, "arguments": a}}).text
            for n, a in (("get_exceptions", {}), ("get_exception_detail", {"id": group["id"]}))
        ]
        cli = client.post(f"{API}/cli/tools/get_exception_detail", json={"id": group["id"]}).text
    assert group["message"] == f"login failed password={MASK}"
    assert detail["causes"][0]["message"] == f"token {MASK}"
    texts = {"list": str(listed), "detail": str(detail), "stream": stream, "mcp": "".join(mcp), "cli": cli}
    for where, text in texts.items():
        assert SENTINEL not in text and JWT not in text, where


# F3: SQL the host app runs, masked at capture (spec §7.3, §11); SQLAlchemy is imported lazily (needs_sqlalchemy)
def _sql_inline_literal(sa: Any, conn: Any) -> None:
    conn.execute(sa.text(f"select '{SENTINEL}' as token, '{JWT}' as jwt"))


def _sql_bind_values(sa: Any, conn: Any) -> None:
    conn.execute(sa.text("select :password as p, :jwt as j"), {"password": SENTINEL, "jwt": JWT})


def _sql_integrity_error(sa: Any, conn: Any) -> None:
    conn.execute(sa.text("create table creds (id integer primary key, secret text)"))
    for _ in range(2):
        with contextlib.suppress(sa.exc.IntegrityError):
            conn.execute(sa.text("insert into creds values (1, :s)"), {"s": SENTINEL})


SQL_CORPUS = [
    pytest.param("inline_literal", {}, False, _sql_inline_literal, marks=pytest.mark.needs_sqlalchemy),
    pytest.param("bind_values_on", {"sql_trace_capture_parameters": True}, False, _sql_bind_values,
                 marks=pytest.mark.needs_sqlalchemy),
    pytest.param("integrity_error", {}, False, _sql_integrity_error, marks=pytest.mark.needs_sqlalchemy),
    pytest.param("echo_bind_values", {}, True, _sql_bind_values, marks=pytest.mark.needs_sqlalchemy),
    pytest.param("metadata_only_error", {"expose_values": "METADATA_ONLY", "sql_trace_capture_parameters": True},
                 False, _sql_integrity_error, marks=pytest.mark.needs_sqlalchemy),
]  # fmt: skip


@pytest.mark.parametrize(("row", "options", "echo", "run"), SQL_CORPUS)
def test_sql_trace_masks_statements(
    tmp_path: Path, row: str, options: dict[str, Any], echo: bool, run: Callable[[Any, Any], None]
):
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine("sqlite://", echo=echo)
    app = create_app(
        show_banner=False, state_dir=str(tmp_path), mcp_enabled="ON", stream_max_seconds=0.05, engines=[engine],
        **options,
    )  # fmt: skip
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        with engine.connect() as conn:
            run(sa, conn)
        report = client.get(f"{API}/sql-trace").json()
        stream = client.get(f"{API}/sql-trace/stream").text
        call = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_sql_traces", "arguments": {}},
        }
        mcp = client.post(f"{API}/mcp", json=call).text
        cli = client.post(f"{API}/cli/tools/get_sql_traces", json={}).text
        logs = str(client.get(f"{API}/log-tail/recent").json())
    assert report["entries"], row
    if "error" in row:
        failed = next(e for e in report["entries"] if not e["success"])
        assert failed["errorMessage"] is None if "metadata" in row else "IntegrityError" in failed["errorMessage"]
    for where, text in {"report": str(report), "stream": stream, "mcp": mcp, "cli": cli, "logs": logs}.items():
        assert SENTINEL not in text and JWT not in text, (row, where)


def _task_request_path(tmp_path: Path) -> str:
    """A host request parked on the loop while the Threads panel, MCP and CLI read its task's request path."""
    app = FastAPI()
    entered, release = threading.Event(), asyncio.Event()

    @app.get("/reset/{token}")
    async def reset(token: str) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        entered.set()
        await release.wait()
        return {}

    install(app, enabled="ON", show_banner=False, state_dir=str(tmp_path), mcp_enabled="ON", cli_enabled=True)
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        host = threading.Thread(target=lambda: client.get(f"/reset/{JWT}"), daemon=True)
        host.start()
        try:
            assert entered.wait(5)
            seen = [client.get(f"{API}/threads").text, client.post(f"{API}/cli/tools/get_threads", json={}).text]
            call = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_threads", "arguments": {}},
            }
            seen.append(client.post(f"{API}/mcp", json=call).text)
        finally:
            client.portal.call(release.set)  # pyright: ignore[reportOptionalMemberAccess]
            host.join(5)
    assert all(f"/reset/{MASK}" in text for text in seen), seen  # the plant really reached the report
    return "\n".join(seen)


def _pool_username(tmp_path: Path) -> str:
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'app.db'}", poolclass=sa.QueuePool)
    engine.url = engine.url.set(username=SENTINEL)  # pysqlite refuses userinfo at create_engine
    app = create_app(show_banner=False, state_dir=str(tmp_path), mcp_enabled="ON", engines=[engine])
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        report = client.get(f"{API}/database-connection-pools/pools").json()
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
        params = {"name": "get_database_connection_pools", "arguments": {}}
        mcp = client.post(f"{API}/mcp", json={**call, "params": params}).text
    assert [p["username"] for p in report["pools"]] == [MASK]
    return f"{report}\n{mcp}"


@pytest.mark.parametrize(
    "plant",
    [
        pytest.param(_task_request_path, id="task_request_path"),
        pytest.param(_pool_username, id="pool_username", marks=pytest.mark.needs_sqlalchemy),
    ],
)
def test_threads_and_pools_mask(tmp_path: Path, plant: Callable[[Path], str]):
    text = plant(tmp_path)
    assert SENTINEL not in text and JWT not in text
