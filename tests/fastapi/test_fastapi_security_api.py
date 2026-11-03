"""``fastapi-security`` routes and MCP tool (BootUI ``spring-security``): static, nothing in the app is called."""

from __future__ import annotations

from typing import Any

from fastapi.security import OAuth2PasswordBearer
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.routing import BaseRoute, Match, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import Depends, FastAPI, Security
from golden import assert_parity
from sharpit import install
from sharpit.engine.collectors.appsecurity import explain
from sharpit.engine.panels import disabled_reason

API = "/sharpit/api/fastapi-security"
MCP = "/sharpit/api/mcp"
SESSION_SECRET = "s3ss10n-secret-key-do-not-leak"
ORIGIN_TOKEN = "sk_live_4eC39HqLyjWDarjtT1zdp7dc"
PRIVATE_HOST = "billing-db.internal.example"


class SessionMiddleware:
    """Stands in for Starlette's (which needs ``itsdangerous``): same name, a secret in its options."""

    def __init__(self, app: ASGIApp, secret_key: str) -> None:
        self.app = app
        self.secret_key = secret_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


async def legacy_app(scope: Scope, receive: Receive, send: Send) -> None:  # an opaque ASGI app
    raise AssertionError("a mounted application was called")


def build_app() -> FastAPI:
    oauth2 = OAuth2PasswordBearer(tokenUrl="token", scopes={"admin": "admins"})

    def current_user(token: str = Depends(oauth2)) -> str:
        raise AssertionError("a dependency was called")

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
    app.add_middleware(CORSMiddleware, allow_origins=[f"https://partner.example?token={ORIGIN_TOKEN}"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", PRIVATE_HOST])

    @app.get("/items/{item_id}")
    def item(item_id: int, user: str = Depends(current_user)) -> str:  # pyright: ignore[reportUnusedFunction]
        return user

    @app.post("/admin/purge")
    def purge(user: str = Security(current_user, scopes=["admin"])) -> str:  # pyright: ignore[reportUnusedFunction]
        return user

    @app.get("/health")
    def health() -> str:  # pyright: ignore[reportUnusedFunction]
        return "ok"

    app.mount("/legacy", legacy_app)
    return app


def client_for(app: Any = None, **options: Any) -> TestClient:
    app = app if app is not None else build_app()
    install(app, enabled="ON", show_banner=False, config_scan=False, **options)
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def test_report_golden_parity():
    response = client_for().get(API)
    assert response.status_code == 200
    assert_parity("fastapi-security", "report", response.json())


def test_endpoints_golden_parity():
    response = client_for().get(f"{API}/endpoints")
    assert response.status_code == 200
    assert_parity("fastapi-security", "endpoints", response.json())


def test_endpoints_rules():
    response = client_for().get(f"{API}/endpoints")
    assert response.status_code == 200
    rows = [(e["method"], e["pattern"], e["rule"], e["roles"], e["bestEffort"]) for e in response.json()["endpoints"]]
    assert rows == [
        ("POST", "/admin/purge", "hasAuthority", ["admin"], False),
        ("GET", "/health", "unsecured", [], False),
        ("GET", "/items/{item_id}", "authenticated", [], False),
        ("ANY", "/legacy/{path}", "unknown", [], True),
    ]


def test_explain_matches_route():
    # ported: SpringSecurityControllerTests.explainMatchesChainWhenPathMatches
    response = client_for().get(f"{API}/explain", params={"method": "GET", "path": "/items/42"})
    assert response.status_code == 200
    assert response.json() == {
        "matched": True,
        "bestEffort": False,
        "chainIndex": 0,
        "matcherDescription": "any request",
        "filters": ["TrustedHostMiddleware", "CORSMiddleware", "SessionMiddleware"],
        "rule": "authenticated",
        "roles": [],
        "pattern": "/items/{item_id}",
    }


def test_explain_defaults_to_get_root():
    response = client_for().get(f"{API}/explain")
    assert response.status_code == 200
    assert response.json()["matched"] is False


def test_explain_absent_is_unmatched():
    # ported: SpringSecurityControllerTests.explainEndpointWithAbsentProxyReturnsUnmatchedResult
    assert explain(None, "GET", "/", "/sharpit") == {
        "matched": False,
        "bestEffort": False,
        "chainIndex": None,
        "matcherDescription": None,
        "filters": [],
        "rule": None,
        "roles": [],
        "pattern": None,
    }


def _explain(client: TestClient, method: str, path: str) -> Any:
    return client.get(f"{API}/explain", params={"method": method, "path": path})


def test_explain_input_edges():
    client = client_for()
    no_slash = _explain(client, "GET", "items/1")
    too_long = _explain(client, "GET", "/" + "a" * 10_000)
    unknown_method = _explain(client, "BREW", "/items/1")
    opaque = _explain(client, "GET", "/legacy/old/page")
    own = _explain(client, "GET", "/sharpit/api/panels")
    assert [r.status_code for r in (no_slash, too_long, unknown_method, opaque, own)] == [400, 400, 200, 200, 200]
    assert no_slash.json() == {"error": "Invalid request"}
    assert too_long.json() == {"error": "Invalid request"}
    assert unknown_method.json()["matched"] is False
    assert opaque.json()["matched"] is True
    assert opaque.json()["bestEffort"] is True
    assert opaque.json()["rule"] == "unknown"
    assert own.json()["matched"] is False
    assert own.json()["matcherDescription"] == "sharpit endpoints are hidden from this report"


def test_middleware_values_never_exposed():
    client = client_for(mcp_enabled="ON")
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_fastapi_security"}}
    bodies = [
        client.get(API).text,
        client.get(f"{API}/endpoints").text,
        _explain(client, "GET", "/items/1").text,
        client.post(MCP, json=call).text,
    ]
    leaks = [(i, s) for i, body in enumerate(bodies) for s in (SESSION_SECRET, ORIGIN_TOKEN, PRIVATE_HOST) if s in body]
    assert leaks == []
    assert '"SessionMiddleware"' in bodies[0]  # the class name is reported, its options are not


def test_mcp_read_tool_only():
    client = client_for(mcp_enabled="ON")
    listed = client.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"]
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_fastapi_security"}}
    reply = client.post(MCP, json=call).json()
    actions = {t["name"]: t["action"] for t in client.get("/sharpit/api/mcp-server").json()["tools"]}
    assert [t["name"] for t in listed if "fastapi_security" in t["name"]] == ["get_fastapi_security"]
    assert actions.get("get_fastapi_security") is False
    assert reply["result"]["isError"] is False
    assert reply["result"]["structuredContent"]["springSecurityPresent"] is True


def test_panel_disabled_403():
    response = client_for(panels={"fastapi-security": {"enabled": False}}).get(API)
    assert response.status_code == 403
    assert response.json() == {
        "error": "sharpit panel access denied",
        "panel": "fastapi-security",
        "reason": disabled_reason("fastapi-security"),
    }


class TrapRoute(BaseRoute):
    """A custom route class: every property read and method call on it is recorded."""

    def __init__(self) -> None:
        self.touched: list[str] = []

    @property
    def path(self) -> str:
        self.touched.append("path")
        return "/trap"

    def effective_candidates(self) -> list[object]:
        self.touched.append("effective_candidates")
        return []

    def effective_low_priority_routes(self) -> list[object]:
        self.touched.append("effective_low_priority_routes")
        return []

    def matches(self, scope: Any) -> tuple[Match, dict[str, Any]]:
        self.touched.append("matches")
        return Match.NONE, {}


def _endpoint_rows(client: TestClient) -> list[tuple[str, str, bool, bool]]:
    rows = client.get(f"{API}/endpoints").json()["endpoints"]
    return [(e["pattern"], e["rule"], e["secured"], e["bestEffort"]) for e in rows]


def test_custom_route_never_touched_by_any_get_lint_clean():
    trap = TrapRoute()
    app = FastAPI()
    app.router.routes.append(trap)
    client = client_for(app, mcp_enabled="ON")
    client.get(API)
    client.get(f"{API}/endpoints")
    _explain(client, "GET", "/trap")
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "get_fastapi_security"},
    }
    client.post(MCP, json=call)
    assert trap.touched == []


def test_custom_route_is_unknown_best_effort():
    app = FastAPI()
    app.router.routes.append(TrapRoute())
    assert [(rule, best) for _, rule, _, best in _endpoint_rows(client_for(app))] == [("unknown", True)]


def _starlette_sub_app() -> FastAPI:
    async def secret(request: Request) -> None:
        raise AssertionError("a mounted endpoint was called")

    sub = Starlette(routes=[Route("/secret", secret)], middleware=[Middleware(GZipMiddleware)])
    app = FastAPI()
    app.mount("/sub", sub)
    return app


def test_plain_starlette_subapp_routes_are_unknown_best_effort():
    assert _endpoint_rows(client_for(_starlette_sub_app())) == [("/sub/secret", "unknown", False, True)]


def test_plain_starlette_subapp_route_explained_as_unknown():
    body = _explain(client_for(_starlette_sub_app()), "GET", "/sub/secret").json()
    assert (body["rule"], body["bestEffort"]) == ("unknown", True)


def test_scheme_less_route_dependency_is_custom_but_not_secured():
    def verify_header() -> None:
        raise AssertionError("a dependency was called")

    app = FastAPI()
    app.get("/guarded", dependencies=[Depends(verify_header)])(lambda: "g")
    assert _endpoint_rows(client_for(app)) == [("/guarded", "custom", False, True)]


def test_explain_mount_captures_its_prefix():
    sub = FastAPI()
    sub.get("/a")(lambda: "a")
    app = FastAPI()
    app.mount("/api", sub)
    app.get("/api/b")(lambda: "b")  # Starlette never reaches it: the mount takes every /api/... path first
    assert _explain(client_for(app), "GET", "/api/b").json()["matched"] is False


def test_scheme_less_parameter_dependency_is_best_effort():
    def session_user(request: Request) -> str:
        raise AssertionError("a dependency was called")

    app = FastAPI()

    @app.get("/me")
    def me(user: str = Depends(session_user)) -> str:  # pyright: ignore[reportUnusedFunction]
        return user

    assert _endpoint_rows(client_for(app)) == [("/me", "unsecured", False, True)]


def test_optional_scheme_inside_enforcing_dependency_is_best_effort():
    optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

    def require_user(token: str | None = Depends(optional)) -> str:
        raise AssertionError("a dependency was called")

    app = FastAPI()

    @app.get("/me")
    def me(user: str = Depends(require_user)) -> str:  # pyright: ignore[reportUnusedFunction]
        return user

    assert _endpoint_rows(client_for(app)) == [("/me", "permitAll", False, True)]


def test_explain_empty_method_defaults_to_get():
    assert _explain(client_for(), "", "/health").json()["matched"] is True


def test_explain_empty_path_defaults_to_root():
    assert _explain(client_for(), "GET", "").status_code == 200
