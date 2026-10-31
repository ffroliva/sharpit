"""A dogfood FastAPI app with SQLAlchemy and Alembic.

Provides routes and database fixtures for sharpit's database, activity, exception,
and advisor panels. Run it from the repository root:
    uv run uvicorn --factory examples.fastapi_sqla.app:create_app --reload
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import SecretStr
from pydantic_settings import BaseSettings
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from starlette.requests import Request

from fastapi import BackgroundTasks, FastAPI
from sharpit import install

log = logging.getLogger("fastapi_sqla")
_sleeping_tasks: set[asyncio.Task[Any]] = set()


class Settings(BaseSettings):
    """Read from the environment: ``APP_NAME``, ``API_TOKEN``, ``DEBUG``."""

    app_name: str = "fastapi-sqla"
    api_token: SecretStr = SecretStr("dev-api-token")
    debug: bool = False


class HandledSampleError(Exception):
    """Custom exception handled by the app's exception handler."""


def user_health_check() -> str:
    """User-defined health check function returning UP."""
    return "UP"


def seed_data(engine: Engine) -> None:
    """Seed sample data if tables exist and are empty."""
    with engine.begin() as conn:
        inspector = inspect(conn)
        if inspector.has_table("owners"):
            count = conn.execute(text("SELECT count(*) FROM owners")).scalar()
            if count == 0:
                conn.execute(
                    text("INSERT INTO owners (id, name, email) VALUES (:id, :name, :email)"),
                    [
                        {"id": 1, "name": "Alice", "email": "alice@example.com"},
                        {"id": 2, "name": "Bob", "email": "bob@example.com"},
                        {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
                        {"id": 4, "name": "Dana", "email": "dana@example.com"},
                        {"id": 5, "name": "Evan", "email": "evan@example.com"},
                        {"id": 6, "name": "Frank", "email": "frank@example.com"},
                    ],
                )
        if inspector.has_table("pets"):
            pet_count = conn.execute(text("SELECT count(*) FROM pets")).scalar()
            if pet_count == 0:
                conn.execute(
                    text("INSERT INTO pets (id, owner_id, name, species) VALUES (:id, :owner_id, :name, :species)"),
                    [
                        {"id": 1, "owner_id": 1, "name": "Fido", "species": "dog"},
                        {"id": 2, "owner_id": 2, "name": "Whiskers", "species": "cat"},
                        {"id": 3, "owner_id": 3, "name": "Goldie", "species": "fish"},
                        {"id": 4, "owner_id": 4, "name": "Polly", "species": "parrot"},
                        {"id": 5, "owner_id": 5, "name": "Rex", "species": "dog"},
                        {"id": 6, "owner_id": 6, "name": "Milo", "species": "cat"},
                    ],
                )


def _background_sql_task(engine: Engine) -> None:
    """Run a query in the background after the response finishes."""
    time.sleep(0.01)
    with engine.connect() as conn:
        conn.execute(text("SELECT count(*) FROM owners"))


async def _sleep_coro() -> None:
    """A task that sleeps 30 seconds for the Threads panel."""
    with suppress(asyncio.CancelledError):
        await asyncio.sleep(30.0)


def create_app(db_dir: Path | None = None, **sharpit_options: Any) -> FastAPI:
    """Create the sample app with sync/async SQLite engines and sharpit installed."""
    settings = Settings()

    if db_dir is None:
        env_dir = os.environ.get("SHARPIT_SQLA_DB_DIR")
        resolved_db_dir = Path(env_dir).resolve() if env_dir else Path(__file__).resolve().parent
    else:
        resolved_db_dir = Path(db_dir).resolve()
    resolved_db_dir.mkdir(parents=True, exist_ok=True)
    db_file = (resolved_db_dir / "sample.db").resolve()

    sync_url = f"sqlite:///{db_file.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    sync_engine: Engine = create_engine(sync_url)
    async_engine: AsyncEngine = create_async_engine(async_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        log.info("fastapi_sqla starting")
        seed_data(sync_engine)
        yield
        for task in list(_sleeping_tasks):
            task.cancel()
        _sleeping_tasks.clear()
        await async_engine.dispose()
        sync_engine.dispose()
        log.info("fastapi_sqla stopped")

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.sync_engine = sync_engine
    app.state.async_engine = async_engine

    # App middleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Handled custom exception
    @app.exception_handler(HandledSampleError)
    async def handled_error_handler(_request: Request, _exc: HandledSampleError) -> Response:
        return JSONResponse(status_code=418, content={"handled": True, "detail": "custom handled error"})

    # Routes
    @app.get("/owners")
    def get_owners_list() -> list[dict[str, Any]]:
        with sync_engine.connect() as conn:
            if not inspect(conn).has_table("owners"):
                return []
            rows = conn.execute(text("SELECT id, name, email FROM owners ORDER BY id")).mappings().all()
            return [{"id": r["id"], "name": r["name"], "email": r["email"]} for r in rows]

    @app.get("/owners/n-plus-one")
    def owners_n_plus_one() -> list[dict[str, Any]]:
        with sync_engine.connect() as conn:
            if not inspect(conn).has_table("owners"):
                return []
            owners_rows = conn.execute(text("SELECT id, name, email FROM owners ORDER BY id")).mappings().all()
            has_pets = inspect(conn).has_table("pets")
            result: list[dict[str, Any]] = []
            for owner in owners_rows:
                owner_id = owner["id"]
                if has_pets:
                    pets_rows = (
                        conn.execute(
                            text("SELECT id, owner_id, name, species FROM pets WHERE owner_id = :owner_id"),
                            {"owner_id": owner_id},
                        )
                        .mappings()
                        .all()
                    )
                    pets = [{"id": p["id"], "name": p["name"], "species": p["species"]} for p in pets_rows]
                else:
                    conn.execute(text("SELECT id, name, email FROM owners WHERE id = :id"), {"id": owner_id})
                    pets = []
                result.append({"id": owner["id"], "name": owner["name"], "pets": pets})
            return result

    @app.get("/slow")
    def slow() -> dict[str, Any]:
        with sync_engine.connect() as conn:
            try:
                conn.connection.dbapi_connection.create_function("py_sleep", 1, time.sleep)  # type: ignore[attr-defined]
                conn.execute(text("SELECT py_sleep(0.3)"))
            except Exception:
                time.sleep(0.3)
        return {"slow": True, "duration": 0.3}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("unhandled error from /boom")

    @app.get("/handled")
    def handled() -> None:
        raise HandledSampleError("deliberate handled error")

    @app.get("/background")
    def background(background_tasks: BackgroundTasks) -> dict[str, bool]:
        background_tasks.add_task(_background_sql_task, sync_engine)
        return {"queued": True}

    @app.get("/warn")
    def warn() -> dict[str, Any]:
        log.warning("sample warning log message from /warn")
        return {"warned": True}

    @app.get("/sleeper")
    async def sleeper() -> dict[str, str]:
        task = asyncio.create_task(_sleep_coro(), name="sleeper")
        _sleeping_tasks.add(task)
        task.add_done_callback(_sleeping_tasks.discard)
        return {"status": "sleeping", "task": task.get_name()}

    # Deliberately poor REST design routes
    @app.get("/getOwners")
    def get_owners() -> list[dict[str, Any]]:
        return [{"id": 1, "name": "Alice"}]

    @app.post("/owners")
    def create_owner(owner: dict[str, Any]) -> dict[str, Any]:
        return owner

    alembic_ini = (Path(__file__).resolve().parent / "alembic.ini").resolve()
    app.state.sharpit = install(
        app,
        settings=[settings],
        engines=[sync_engine, async_engine],
        health_checks={"user": user_health_check},
        alembic_config=str(alembic_ini),
        **{"enabled": "ON", **sharpit_options},
    )
    return app
