"""Middleware options (CORS origins, TrustedHost hosts, auth backend state) never reach ``fastapi-security`` output."""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.authentication import AuthenticationBackend
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fastapi import FastAPI
from sharpit import install

STRIPE_KEY = "sk_live_4eC39HqLyjWDarjtT1zdp7dc"
JWT_SECRET = "jwt-hs256-secret-0123456789abcdef"


class JwtBackend(AuthenticationBackend):
    def __init__(self, secret: str) -> None:
        self.secret = secret

    async def authenticate(self, conn: object) -> None:
        return None  # every request is anonymous


def test_middleware_options_never_appear():
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware, backend=JwtBackend(JWT_SECRET))
    app.add_middleware(CORSMiddleware, allow_origins=[f"https://x.example?token={STRIPE_KEY}"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", f"{STRIPE_KEY}.example"])
    install(app, enabled="ON", show_banner=False, config_scan=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    body = client.get("/sharpit/api/fastapi-security").text + client.get("/sharpit/api/fastapi-security/endpoints").text
    assert STRIPE_KEY not in body
    assert JWT_SECRET not in body
    assert f'"{__name__}.JwtBackend"' in body  # the backend's type is reported, never its state
