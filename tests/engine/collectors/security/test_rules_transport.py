"""Session, CORS, OAuth2 endpoint and host/proxy rules (BootUI ``SecurityRules``; SEC-FAPI-001/003 are new)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.security import OAuth2AuthorizationCodeBearer, OpenIdConnect
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from fastapi import Depends, FastAPI
from sharpit.engine.collectors.security import View

RuleRun = Callable[..., list[tuple[str, str]]]
LONG_SECRET = "x" * 40
SHORT_SECRET = "s3cr3t-signing-key"  # 18 characters


class SessionMiddleware:
    """Stands in for Starlette's (which needs ``itsdangerous``): same name and options."""

    def __init__(self, app: ASGIApp, secret_key: str, same_site: str = "lax", https_only: bool = False) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


def _app(*middleware: tuple[Any, dict[str, Any]]) -> FastAPI:
    app = FastAPI()
    for cls, options in middleware:
        app.add_middleware(cls, **options)
    app.get("/items")(lambda: "items")
    return app


def _targets(found: list[tuple[str, str]]) -> list[str]:
    return [target for target, _ in found]


def test_session_cookie_without_https_only(run_rule: RuleRun):
    # ported: SecurityRulesTests.sessionCookieSecureReviewsProductionWithoutDirectTls
    plain = _app((SessionMiddleware, {"secret_key": LONG_SECRET}))
    secure = _app((SessionMiddleware, {"secret_key": LONG_SECRET, "https_only": True}))
    assert _targets(run_rule("SEC-SESSION-002", plain)) == []
    found = [_targets(run_rule("SEC-SESSION-002", app, view=View(production=True))) for app in (plain, secure)]
    assert found == [["SessionMiddleware"], []]


def test_session_cookie_same_site_none(run_rule: RuleRun):
    none = _app((SessionMiddleware, {"secret_key": LONG_SECRET, "same_site": "none"}))
    lax = _app((SessionMiddleware, {"secret_key": LONG_SECRET}))
    found = [_targets(run_rule("SEC-SESSION-004", app)) for app in (none, lax)]
    assert found == [["SessionMiddleware"], []]


def test_session_secret_shorter_than_32_characters(run_rule: RuleRun):
    short = _app((SessionMiddleware, {"secret_key": SHORT_SECRET}))
    long = _app((SessionMiddleware, {"secret_key": LONG_SECRET}))
    found = [_targets(run_rule("SEC-SESSION-008", app)) for app in (short, long)]
    assert found == [["SessionMiddleware"], []]


def test_session_secret_message_has_no_secret(run_rule: RuleRun):
    found = run_rule("SEC-SESSION-008", _app((SessionMiddleware, {"secret_key": SHORT_SECRET})))
    assert found != []
    assert SHORT_SECRET not in repr(found)


def test_cors_wildcard_without_credentials(run_rule: RuleRun):
    # ported: SecurityRulesTests.corsWildcardOriginWithoutCredentials
    wildcard = _app((CORSMiddleware, {"allow_origins": ["*"]}))
    credentialed = _app((CORSMiddleware, {"allow_origins": ["*"], "allow_credentials": True}))
    listed = _app((CORSMiddleware, {"allow_origins": ["https://app.example"]}))
    found = [_targets(run_rule("SEC-CORS-001", app)) for app in (wildcard, credentialed, listed)]
    assert found == [["CORSMiddleware"], [], []]


def test_cors_wildcard_with_credentials(run_rule: RuleRun):
    # ported: SecurityRulesTests.corsWildcardWithCredentials
    credentialed = _app((CORSMiddleware, {"allow_origins": ["*"], "allow_credentials": True}))
    wildcard = _app((CORSMiddleware, {"allow_origins": ["*"]}))
    found = [_targets(run_rule("SEC-CORS-002", app)) for app in (credentialed, wildcard)]
    assert found == [["CORSMiddleware"], []]


def test_cors_broad_origin_regex(run_rule: RuleRun):
    broad = _app((CORSMiddleware, {"allow_origin_regex": "https?://.*"}))
    anchored = _app((CORSMiddleware, {"allow_origin_regex": r"https://[a-z0-9-]+\.example\.com"}))
    found = [_targets(run_rule("SEC-CORS-006", app)) for app in (broad, anchored)]
    assert found == [["CORSMiddleware"], []]


def _schemed(scheme: Any) -> FastAPI:
    app = FastAPI()

    @app.get("/me")
    def me(token: str = Depends(scheme)) -> str:  # pyright: ignore[reportUnusedFunction]
        raise AssertionError("an endpoint was called")

    return app


def test_openid_connect_url_over_http(run_rule: RuleRun):
    remote = _schemed(OpenIdConnect(openIdConnectUrl="http://idp.example/.well-known/openid-configuration"))
    loopback = _schemed(OpenIdConnect(openIdConnectUrl="http://localhost:8080/.well-known/openid-configuration"))
    secure = _schemed(OpenIdConnect(openIdConnectUrl="https://idp.example/.well-known/openid-configuration"))
    assert _targets(run_rule("SEC-OAUTH-004", remote)) == []
    found = [_targets(run_rule("SEC-OAUTH-004", app, view=View(production=True))) for app in (remote, loopback, secure)]
    assert found == [["OpenIdConnect openIdConnectUrl"], [], []]


def test_oauth2_flow_url_over_http(run_rule: RuleRun):
    scheme = OAuth2AuthorizationCodeBearer(
        authorizationUrl="http://idp.example/authorize", tokenUrl="token", refreshUrl="https://idp.example/refresh"
    )
    app = _schemed(scheme)
    assert _targets(run_rule("SEC-OAUTH-006", app)) == []
    found = _targets(run_rule("SEC-OAUTH-006", app, view=View(production=True)))
    assert found == ["OAuth2AuthorizationCodeBearer authorizationUrl"]


def test_host_header_not_restricted(run_rule: RuleRun):
    missing = _app()
    any_host = _app((TrustedHostMiddleware, {"allowed_hosts": ["*"]}))
    listed = _app((TrustedHostMiddleware, {"allowed_hosts": ["app.example"]}))
    found = [_targets(run_rule("SEC-FAPI-001", app)) for app in (missing, any_host, listed)]
    assert found == [["ASGI middleware stack"], ["TrustedHostMiddleware"], []]


def test_proxy_headers_trusted_from_any_host(run_rule: RuleRun):
    any_proxy = _app((ProxyHeadersMiddleware, {"trusted_hosts": "*"}))
    listed = _app((ProxyHeadersMiddleware, {"trusted_hosts": ["10.0.0.1"]}))
    found = [_targets(run_rule("SEC-FAPI-003", app)) for app in (any_proxy, listed)]
    assert found == [["ProxyHeadersMiddleware"], []]
