"""Authentication, authorization and CSRF rules over route schemes and middleware stacks (nothing is called)."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from typing import Any

from fastapi.security import APIKeyCookie, HTTPBasic, OAuth2PasswordBearer
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.routing import Host, Mount
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import Depends, FastAPI, Security
from sharpit.engine.collectors.security import View

RuleRun = Callable[..., list[tuple[str, str]]]


class Wrapper:
    """A hand-written pure-ASGI wrapper (not a Starlette middleware class)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class CSRFMiddleware(Wrapper):
    """Stands in for ``starlette_csrf.CSRFMiddleware``."""


def _never(*_args: Any) -> str:
    raise AssertionError("a dependency or endpoint was called")


def _targets(found: list[tuple[str, str]]) -> list[str]:
    return [target for target, _ in found]


def _with(scheme: Any, *, method: str = "get", path: str = "/items", https: bool = False) -> FastAPI:
    app = FastAPI()
    if https:
        app.add_middleware(HTTPSRedirectMiddleware)
    app.add_api_route(path, _never, methods=[method.upper()], dependencies=[Depends(scheme)])
    return app


def test_http_basic_without_https(run_rule: RuleRun):
    # ported: SecurityRulesTests.basicAuthWithoutTlsFiresInProduction
    # ported: SecurityRulesTests.basicAuthWithoutTlsIsIgnoredOutsideProduction
    app = _with(HTTPBasic())
    assert _targets(run_rule("SEC-AUTH-007", app)) == []
    assert _targets(run_rule("SEC-AUTH-007", app, view=View(production=True))) == ["GET /items"]
    assert _targets(run_rule("SEC-AUTH-007", _with(HTTPBasic(), https=True), view=View(production=True))) == []


def test_password_form_login_without_https(run_rule: RuleRun):
    # ported: SecurityRulesTests.formLoginWithoutTlsFiresInProduction
    # ported: SecurityRulesTests.formLoginWithoutTlsIsIgnoredOutsideProduction
    bearer = OAuth2PasswordBearer(tokenUrl="token")
    app = _with(bearer)
    assert _targets(run_rule("SEC-AUTH-010", app)) == []
    assert _targets(run_rule("SEC-AUTH-010", app, view=View(production=True))) == ["GET /items"]
    assert _targets(run_rule("SEC-AUTH-010", _with(bearer, https=True), view=View(production=True))) == []


def _scoped_app() -> FastAPI:
    oauth2 = OAuth2PasswordBearer(tokenUrl="token", scopes={"admin": "admins"})

    def user(token: str = Depends(oauth2)) -> str:
        return _never(token)

    app = FastAPI()
    app.add_api_route("/me", _never, methods=["GET"], dependencies=[Depends(user)])
    app.add_api_route("/admin", _never, methods=["DELETE"], dependencies=[Security(user, scopes=["admin"])])
    app.add_api_route("/public", _never, methods=["POST"])
    app.add_api_route("/health", _never, methods=["GET"])
    return app


def test_unsecured_write_route_in_a_secured_app(run_rule: RuleRun):
    # ported: SecurityRulesTests.missingAuthorizationFilter (INFO in Python: public write routes can be intended)
    assert _targets(run_rule("SEC-AUTHZ-001", _scoped_app())) == ["POST /public"]


def test_scopes_floor_and_newest_classify_same(run_rule: RuleRun):
    # A ``Security(..., scopes=[...])`` route and a plain ``Depends`` route are both secured on the installed FastAPI;
    # CI runs this on the floor (0.115, ``security_scopes``) and the newest (``own_oauth_scopes``) alike.
    found = run_rule("SEC-AUTHZ-001", _scoped_app()) + run_rule("SEC-AUTHZ-002", _scoped_app())
    assert _targets(found) == ["POST /public"]


def test_blanket_permit_all(run_rule: RuleRun):
    # ported: SecurityScannerTests.blanketPermitAllRequiresEveryBoundedPathProbeToBeGranted (static: no route secured)
    open_app = FastAPI()
    open_app.add_api_route("/items", _never, methods=["GET", "POST"])
    found = [_targets(run_rule("SEC-AUTHZ-002", app)) for app in (open_app, _scoped_app())]
    assert found == [["application"], []]


def test_wrapped_host_and_static_files_are_never_called_permit_all(run_rule: RuleRun):
    # R-fastapi-security council follow-ups: a Host route behind a hand-written wrapper is unknown (not unsecured),
    # and a hand-written wrapper around StaticFiles is served as is; neither crashes nor counts as secured
    sub = FastAPI()
    sub.add_api_route("/me", _never, methods=["GET"], dependencies=[Depends(OAuth2PasswordBearer(tokenUrl="t"))])
    app = FastAPI()
    app.router.routes.append(Host("api.example", app=Wrapper(sub)))
    app.router.routes.append(Mount("/static", app=Wrapper(StaticFiles(directory=tempfile.gettempdir()))))
    app.add_api_route("/items", _never, methods=["GET"])
    assert run_rule("SEC-AUTHZ-002", app) == []


def test_csrf_for_cookie_credentials(run_rule: RuleRun):
    # ported: SecurityRulesTests.csrfDisabledStateful
    cookie = APIKeyCookie(name="session")
    unprotected = _with(cookie, method="post")
    protected = _with(cookie, method="post")
    protected.add_middleware(CSRFMiddleware)
    read_only = _with(cookie, method="get")
    found = [_targets(run_rule("SEC-CSRF-001", app)) for app in (unprotected, protected, read_only)]
    assert found == [["POST /items"], [], []]


def test_csrf_for_http_basic(run_rule: RuleRun):
    # ported: SecurityRulesTests.csrfGloballyDisabled (HTTP Basic credentials are resent by browsers)
    found = [_targets(run_rule("SEC-CSRF-002", _with(HTTPBasic(), method=m))) for m in ("put", "get")]
    assert found == [["PUT /items"], []]


def test_public_openapi_for_a_secured_api(run_rule: RuleRun):
    secured = _with(OAuth2PasswordBearer(tokenUrl="token"))
    hidden = FastAPI(openapi_url=None)
    hidden.add_api_route("/items", _never, methods=["GET"], dependencies=[Depends(HTTPBasic())])
    open_app = FastAPI()
    open_app.add_api_route("/items", _never, methods=["GET"])
    found = [_targets(run_rule("SEC-FAPI-002", app)) for app in (secured, hidden, open_app)]
    assert found == [["/openapi.json"], [], []]


def test_optional_scheme_is_the_only_check(run_rule: RuleRun):
    optional = _with(OAuth2PasswordBearer(tokenUrl="token", auto_error=False))
    required = _with(OAuth2PasswordBearer(tokenUrl="token"))
    found = [_targets(run_rule("SEC-FAPI-004", app)) for app in (optional, required)]
    assert found == [["GET /items"], []]


def test_route_mixes_authentication_schemes(run_rule: RuleRun):
    app = FastAPI()
    both = [Depends(HTTPBasic()), Depends(OAuth2PasswordBearer(tokenUrl="token"))]
    app.add_api_route("/mixed", _never, methods=["GET"], dependencies=both)
    app.add_api_route("/single", _never, methods=["GET"], dependencies=[Depends(HTTPBasic())])
    assert _targets(run_rule("SEC-FAPI-005", app)) == ["GET /mixed"]
