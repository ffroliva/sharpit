"""``FastApiIntrospector.security_model()``: a static read of middleware and dependency trees, nothing called."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from fastapi.security.base import SecurityBase
from starlette.applications import Starlette
from starlette.authentication import AuthCredentials, AuthenticationBackend, SimpleUser
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fastapi import APIRouter, Depends, FastAPI, Security
from sharpit import install
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
