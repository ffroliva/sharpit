import asyncio
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from conftest import golden
from fastapi import FastAPI, Request
from sharpit import install
from sharpit.engine.guard import (
    MESSAGE_CROSS_SITE,
    MESSAGE_DISALLOWED_HOST,
    MESSAGE_FORWARDED_SOURCE,
)
from sharpit.engine.headers import CSP
from sharpit.engine.sqltext import identity
from sharpit.fastapi.adapter import SharpitMount
from sharpit.settings import SharpitSettings
from surface import BASE_PANEL_IDS, expected_panel_ids

LOCAL = ("127.0.0.1", 50000)
REMOTE = ("10.0.0.5", 50000)
TOKEN = "test-token"
# A stream must outlive the agent-sessions debounce, or its loop body (refresh, resend) never runs in the sweep.
STREAM_SWEEP_SECONDS = max(SharpitSettings.copilot_stream_debounce, SharpitSettings.claude_code_stream_debounce) + 0.25
AUTH_REQUIRED = {"error": "sharpit authentication required"}


def _app(**options: Any) -> FastAPI:
    app = FastAPI(title="petclinic")
    install(app, **{"enabled": "ON", "show_banner": False, **options})
    return app


def _client(app: Any, client: tuple[str, int] = LOCAL, base_url: str = "http://localhost", **kw: Any) -> TestClient:
    return TestClient(app, base_url=base_url, client=client, follow_redirects=False, **kw)


def test_inactive_404_every_path_and_method():
    app = FastAPI()
    install(app, enabled="OFF")
    client = _client(app)
    host_404 = client.get("/definitely-not-a-route")
    assert host_404.status_code == 404
    for path in ("/sharpit", "/sharpit/", "/sharpit/api/overview", "/sharpit/api/nope"):
        for method in ("GET", "POST", "DELETE"):
            resp = client.request(method, path)
            assert resp.status_code == 404, (method, path)
            assert resp.json() == host_404.json() == {"detail": "Not Found"}
            assert "content-security-policy" not in resp.headers
            assert "x-frame-options" not in resp.headers


def test_inactive_logs_reason(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger="sharpit"):
        install(FastAPI(), enabled="OFF")
    assert [r.getMessage() for r in caplog.records] == ["sharpit inactive: Disabled by SHARPIT_ENABLED=OFF"]


def test_an_inactive_install_creates_no_key(tmp_path: Any) -> None:
    install(FastAPI(), enabled="OFF", state_dir=str(tmp_path))
    assert not (tmp_path / "identity.key").exists()


def test_the_env_key_overrides_the_file(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    key = "k" * 32
    (tmp_path / "identity.key").write_bytes(b"f" * 32)
    monkeypatch.setenv("SHARPIT_IDENTITY_KEY", key)
    handle = install(FastAPI(), enabled="ON", show_banner=False, state_dir=str(tmp_path))
    assert handle.context.masker.identity_key == key.encode()
    assert (tmp_path / "identity.key").read_bytes() == b"f" * 32


def test_no_key_leaves_sqlite_statements_ungrouped(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from sharpit.fastapi import install as install_module

    monkeypatch.setattr(install_module, "load_key", lambda *_args, **_kw: None)
    handle = install(FastAPI(), enabled="ON", show_banner=False, state_dir=str(tmp_path))
    assert handle.context.masker.identity_key is None
    assert len([row for row in caplog.records if "SQLite statement identities are unavailable" in row.message]) == 1
    from sharpit.engine.capture.sqltrace import SqlTraceRecorder
    from sharpit.engine.sqltext import Dialect

    recorder = SqlTraceRecorder(handle.context.masker)
    recorder.record(
        'select "id" from "users"', duration_ns=1, thread="main", connection_id=None, dialect=Dialect.SQLITE
    )
    assert recorder.aggregate_count == 0


def test_install_creates_the_key_in_a_fresh_directory(tmp_path: Any) -> None:
    state_dir = tmp_path / "fresh"
    handle = install(FastAPI(), enabled="ON", show_banner=False, state_dir=str(state_dir))
    assert handle.context.masker.identity_key == (state_dir / "identity.key").read_bytes()


def _spy_on_load_key(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Every ``create`` a read passes. With the key on disk, ``create=True`` writes nothing: only the argument shows."""
    real, calls = identity.load_key, []

    def spy(state_dir: Any, *, create: bool) -> bytes | None:
        calls.append(create)
        return real(state_dir, create=create)

    for name, module in list(sys.modules.items()):
        if name.startswith("sharpit") and hasattr(module, "load_key"):
            monkeypatch.setattr(module, "load_key", spy)
    return calls


def _get_routes(app: FastAPI) -> list[str]:
    mount = next(route for route in app.router.routes if isinstance(route, SharpitMount))
    found = [route.path_format for route in mount.routes if isinstance(route, Route) and "GET" in (route.methods or ())]
    return ["/sharpit" + path for path in found if "{" not in path]


def test_a_read_creates_no_key(no_side_effects: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    install(
        app,
        enabled="ON",
        show_banner=False,
        state_dir=str(no_side_effects.state_dir),
        stream_max_seconds=STREAM_SWEEP_SECONDS,
    )
    assert (no_side_effects.state_dir / "identity.key").is_file()
    no_side_effects.rebaseline()
    calls = _spy_on_load_key(monkeypatch)
    no_side_effects.unblock_network()
    with _client(app) as client:
        no_side_effects.block_network()
        statuses = {path: client.get(path).status_code for path in _get_routes(app)}
    assert statuses["/sharpit/api/overview"] == 200
    assert no_side_effects.violations == []
    assert True not in calls, "a GET asked to create the key"


def test_bare_path_goes_through_guard():
    resp = _client(_app()).get("/sharpit", headers={"Host": "evil.example"})
    assert resp.status_code == 403
    assert resp.json() == {"error": MESSAGE_DISALLOWED_HOST}


def test_redirect_to_trailing_slash():
    resp = _client(_app()).get("/sharpit")
    assert resp.status_code == 307
    assert resp.headers["location"].endswith("/sharpit/")


def test_shell_served_with_csp_and_no_cache():
    resp = _client(_app()).get("/sharpit/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert resp.headers["content-security-policy"] == CSP
    assert resp.headers["cache-control"] == "no-cache"


def test_asset_traversal_is_404():
    assert _client(_app()).get("/sharpit/assets/index.html").status_code == 404
    for path in ("/sharpit/assets/..", r"/sharpit/assets/..\index.html"):  # raw: httpx would normalise ".."
        assert _status_and_body(_raw(_app(), [(b"host", b"localhost")], path=path))[0] == 404


def test_overview_shape_matches_golden_keys():
    resp = _client(_app()).get("/sharpit/api/overview")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store, must-revalidate"
    assert resp.headers["pragma"] == "no-cache"
    body = resp.json()
    assert set(body) == set(golden("overview")) | {"run"}  # BootUI 2.2.0 OverviewDto.run
    assert body["frameworkName"] == "FastAPI"
    assert body["webApplicationType"] == "ASGI"
    assert body["managementPort"] is None
    assert body["applicationName"] == "petclinic"
    assert body["openApiUrl"] == "/docs"


def test_panels_platform_fastapi_and_ids():
    resp = _client(_app(panels={"loggers": {"read_only": True}}, read_only=False)).get("/sharpit/api/panels")
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "fastapi"
    assert [p["id"] for p in body["panels"]] == expected_panel_ids()  # the base panels, then implemented 0.4 panels
    live_memory = next(p for p in body["panels"] if p["id"] == "live-memory")
    assert live_memory["title"] == "Live Memory"
    assert live_memory["enabled"] is True
    assert live_memory["readOnly"] is False
    loggers = body["panels"][3]
    assert loggers["readOnly"] is True
    assert loggers["readOnlyReason"] == "Panel is read-only via SHARPIT_PANELS_LOGGERS_READ_ONLY=true"


def test_mvp_panels_stay_available():
    body = _client(_app()).get("/sharpit/api/panels").json()
    # sql-trace depends on whether SQLAlchemy is imported: test_sql_trace_api and test_sqla_absent cover both states
    # alembic depends on whether an Alembic config is found: test_alembic_api covers both states
    # database-connection-pools depends on whether SQLAlchemy is imported: test_panel_availability covers both states
    excluded = ("sql-trace", "alembic", "database-connection-pools")
    mvp = [p for p in body["panels"] if p["id"] in BASE_PANEL_IDS and p["id"] not in excluded]
    assert len(mvp) == 17  # the live-memory panel is included alongside the 0.2.0 additions
    # activity (Task 6), health (Task 7), threads (Task 8), rest-api (Task 10), http-probe (Task 11)
    assert all(p["available"] and p["unavailableReason"] is None for p in mvp)


def test_catch_all_does_not_shadow():
    app = FastAPI()

    @app.api_route("/{p:path}", methods=["GET", "POST"])
    def spa(p: str) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"host": p}

    install(app, enabled="ON", show_banner=False)
    client = _client(app)
    assert client.get("/sharpit").status_code == 307
    assert client.get("/sharpit/api/overview").json()["frameworkName"] == "FastAPI"
    assert client.get("/elsewhere").json() == {"host": "elsewhere"}


def test_custom_paths():
    app = _app(path="/dev/console", api_path="/dev/console/rest", allow_non_localhost=True, authentication_token=TOKEN)
    assert _client(app).get("/dev/console/rest/overview").status_code == 200
    assert _client(app).get("/sharpit/api/overview").status_code == 404
    resp = _client(app, REMOTE).post("/dev/console/rest/auth/session", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 204
    assert resp.headers["set-cookie"] == f"SHARPIT_SESSION={TOKEN}; Path=/dev/console/rest; HttpOnly; SameSite=Strict"


def test_host_cors_wildcard_cannot_read():
    app = _app()
    app.add_middleware(CORSMiddleware, allow_origins=["*"])
    resp = _client(app).get("/sharpit/api/overview", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403
    assert resp.json() == {"error": MESSAGE_CROSS_SITE}


def test_host_trusted_host_middleware_with_localhost_allowed():
    app = _app()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost"])
    assert _client(app).get("/sharpit/api/overview").status_code == 200


def test_remote_needs_token_and_session_cookie():
    app = _app(allow_non_localhost=True, authentication_token=TOKEN)
    client = _client(app, REMOTE)

    denied = client.get("/sharpit/api/overview")
    assert denied.status_code == 401
    assert denied.json() == AUTH_REQUIRED
    assert denied.headers["www-authenticate"] == 'Bearer realm="sharpit"'
    assert denied.headers["cache-control"] == "no-store"

    session = client.post("/sharpit/api/auth/session", headers={"Authorization": f"Bearer {TOKEN}"})
    assert session.status_code == 204
    cookie = session.headers["set-cookie"]
    assert cookie.startswith("SHARPIT_SESSION=")
    assert cookie.endswith("; Path=/sharpit/api; HttpOnly; SameSite=Strict")

    client.cookies.clear()
    ok = client.get("/sharpit/api/overview", headers={"Cookie": f"SHARPIT_SESSION={TOKEN}"})
    assert ok.status_code == 200

    wrong = client.post("/sharpit/api/auth/session", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401
    assert wrong.json() == AUTH_REQUIRED
    assert "set-cookie" not in wrong.headers

    secure = _client(app, REMOTE, base_url="https://localhost").post(
        "/sharpit/api/auth/session", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert secure.headers["set-cookie"].endswith("; SameSite=Strict; Secure")


# ported: ApiAuthenticationFilterTests.validBearerTokenCreatesAnHttpOnlyBrowserSession
def test_valid_bearer_token_creates_an_http_only_browser_session():
    app = _app(allow_non_localhost=True, authentication_token=TOKEN)
    resp = _client(app, REMOTE).post("/sharpit/api/auth/session", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 204
    assert resp.headers["set-cookie"] == "SHARPIT_SESSION=test-token; Path=/sharpit/api; HttpOnly; SameSite=Strict"


# ported: ApiAuthenticationFilterTests.sessionCookieIncludesTheServletContextAndConfiguredApiPath
# The servlet context path is the ASGI root_path; sharpit requires api_path under path, so /internal/bootui-api
# becomes /console/internal-api.
def test_session_cookie_includes_the_root_path_and_configured_api_path():
    app = _app(path="/console", api_path="/console/internal-api", allow_non_localhost=True, authentication_token=TOKEN)
    resp = _client(app, REMOTE, root_path="/host").post(
        "/host/console/internal-api/auth/session", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert resp.status_code == 204
    expected = "SHARPIT_SESSION=test-token; Path=/host/console/internal-api; HttpOnly; SameSite=Strict"
    assert resp.headers["set-cookie"] == expected


def test_trusted_source_session_sets_no_cookie():
    resp = _client(_app()).post("/sharpit/api/auth/session")
    assert resp.status_code == 204
    assert "set-cookie" not in resp.headers


def test_xff_spoof_through_uvicorn_proxy_headers():
    wrapped = ProxyHeadersMiddleware(_app(), trusted_hosts="*")
    resp = _client(wrapped, REMOTE).get("/sharpit/api/overview", headers={"X-Forwarded-For": "127.0.0.1"})
    assert resp.status_code == 403
    assert resp.json() == {"error": MESSAGE_FORWARDED_SOURCE}


def test_startup_time_set_after_lifespan():
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[dict[str, str]]:
        yield {"flag": "host-state"}

    app = FastAPI(lifespan=lifespan)

    @app.get("/flag")
    def flag(request: Request) -> str:  # pyright: ignore[reportUnusedFunction]
        return request.state.flag

    handle = install(app, enabled="ON", show_banner=False)
    assert handle.original_lifespan is lifespan
    assert _client(app).get("/sharpit/api/overview").json()["startupTimeMillis"] is None
    with _client(app) as client:
        assert client.get("/flag").json() == "host-state"
        startup = client.get("/sharpit/api/overview").json()["startupTimeMillis"]
    assert isinstance(startup, int)
    assert startup >= 0


def test_banner_prints_generated_token(capsys: pytest.CaptureFixture[str]):
    handle = install(FastAPI(), enabled="ON", allow_non_localhost=True)
    token = handle.context.token
    assert token
    assert token in capsys.readouterr().err


def test_generated_token_printed_once_without_banner(capsys: pytest.CaptureFixture[str]):
    handle = install(FastAPI(), enabled="ON", allow_non_localhost=True, show_banner=False)
    token = handle.context.token
    assert token
    err = capsys.readouterr().err
    assert err.count(token) == 1
    assert err.count("\n") == 1
    assert "sharpit active at" not in err


def test_no_output_without_banner_or_generated_token(capsys: pytest.CaptureFixture[str]):
    install(FastAPI(), enabled="ON", allow_non_localhost=True, authentication_token="configured", show_banner=False)
    assert capsys.readouterr().err == ""


def test_banner_never_prints_configured_token(capsys: pytest.CaptureFixture[str]):
    install(FastAPI(), enabled="ON", allow_non_localhost=True, authentication_token="configured-secret")
    err = capsys.readouterr().err
    assert "sharpit" in err
    assert "configured-secret" not in err


def test_expose_full_logs_warning(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        install(FastAPI(), enabled="ON", show_banner=False, expose_values="FULL")
    assert any(r.levelno == logging.WARNING and "FULL" in r.getMessage() for r in caplog.records)


# --- raw ASGI: duplicate headers and non-HTTP scopes (httpx would normalise these) ----------------------------------


def _raw(
    app: Any, headers: list[tuple[bytes, bytes]], scope_type: str = "http", path: str = "/sharpit/api/overview"
) -> list[dict[str, Any]]:
    scope: dict[str, Any] = {
        "type": scope_type,
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http" if scope_type == "http" else "ws",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "client": LOCAL,
        "server": ("localhost", 80),
    }
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent


def _status_and_body(sent: list[dict[str, Any]]) -> tuple[int, bytes]:
    return sent[0]["status"], b"".join(m.get("body", b"") for m in sent[1:])


def test_raw_single_localhost_host_is_allowed():
    assert _status_and_body(_raw(_app(), [(b"host", b"localhost")]))[0] == 200


def test_duplicate_host_header_is_denied_as_disallowed_host():
    status, body = _status_and_body(_raw(_app(), [(b"host", b"localhost"), (b"host", b"evil.example")]))
    assert status == 403
    assert MESSAGE_DISALLOWED_HOST.encode() in body


def test_duplicate_origin_header_is_denied_as_cross_site():
    headers = [(b"host", b"localhost"), (b"origin", b"http://localhost"), (b"origin", b"http://localhost")]
    status, body = _status_and_body(_raw(_app(), headers))
    assert status == 403
    assert MESSAGE_CROSS_SITE.encode() in body


def test_websocket_scope_is_closed():
    sent = _raw(_app(), [(b"host", b"localhost")], scope_type="websocket")
    assert sent == [{"type": "websocket.close", "code": 1000, "reason": ""}]


def test_inactive_websocket_scope_is_closed():
    app = FastAPI()
    install(app, enabled="OFF")
    sent = _raw(app, [(b"host", b"localhost")], scope_type="websocket")
    assert sent == [{"type": "websocket.close", "code": 1000, "reason": ""}]


# --- Task P1 items 4-7: install() robustness ----------------------------------------------------------------------


class _AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="P1APP_")
    region: str = "eu"


def _config_names(app: FastAPI) -> set[str]:
    body = _client(app).get("/sharpit/api/config", params={"q": "p1app_", "limit": 500}).json()
    return {p["name"] for p in body["properties"]}


def test_settings_accepts_a_single_instance():
    assert "P1APP_REGION" in _config_names(_app(config_scan=False, settings=_AppSettings()))
    assert "P1APP_REGION" in _config_names(_app(config_scan=False, settings=[_AppSettings()]))


def test_settings_rejects_a_non_settings_object():
    with pytest.raises(TypeError, match="settings"):
        _app(settings=[object()])


def test_second_install_is_a_noop_with_a_warning(caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]):
    app = FastAPI()
    first = install(app, enabled="ON")
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        second = install(app, enabled="ON")
    assert second is first
    assert sum(getattr(r, "name", None) == "sharpit" for r in app.router.routes) == 1
    assert capsys.readouterr().err.count("sharpit active at") == 1
    assert any("already" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


def test_settings_warnings_are_logged(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SHARPIT_MCP_MAX_RESULTS", "lots")
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        install(FastAPI(), enabled="ON", show_banner=False)
    assert "Ignoring invalid SHARPIT_MCP_MAX_RESULTS value 'lots'" in [
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    ]


def test_explicit_off_is_info(caplog: pytest.LogCaptureFixture):
    # review M3: switching sharpit off on purpose is not a warning
    with caplog.at_level(logging.INFO, logger="sharpit"):
        install(FastAPI(), enabled="OFF")
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.INFO, "sharpit inactive: Disabled by SHARPIT_ENABLED=OFF")
    ]


def test_requested_but_inactive_is_a_warning(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch):
    # an enabled profile that a disabled profile overrides, and an unusable SHARPIT_ENABLED: asked for, still off
    monkeypatch.setenv("SHARPIT_PROFILES", "dev,prod")
    with caplog.at_level(logging.INFO, logger="sharpit"):
        install(FastAPI(), show_banner=False)
        install(FastAPI(), enabled="maybe")
    inactive = [r for r in caplog.records if r.getMessage().startswith("sharpit inactive")]
    assert [r.levelno for r in inactive] == [logging.WARNING, logging.WARNING]


def test_second_install_after_an_inactive_one_names_the_reason(caplog: pytest.LogCaptureFixture):
    # review M4
    app = FastAPI()
    install(app, enabled="OFF")
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        install(app, enabled="ON")
    (again,) = [r.getMessage() for r in caplog.records if "already called" in r.getMessage()]
    assert "Disabled by SHARPIT_ENABLED=OFF" in again


def test_inactive_reason_is_info_when_nothing_was_configured(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    for name in [n for n in os.environ if n.upper().startswith("SHARPIT_")]:
        monkeypatch.delenv(name)
    with caplog.at_level(logging.INFO, logger="sharpit"):
        install(FastAPI())
    assert [r.levelno for r in caplog.records] == [logging.INFO]


def _nested(**options: Any) -> FastAPI:
    outer, inner = FastAPI(), FastAPI()
    install(inner, **{"enabled": "ON", "show_banner": False, **options})
    outer.mount("/v1", inner)
    return outer


def test_nested_mount_cookie_path_includes_the_mount_prefix():
    client = _client(_nested(allow_non_localhost=True, authentication_token=TOKEN), REMOTE)
    resp = client.post("/v1/sharpit/api/auth/session", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 204
    assert "Path=/v1/sharpit/api;" in resp.headers["set-cookie"]
    assert client.get("/v1/sharpit/api/overview").status_code == 200  # the cookie comes back


def test_advertised_endpoints_include_the_root_path():
    client = _client(_nested())
    assert client.get("/v1/sharpit/api/cli").json()["endpoint"] == "/v1/sharpit/api/cli"
    assert client.get("/v1/sharpit/api/mcp-server").json()["endpoint"] == "/v1/sharpit/api/mcp"
    toggled = client.post("/v1/sharpit/api/mcp-server/toggle", json={"enabled": False}).json()
    assert toggled["endpoint"] == "/v1/sharpit/api/mcp"
    plain = _client(_app())
    assert plain.get("/sharpit/api/cli").json()["endpoint"] == "/sharpit/api/cli"


def test_app_root_path_prefixes_the_advertised_endpoints():
    app = FastAPI(root_path="/proxy")
    install(app, enabled="ON", show_banner=False)
    client = _client(app)
    assert client.get("/proxy/sharpit/api/cli").json()["endpoint"] == "/proxy/sharpit/api/cli"
    assert client.get("/proxy/sharpit/api/mcp-server").json()["endpoint"] == "/proxy/sharpit/api/mcp"
