"""The GET corpus stays stable after an earlier test registered SQLAlchemy state."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fastapi import FastAPI

sa = pytest.importorskip("sqlalchemy")
pytestmark = pytest.mark.needs_sqlalchemy

from tests.fastapi.test_console_corpus_get import _assert_get_corpus  # noqa: E402

from sharpit import install  # noqa: E402
from sharpit.engine.sqla import attached, routed  # noqa: E402


def test_get_corpus_is_independent_of_earlier_sqlalchemy_state(no_side_effects, tmp_path: Path) -> None:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    app = FastAPI()

    @app.get("/seed-sql")
    def seed_sql() -> dict[str, int]:
        with engine.connect() as connection:
            return {"value": connection.execute(sa.text("select 42")).scalar_one()}

    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        state_dir=str(tmp_path / "earlier-app"),
        engines=[engine],
    )
    try:
        assert routed(handle.context) == (True, True)
        assert any(attached().values())
        assert handle.context.capture.engine_registry is not None
        assert handle.context.capture.engine_registry.has_engines()
        no_side_effects.unblock_network()
        try:
            with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
                assert client.get("/seed-sql").json() == {"value": 42}
        finally:
            no_side_effects.block_network()
        _assert_get_corpus(no_side_effects)
    finally:
        handle.uninstall_capture()
        engine.dispose()
