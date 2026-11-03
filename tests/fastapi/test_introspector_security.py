"""``FastApiIntrospector.security_model()``: a static read of middleware and dependency trees, nothing called."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import fastapi.routing
import pytest
from fastapi.routing import APIRoute
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from fastapi.security.base import SecurityBase
from starlette.applications import Starlette
from starlette.authentication import AuthCredentials, AuthenticationBackend, SimpleUser
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import BaseRoute, Match, Mount

from fastapi import APIRouter, Depends, FastAPI, Security
from sharpit import install
from sharpit.engine.collectors.appsecurity import explain
from sharpit.fastapi.introspector import FastApiIntrospector

BEARER = "fastapi.security.oauth2.OAuth2PasswordBearer"
API_KEY = "fastapi.security.api_key.APIKeyHeader"


class TokenBackend(AuthenticationBackend):
    async def authenticate(self, conn: Any) -> tuple[AuthCredentials, SimpleUser] | None:
        pytest.fail("an authentication backend was called")


class TrapScheme(SecurityBase):
    """A user scheme whose call and ``auto_error`` property both fail the test if touched."""

    def __init__(self) -> None:
        self.model = None  # pyright: ignore[reportAttributeAccessIssue]
        self.scheme_name = "trap"

    @property
    def auto_error(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        pytest.fail("a user property was read")

    async def __call__(self) -> str:
        pytest.fail("a security scheme was called")


def _rows(app: object) -> list[tuple[str, tuple[str, ...], tuple[tuple[str, bool, tuple[str, ...]], ...]]]:
    model = FastApiIntrospector(app, "/sharpit").security_model()
    return [(r.path, r.methods, tuple((s.type_name, s.auto_error, s.scopes) for s in r.schemes)) for r in model.routes]


def test_get_never_calls_dependencies():
    def leaf() -> str:
        pytest.fail("a dependency was called")

    def middle(value: str = Depends(leaf), token: str = Depends(TrapScheme())) -> str:
        pytest.fail("a dependency was called")

    app = FastAPI()

    @app.get("/items")
    def items(user: str = Depends(middle)) -> str:  # pyright: ignore[reportUnusedFunction]
        pytest.fail("an endpoint was called")

    trap = f"{__name__}.TrapScheme"
    assert _rows(app) == [("/items", ("GET",), ((trap, True, ()),))]


def test_scheme_found_in_nested_dependency():
    oauth2 = OAuth2PasswordBearer(tokenUrl="token")

    def current_user(token: str = Depends(oauth2)) -> str:
        return token

    def active_user(user: str = Depends(current_user)) -> str:
        return user

    app = FastAPI()

    @app.get("/me")
    def me(user: str = Depends(active_user)) -> str:  # pyright: ignore[reportUnusedFunction]
        return user

    @app.get("/open")
    def open_(key: str | None = Depends(APIKeyHeader(name="x-key", auto_error=False))) -> str:  # pyright: ignore[reportUnusedFunction]
        return "ok"

    assert _rows(app) == [("/me", ("GET",), ((BEARER, True, ()),)), ("/open", ("GET",), ((API_KEY, False, ()),))]


def test_security_scopes_read():
    oauth2 = OAuth2PasswordBearer(tokenUrl="token", scopes={"admin": "", "read": ""})

    def current_user(token: str = Depends(oauth2)) -> str:
        return token

    app = FastAPI()

    @app.delete("/items/{item_id}")
    def delete(item_id: int, user: str = Security(current_user, scopes=["read", "admin"])) -> str:  # pyright: ignore[reportUnusedFunction]
        return user

    assert _rows(app) == [("/items/{item_id}", ("DELETE",), ((BEARER, True, ("admin", "read")),))]


def test_route_level_dependency_without_scheme_is_unknown():
    def verify_header() -> None:
        pytest.fail("a dependency was called")

    def get_db() -> str:
        return "db"

    router = APIRouter(dependencies=[Depends(verify_header)])

    @router.get("/guarded")
    def guarded(db: str = Depends(get_db)) -> str:  # pyright: ignore[reportUnusedFunction]
        return db

    app = FastAPI()
    app.include_router(router)

    @app.get("/plain")
    def plain(db: str = Depends(get_db)) -> str:  # pyright: ignore[reportUnusedFunction]
        return db

    model = FastApiIntrospector(app).security_model()
    assert [(r.path, r.unknown_dependency) for r in model.routes] == [("/guarded", True), ("/plain", False)]


def test_middleware_and_backend_types_read():
    app = FastAPI()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["internal.example.test"])
    app.add_middleware(CORSMiddleware, allow_origins=["https://example.test"])
    app.add_middleware(AuthenticationMiddleware, backend=TokenBackend())
    model = FastApiIntrospector(app).security_model()
    assert [c.middleware for c in model.chains] == [
        (
            "starlette.middleware.authentication.AuthenticationMiddleware",
            "starlette.middleware.cors.CORSMiddleware",
            "starlette.middleware.trustedhost.TrustedHostMiddleware",
        )
    ]
    assert model.auth_backends == (f"{__name__}.TokenBackend",)


def test_mounted_sub_app_middleware_is_its_own_chain():
    admin = FastAPI()
    admin.add_middleware(GZipMiddleware)

    @admin.get("/users")
    def users() -> str:  # pyright: ignore[reportUnusedFunction]
        return "u"

    app = FastAPI()
    app.mount("/admin", admin)

    @app.get("/")
    def root() -> str:  # pyright: ignore[reportUnusedFunction]
        return "r"

    model = FastApiIntrospector(app).security_model()
    assert [(c.prefix, c.middleware) for c in model.chains] == [
        (None, ()),
        ("/admin", ("starlette.middleware.gzip.GZipMiddleware",)),
    ]
    assert [(r.path, r.chain) for r in model.routes] == [("/admin/users", 1), ("/", 0)]


def test_sharpit_mount_hidden():
    # ported: SpringSecurityControllerTests.bootUiSecurityChainsAreHiddenByDefault
    app = FastAPI()

    @app.get("/items")
    def items() -> str:  # pyright: ignore[reportUnusedFunction]
        return "i"

    install(app, enabled="ON", show_banner=False, config_scan=False)
    model = FastApiIntrospector(app, "/sharpit").security_model()
    assert [r.path for r in model.routes] == ["/items"]
    assert [m for c in model.chains for m in c.middleware if m.startswith("sharpit.")] == []


def test_plain_starlette_app_not_present():
    # ported: SpringSecurityControllerTests.absentFilterChainProxyReturnsDisabledReport
    model = FastApiIntrospector(Starlette()).security_model()
    assert model.present is False
    assert model.limitations == ("FastAPI security dependencies are not available: the app is not a FastAPI app",)


class _DriftedDependant:
    @property
    def dependencies(self) -> list[object]:
        raise RuntimeError("internals moved")


def test_internals_drift_degrades():
    app = FastAPI()

    @app.get("/items")
    def items() -> str:  # pyright: ignore[reportUnusedFunction]
        return "i"

    route = next(r for r in app.routes if isinstance(r, APIRoute))
    route.dependant = _DriftedDependant()  # pyright: ignore[reportAttributeAccessIssue]
    model = FastApiIntrospector(app).security_model()
    assert [(r.path, r.opaque) for r in model.routes] == [("/items", True)]
    assert model.limitations == ("Route /items could not be inspected (RuntimeError).",)


CORS = "starlette.middleware.cors.CORSMiddleware"
GZIP = "starlette.middleware.gzip.GZipMiddleware"
TRUSTED = "starlette.middleware.trustedhost.TrustedHostMiddleware"


class TrapRoute(BaseRoute):
    """A custom route class: every property read and method call on it is recorded."""

    def __init__(self) -> None:
        self.touched: list[str] = []

    @property
    def path(self) -> str:
        self.touched.append("path")
        return "/trap"

    @property
    def endpoint(self) -> object:
        self.touched.append("endpoint")
        return None

    @property
    def methods(self) -> set[str]:
        self.touched.append("methods")
        return {"GET"}

    def effective_candidates(self) -> list[object]:
        self.touched.append("effective_candidates")
        return []

    def effective_low_priority_routes(self) -> list[object]:
        self.touched.append("effective_low_priority_routes")
        return []

    def matches(self, scope: Any) -> tuple[Match, dict[str, Any]]:
        self.touched.append("matches")
        return Match.NONE, {}


def test_custom_route_class_is_never_read_or_called():
    trap = TrapRoute()
    app = FastAPI()
    app.router.routes.append(trap)
    FastApiIntrospector(app).security_model()
    assert trap.touched == []


def test_custom_route_class_is_unknown():
    app = FastAPI()
    app.router.routes.append(TrapRoute())
    model = FastApiIntrospector(app).security_model()
    assert [(r.opaque, r.path_regex) for r in model.routes] == [(True, None)]


def test_route_chain_is_every_enclosing_stack():
    def endpoint() -> str:
        return "x"

    inner = FastAPI()
    inner.add_middleware(GZipMiddleware)
    inner.get("/x")(endpoint)
    outer = FastAPI()
    outer.add_middleware(TrustedHostMiddleware, allowed_hosts=["a.example.test"])
    outer.mount("/inner", inner)
    outer.get("/y")(endpoint)
    by_host = FastAPI()
    by_host.add_middleware(GZipMiddleware)
    by_host.get("/h")(endpoint)
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["https://example.test"])
    app.mount("/outer", outer)
    app.router.routes.append(Mount("/m", routes=[APIRoute("/z", endpoint)], middleware=[Middleware(GZipMiddleware)]))
    app.host("api.example.test", by_host)
    app.get("/outer/late")(endpoint)  # after the mount, at the top level: only the app's own stack wraps it
    model = FastApiIntrospector(app).security_model()
    stacks = {r.path: model.chains[r.chain].middleware for r in model.routes}
    assert stacks == {
        "/outer/inner/x": (CORS, TRUSTED, GZIP),
        "/outer/y": (CORS, TRUSTED),
        "/m/z": (CORS, GZIP),
        "/h": (CORS, GZIP),
        "/outer/late": (CORS,),
    }


def test_unexpandable_include_router_limitation_says_so():
    lazy = getattr(fastapi.routing, "_IncludedRouter", None)
    if lazy is None:
        pytest.skip("this FastAPI includes routers eagerly")
    router = APIRouter()
    router.get("/a")(lambda: "a")
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    included = next(r for r in app.router.routes if type(r) is lazy)
    included.original_router = object()  # pyright: ignore[reportAttributeAccessIssue]
    model = FastApiIntrospector(app).security_model()
    assert model.limitations == ("Included router at /v1 could not be expanded.",)


def _floor_shape(node: Any) -> SimpleNamespace:
    """A FastAPI 0.115 ``Dependant``: ``security_scopes`` holds every scope from the route down (parent + own)."""
    own = list(getattr(node, "own_oauth_scopes", None) or ())
    parent = list(getattr(node, "parent_oauth_scopes", None) or ())
    return SimpleNamespace(
        call=node.call,
        name=node.name,
        security_scopes=parent + own,
        dependencies=[_floor_shape(sub) for sub in node.dependencies],
    )


def _scoped_app() -> FastAPI:
    oauth2 = OAuth2PasswordBearer(tokenUrl="token", scopes={"read": "r", "admin": "a"})

    def user(token: str = Security(oauth2, scopes=["read"])) -> str:
        pytest.fail("a dependency was called")

    app = FastAPI()

    @app.get("/a")
    def a(u: str = Security(user, scopes=["admin"])) -> str:  # pyright: ignore[reportUnusedFunction]
        return u

    return app


def test_scopes_floor_and_newest_classify_same():
    newest = _rows(_scoped_app())
    floor_app = _scoped_app()
    for route in floor_app.routes:
        if type(route) is APIRoute:
            route.dependant = _floor_shape(route.dependant)  # pyright: ignore[reportAttributeAccessIssue]
    assert _rows(floor_app) == newest


def test_apiroute_in_plain_starlette_subapp_is_unknown():
    router = APIRouter()
    router.get("/secret")(lambda: "s")
    app = FastAPI()
    app.mount("/sub", Starlette(routes=router.routes, middleware=[Middleware(GZipMiddleware)]))
    model = FastApiIntrospector(app, "/sharpit").security_model()
    assert [(r.path, r.opaque) for r in model.routes] == [("/sub/secret", True)]


async def _legacy_asgi(scope: Any, receive: Any, send: Any) -> None:
    pytest.fail("a mounted application was called")


@pytest.mark.parametrize(
    "mount",
    [
        lambda: Mount("/legacy", app=_legacy_asgi, middleware=[Middleware(GZipMiddleware)]),
        lambda: Mount("/legacy", app=GZipMiddleware(Starlette())),
    ],
    ids=["mount-middleware", "wrapped-starlette-app"],
)
def test_opaque_sub_app_behind_middleware_is_unknown_on_its_own_chain(mount: Any):
    # council R-fastapi-security (Gemini, high): the wrapper's ``starlette.`` name made the mount framework code
    app = FastAPI()
    app.router.routes.append(mount())
    model = FastApiIntrospector(app, "/sharpit").security_model()
    rows = [(r.path, r.opaque, r.chain) for r in model.routes if r.path.startswith("/legacy")]
    assert rows == [("/legacy/{path}", True, 1)]
    assert "Mounted application at /legacy has no inspectable routes." in model.limitations


def test_opaque_mount_inside_sub_app_is_explained():
    admin = FastAPI()
    admin.get("/users")(lambda: "u")
    admin.mount("/legacy", _legacy_asgi)
    app = FastAPI()
    app.mount("/admin", admin)
    result = explain(FastApiIntrospector(app, "/sharpit").security_model(), "GET", "/admin/legacy/x", "/sharpit")
    assert result["pattern"] == "/admin/legacy/{path}"


class _PosingAsFastAPI:
    @property
    def __class__(self) -> type:  # pyright: ignore[reportIncompatibleMethodOverride]  # isinstance() reads it
        return FastAPI


def test_object_posing_as_fastapi_is_not_present():
    # council R-fastapi-security #5: isinstance() read a user ``__class__``
    assert FastApiIntrospector(_PosingAsFastAPI()).security_model().present is False


def test_route_two_mounts_deep_is_explained():
    # found in fix round 1: each mount's pattern is matched against the path its parent left, as Starlette does
    inner = FastAPI()
    inner.get("/c")(lambda: "c")
    middle = FastAPI()
    middle.mount("/b", inner)
    app = FastAPI()
    app.mount("/a", middle)
    result = explain(FastApiIntrospector(app, "/sharpit").security_model(), "GET", "/a/b/c", "/sharpit")
    assert result["pattern"] == "/a/b/c"
