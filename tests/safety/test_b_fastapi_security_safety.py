"""``fastapi-security`` reads have no side effects (lane B-fastapi-security; AGENTS.md safety model 4)."""

from __future__ import annotations

from fastapi.security import OAuth2PasswordBearer
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import Depends, FastAPI
from sharpit import install

PANEL = "fastapi-security"
GET_ROWS = [
    "/sharpit/api/fastapi-security",
    "/sharpit/api/fastapi-security/explain",
    "/sharpit/api/fastapi-security/endpoints",
]
WRITE_ROWS: list[tuple[str, str]] = []


def test_get_no_side_effects(no_side_effects: SideEffectGuard):
    calls: list[str] = []
    oauth2 = OAuth2PasswordBearer(tokenUrl="token")

    def current_user(token: str = Depends(oauth2)) -> str:
        calls.append("dependency")
        return token

    app = FastAPI()

    @app.get("/items")
    def items(user: str = Depends(current_user)) -> str:  # pyright: ignore[reportUnusedFunction]
        calls.append("endpoint")
        return user

    install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        no_side_effects.block_network()
        statuses = [
            client.get("/sharpit/api/fastapi-security").status_code,
            client.get("/sharpit/api/fastapi-security/endpoints").status_code,
            client.get("/sharpit/api/fastapi-security/explain", params={"path": "/items"}).status_code,
        ]
    assert statuses == [200, 200, 200]
    assert calls == []
    assert no_side_effects.violations == []
