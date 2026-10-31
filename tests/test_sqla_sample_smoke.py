"""Smoke test for the examples/fastapi_sqla dogfood sample app."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.needs_sqlalchemy

pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")
pytest.importorskip("alembic")

from examples.fastapi_sqla.app import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_sqla_sample_smoke(tmp_path: Path) -> None:
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    ini_path = Path(__file__).resolve().parent.parent / "examples" / "fastapi_sqla" / "alembic.ini"

    # Run alembic upgrade head in a subprocess on tmp_path
    env = os.environ.copy()
    env["SHARPIT_SQLA_DB_DIR"] = str(db_dir)
    cmd = [sys.executable, "-m", "alembic", "-c", str(ini_path), "upgrade", "head"]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"alembic upgrade head failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    app = create_app(db_dir=db_dir)
    with TestClient(app, raise_server_exceptions=False) as client:
        # Hit /owners and /getOwners, asserting 200
        res_owners = client.get("/owners")
        assert res_owners.status_code == 200
        owners = res_owners.json()
        assert isinstance(owners, list)
        assert len(owners) >= 3

        res_get_owners = client.get("/getOwners")
        assert res_get_owners.status_code == 200

        # Verify other dogfood routes
        assert client.get("/owners/n-plus-one").status_code == 200
        assert client.post("/owners", json={"name": "Test"}).status_code == 200
        assert client.get("/handled").status_code == 418
        assert client.get("/boom").status_code == 500
        assert client.get("/warn").status_code == 200
        assert client.get("/sleeper").status_code == 200
        assert client.get("/background").status_code == 200
        assert client.get("/slow").status_code == 200


def test_sqla_sample_pending_revision(tmp_path: Path) -> None:
    db_dir = tmp_path / "db_rev2"
    db_dir.mkdir(parents=True, exist_ok=True)
    ini_path = Path(__file__).resolve().parent.parent / "examples" / "fastapi_sqla" / "alembic.ini"

    # Run alembic upgrade 0002 in a subprocess on tmp_path
    env = os.environ.copy()
    env["SHARPIT_SQLA_DB_DIR"] = str(db_dir)
    cmd = [sys.executable, "-m", "alembic", "-c", str(ini_path), "upgrade", "0002"]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"alembic upgrade 0002 failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    app = create_app(db_dir=db_dir)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        # Check alembic report through sharpit API
        res = client.post("/sharpit/api/alembic/refresh")
        assert res.status_code == 200
        data = res.json()
        assert data["alembicPresent"] is True
        assert data["total"] == 3
        assert data["heads"] == ["0003"]
        db_read = data["databases"][0]
        assert db_read["currentVersion"] == "0002"
        assert db_read["pending"] == 1
        assert db_read["applied"] == 2


def test_db_path_matches_alembic_env_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHARPIT_SQLA_DB_DIR", raising=False)
    ini_path = Path(__file__).resolve().parent.parent / "examples" / "fastapi_sqla" / "alembic.ini"
    expected_folder = ini_path.parent.resolve()
    expected_db = (expected_folder / "sample.db").resolve()

    app = create_app(show_banner=False)
    app_db = Path(app.state.sync_engine.url.database).resolve()

    from alembic.config import Config
    from alembic.runtime.environment import EnvironmentContext
    from alembic.script import ScriptDirectory
    from sqlalchemy.engine import make_url

    cfg = Config(str(ini_path))
    script = ScriptDirectory.from_config(cfg)
    env = EnvironmentContext(cfg, script, fn=lambda rev, ctx: [], as_sql=True)
    with env:
        script.run_env()
    alembic_url = cfg.get_main_option("sqlalchemy.url")
    assert alembic_url is not None
    alembic_db = Path(make_url(alembic_url).database).resolve()

    assert app_db == expected_db
    assert alembic_db == expected_db
    assert app_db == alembic_db


def test_db_path_matches_alembic_env_when_override_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom_dir = (tmp_path / "custom_db").resolve()
    custom_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SHARPIT_SQLA_DB_DIR", str(custom_dir))
    ini_path = Path(__file__).resolve().parent.parent / "examples" / "fastapi_sqla" / "alembic.ini"
    expected_db = (custom_dir / "sample.db").resolve()

    app = create_app(show_banner=False)
    app_db = Path(app.state.sync_engine.url.database).resolve()

    from alembic.config import Config
    from alembic.runtime.environment import EnvironmentContext
    from alembic.script import ScriptDirectory
    from sqlalchemy.engine import make_url

    cfg = Config(str(ini_path))
    script = ScriptDirectory.from_config(cfg)
    env = EnvironmentContext(cfg, script, fn=lambda rev, ctx: [], as_sql=True)
    with env:
        script.run_env()
    alembic_url = cfg.get_main_option("sqlalchemy.url")
    assert alembic_url is not None
    alembic_db = Path(make_url(alembic_url).database).resolve()

    assert app_db == expected_db
    assert alembic_db == expected_db
    assert app_db == alembic_db
