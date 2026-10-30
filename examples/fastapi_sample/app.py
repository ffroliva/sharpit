"""A small FastAPI app that gives every sharpit panel something to show.

Run it from the repository root: ``uv run uvicorn --factory examples.fastapi_sample.app:create_app --reload`` and
open http://127.0.0.1:8000/sharpit/. Nothing here touches the network at import or in ``create_app()``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import SecretStr
from pydantic_settings import BaseSettings
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import Depends, FastAPI, WebSocket
from sharpit import install

STATIC = Path(__file__).resolve().parent / "static"
log = logging.getLogger("fastapi_sample")


class Settings(BaseSettings):
    """Read from the environment: ``APP_NAME``, ``DATABASE_URL``, ``API_TOKEN``, ``GREETING``, ``DEBUG``."""

    app_name: str = "fastapi-sample"
    database_url: str = "sqlite:///./sample.db"
    api_token: SecretStr = SecretStr("dev-api-token")
    greeting: SecretStr = SecretStr("hello")  # a harmless name: only the SecretStr type marks it secret
    debug: bool = False


class SignedSessionMiddleware:
    """Stand-in for Starlette's ``SessionMiddleware`` (which needs ``itsdangerous``): a secret constructor kwarg."""

    def __init__(self, app: ASGIApp, secret_key: str) -> None:
        self.app = app
        self.secret_key = secret_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


def get_settings() -> Settings:
    return Settings()


def get_database(settings: Annotated[Settings, Depends(get_settings)]) -> str:
    return settings.database_url


def get_owner_repository(database: Annotated[str, Depends(get_database)]) -> dict[str, str]:
    return {"database": database}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    log.info("fastapi-sample starting")
    yield


def create_app(**sharpit_options: Any) -> FastAPI:
    """The sample app with sharpit installed; ``sharpit_options`` go to ``install()`` (tests pass a state dir)."""
    settings = Settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(SignedSessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-session-secret"))

    @app.get("/owners")
    def owners(repository: Annotated[dict[str, str], Depends(get_owner_repository)]) -> dict[str, Any]:
        return {"owners": [], "jwtIssuer": os.environ.get("JWT_ISSUER", "fastapi-sample"), **repository}

    @app.post("/owners")
    def create_owner(owner: dict[str, str]) -> dict[str, str]:
        return owner

    @app.get("/token-info")
    def token_info() -> dict[str, int]:
        return {"length": len(os.getenv("JWT_SECRET", "dev-only-jwt-secret"))}

    @app.websocket("/ws/echo")
    async def echo(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text(await websocket.receive_text())
        await websocket.close()

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/{path:path}")
    def spa(path: str) -> dict[str, str]:
        return {"page": path}

    # A dev-only sample, so sharpit is always on here (SHARPIT_ENABLED=OFF still wins).
    app.state.sharpit = install(app, settings=[settings], **{"enabled": "ON", **sharpit_options})
    return app
