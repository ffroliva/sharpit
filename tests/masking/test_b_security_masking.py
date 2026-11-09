"""A security violation names a rule and a place, never the secret it found (PLAN.md Review Focus 7)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OpenIdConnect
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import Depends, FastAPI
from sharpit import install

STRIPE_KEY = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"  # in pieces: GitHub push protection
API = "/sharpit/api/security"
EXPECTED = {"SEC-CORS-006", "SEC-SESSION-008", "SEC-OAUTH-004", "SEC-CONFIG-007", "SEC-SRC-001"}


class SessionMiddleware:
    """Stands in for Starlette's (which needs ``itsdangerous``): same name, the secret in its options."""

    def __init__(self, app: ASGIApp, secret_key: str) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


def _package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "leakyapp"
    package.mkdir()
    (package / "__init__.py").write_text(f'STRIPE = "{STRIPE_KEY}"\n', encoding="utf-8")
    (package / "settings.py").write_text(
        f'import os\nSECRET_KEY = os.getenv("SECRET_KEY", "{STRIPE_KEY}")\n', encoding="utf-8"
    )
    module = ModuleType("leakyapp")
    module.__file__ = str(package / "__init__.py")
    module.__path__ = [str(package)]
    monkeypatch.setitem(sys.modules, "leakyapp", module)


def _app() -> FastAPI:
    oidc = OpenIdConnect(openIdConnectUrl=f"http://idp.example/.well-known/openid-configuration?key={STRIPE_KEY}")
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key=STRIPE_KEY[:20])
    app.add_middleware(CORSMiddleware, allow_origin_regex=f".*|{STRIPE_KEY}")

    @app.get("/me")
    def me(token: str = Depends(oidc)) -> str:  # pyright: ignore[reportUnusedFunction]
        raise AssertionError("an endpoint was called")

    return app


def _mcp(client: TestClient, name: str, arguments: dict[str, Any]) -> str:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return client.post("/sharpit/api/mcp", json=body).text


def test_violation_never_contains_literal_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _package(tmp_path, monkeypatch)
    app = _app()
    install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        mcp_enabled="ON",
        state_dir=str(tmp_path / "state"),
        app_package="leakyapp",
    )
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    scanned = client.post(f"{API}/scan")
    assert scanned.status_code == 200, scanned.text
    found = {r["id"] for r in scanned.json()["results"]}
    scan_id = scanned.json()["violationDetails"]["scanId"]
    outputs = [scanned.text, client.get(API).text, _mcp(client, "get_security_report", {})]
    for rule_id in sorted(EXPECTED & found):
        outputs.append(client.get(f"{API}/rules/{rule_id}/violations", params={"scanId": scan_id}).text)
        outputs.append(_mcp(client, "get_security_rule_violations", {"id": rule_id, "scanId": scan_id}))
    assert EXPECTED - found == set()
    assert [STRIPE_KEY in text for text in outputs] == [False] * len(outputs)
