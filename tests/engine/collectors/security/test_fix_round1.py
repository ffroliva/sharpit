"""Fix round 1 (council and review findings): cases where the advisor called an insecure app fine."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.security import HTTPBearer
from pydantic import SecretStr
from starlette.datastructures import Secret
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import Depends, FastAPI

RuleRun = Callable[..., list[tuple[str, str]]]
InputsOf = Callable[..., Any]
QUIET_SECRET = "correct-horse-battery-staple-42"  # long, but no value detector flags it: only its name gives it away
SHORT_SECRET = "s3cr3t-signing-key"  # 18 characters


class SessionMiddleware:
    """Stands in for Starlette's (which needs ``itsdangerous``): same name and options."""

    def __init__(self, app: ASGIApp, secret_key: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


def _targets(found: list[tuple[str, str]]) -> list[str]:
    return [target for target, _ in found]


def _root_mounting(sub: Any, path: str = "/api") -> FastAPI:
    app = FastAPI()
    app.get("/items")(lambda: "items")
    app.router.routes.append(Mount(path, app=sub))
    return app


def _cors_sub() -> FastAPI:
    sub = FastAPI()
    sub.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
    sub.get("/orders")(lambda: "orders")
    return sub


# ---- 1. mounted sub-apps' middleware (council-claude #1) ------------------------------------------------------------


def test_mounted_sub_app_cors_with_credentials_is_flagged(run_rule: RuleRun):
    assert _targets(run_rule("SEC-CORS-002", _root_mounting(_cors_sub()))) == ["CORSMiddleware at /api"]


def test_mounted_sub_app_cors_message_names_the_mount(run_rule: RuleRun):
    found = run_rule("SEC-CORS-002", _root_mounting(_cors_sub()))
    assert [message for _, message in found] == [
        'CORSMiddleware on the app mounted at /api allows any origin ("*") with allow_credentials=True;'
        " the request Origin is reflected."
    ]


def test_mounted_trusted_host_does_not_cover_the_root_app(run_rule: RuleRun):
    sub = FastAPI()
    sub.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.example"])
    assert _targets(run_rule("SEC-FAPI-001", _root_mounting(sub))) == ["ASGI middleware stack"]


def test_mounted_trusted_host_allowing_any_host_is_flagged(run_rule: RuleRun):
    sub = FastAPI()
    sub.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
    app = _root_mounting(sub)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["app.example"])
    assert _targets(run_rule("SEC-FAPI-001", app)) == ["TrustedHostMiddleware at /api"]


def test_middleware_instance_wrapping_a_mount_is_a_limitation(inputs_of: InputsOf):
    wrapped = CORSMiddleware(FastAPI(), allow_origins=["*"], allow_credentials=True)
    facts = inputs_of(_root_mounting(wrapped, "/w")).facts
    assert "CORSMiddleware options on the app mounted at /w were not read." in facts.limitations


# ---- 2. SEC-SRC-001 literal shapes (council-claude #2) --------------------------------------------------------------


def _secrets_package(root: Path) -> Path:
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "wiring.py").write_text(
        f'app.add_middleware(SessionMiddleware, secret_key="{QUIET_SECRET}")\n'
        f'CONFIG = {{"password": "{QUIET_SECRET}", "label": "{QUIET_SECRET}"}}\n'
        f'def connect(host: str = "{QUIET_SECRET}", api_key: str = "{QUIET_SECRET}"): ...\n'
        f'def login(*, client_secret="{QUIET_SECRET}"): ...\n'
        "class Settings:\n"
        f'    jwt_secret: str = Field(default="{QUIET_SECRET}")\n'
        f'    title: str = Field(default="{QUIET_SECRET}")\n'
        f'    signing_key = Field("{QUIET_SECRET}")\n',
        encoding="utf-8",
    )
    return package


def test_literal_secret_as_keyword_dict_value_default_or_field(run_rule: RuleRun, tmp_path: Path):
    found = run_rule("SEC-SRC-001", FastAPI(), source=_secrets_package(tmp_path))
    assert _targets(found) == [f"shop/wiring.py:{line}" for line in (1, 2, 3, 4, 6, 8)]


def test_literal_secret_shapes_message_has_no_value(run_rule: RuleRun, tmp_path: Path):
    found = run_rule("SEC-SRC-001", FastAPI(), source=_secrets_package(tmp_path))
    assert found != []
    assert QUIET_SECRET not in repr(found)


# ---- 3. SEC-AUTHZ-001 with an ordinary parameter dependency (council-gemini Medium, council-claude #3) ---------------


def _db() -> str:
    return "session"


def test_unsecured_write_with_an_ordinary_dependency_is_flagged(run_rule: RuleRun):
    app = FastAPI()
    app.get("/me", dependencies=[Depends(HTTPBearer())])(lambda: "me")

    @app.post("/items")
    def create(db: str = Depends(_db)) -> str:
        return db

    assert _targets(run_rule("SEC-AUTHZ-001", app)) == ["POST /items"]


# ---- 4. minors (review-gemini-r1) -----------------------------------------------------------------------------------


def _with(cls: Any, **options: Any) -> FastAPI:
    app = FastAPI()
    app.add_middleware(cls, **options)
    app.get("/items")(lambda: "items")
    return app


def test_cors_origins_as_set_or_frozenset_are_read(run_rule: RuleRun):
    apps = [_with(CORSMiddleware, allow_origins={"*"}), _with(CORSMiddleware, allow_origins=frozenset({"*"}))]
    assert [_targets(run_rule("SEC-CORS-001", app)) for app in apps] == [["CORSMiddleware"], ["CORSMiddleware"]]


def test_short_session_secret_wrapped_in_secret_types_is_flagged(run_rule: RuleRun):
    apps = [
        _with(SessionMiddleware, secret_key=Secret(SHORT_SECRET)),
        _with(SessionMiddleware, secret_key=SecretStr(SHORT_SECRET)),
    ]
    assert [_targets(run_rule("SEC-SESSION-008", app)) for app in apps] == [
        ["SessionMiddleware"],
        ["SessionMiddleware"],
    ]


def test_long_session_secret_wrapped_in_secret_types_is_not_flagged(run_rule: RuleRun):
    apps = [
        _with(SessionMiddleware, secret_key=Secret("x" * 40)),
        _with(SessionMiddleware, secret_key=SecretStr("x" * 40)),
    ]
    assert [_targets(run_rule("SEC-SESSION-008", app)) for app in apps] == [[], []]


def test_bcrypt_zero_rounds_is_flagged(run_rule: RuleRun, tmp_path: Path):
    package = tmp_path / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "hashing.py").write_text(
        'zero = CryptContext(schemes=["bcrypt"], bcrypt__rounds=0)\nsalt = bcrypt.gensalt(rounds=0)\n',
        encoding="utf-8",
    )
    found = run_rule("SEC-AUTH-006", FastAPI(), source=package)
    assert _targets(found) == ["shop/hashing.py:1", "shop/hashing.py:2"]
