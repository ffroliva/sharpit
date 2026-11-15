"""Use case: sharpit reaches production by accident (website/docs/safety.md, "If sharpit reaches production").

sharpit is a development and test tool. If an app ships with ``sharpit.install(app)`` still in it, the install must be
inert: every sharpit path answers 404 (reads and actions alike), the app's own routes are untouched, no SQL listener
is attached, no log handler is added and nothing is written. Two ways it lands there: no dev-server signal at all, and
a production profile even when the code forces ``enabled="ON"``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402
from tests.conftest import SideEffectGuard  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.panels import PANELS  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

# actions a scanner or a curious user could try against a forgotten install
ACTIONS = [
    "/sharpit/api/security/scan",
    "/sharpit/api/alembic/migrate",
    "/sharpit/api/cache/clear",
    "/sharpit/api/config/overrides",
]


def _shop(state_dir: str, **options: Any) -> tuple[FastAPI, Any]:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    app = FastAPI()

    @app.get("/orders/{order_id}")
    def get_order(order_id: int) -> dict[str, int]:
        with engine.connect() as conn:
            return {"order_id": conn.execute(sa.text("select :n"), {"n": order_id}).scalar_one()}

    install(app, show_banner=False, state_dir=state_dir, engines=[engine], **options)
    return app, engine


def _assert_inert(app: FastAPI, guard: SideEffectGuard, handlers_before: list[logging.Handler]) -> None:
    guard.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    assert client.get("/orders/7").json() == {"order_id": 7}  # the app itself is untouched
    reads = ["/sharpit", "/sharpit/", "/sharpit/api", "/sharpit/api/panels"]
    reads += [f"/sharpit/api{p.api_prefix}" for p in PANELS if p.api_prefix]
    for path in reads:
        assert client.get(path).status_code == 404, path
    for path in ACTIONS:
        assert client.post(path, json={}).status_code == 404, path
    assert not any(sqla.attached().values())  # no SQL listener, even after the app ran a query
    assert logging.getLogger().handlers == handlers_before  # no log handler added


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SHARPIT_ENABLED", "SHARPIT_PROFILES", "SHARPIT_ENABLED_PROFILES", "SHARPIT_DISABLED_PROFILES"):
        monkeypatch.delenv(name, raising=False)
    sqla.detach_all()


def test_installed_in_production_with_no_dev_signal_is_inert(no_side_effects: SideEffectGuard):
    before = list(logging.getLogger().handlers)
    app, _engine = _shop(str(no_side_effects.state_dir))
    _assert_inert(app, no_side_effects, before)


@pytest.fixture
def prod_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    # set before no_side_effects snapshots the environment, so the guard sees it as the starting state
    monkeypatch.setenv("SHARPIT_PROFILES", "prod")


@pytest.fixture
def reload_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    # the dev-server signal sharpit reads (fastapi/signals.py): this process looks started by `uvicorn --reload`
    monkeypatch.setattr(sys, "argv", ["uvicorn", "app:app", "--reload"])


def test_a_prod_profile_beats_the_dev_server_signal(
    prod_profile: None, reload_signal: None, no_side_effects: SideEffectGuard
):
    before = list(logging.getLogger().handlers)
    app, _engine = _shop(str(no_side_effects.state_dir))
    _assert_inert(app, no_side_effects, before)


def test_control_the_dev_server_signal_alone_turns_sharpit_on(reload_signal: None, tmp_path: Path):
    app, _engine = _shop(str(tmp_path))
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    assert client.get("/sharpit/api/panels").status_code == 200


# enabled="ON" hard-coded in the app overrides a prod profile on purpose (activation.py: SHARPIT_ENABLED=ON forces it
# on, with a warning). What still holds in production is the guard chain: only loopback callers get an answer.
def test_enabled_on_shipped_to_production_warns_and_answers_only_loopback(
    prod_profile: None, no_side_effects: SideEffectGuard, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        app, _engine = _shop(str(no_side_effects.state_dir), enabled="ON")
    assert any("forces it on" in r.getMessage() for r in caplog.records)
    no_side_effects.unblock_network()
    remote = TestClient(app, base_url="http://localhost", client=("203.0.113.7", 50000))
    assert remote.get("/orders/7").json() == {"order_id": 7}
    for path in ["/sharpit/api/panels", "/sharpit/api/config"]:
        response = remote.get(path)
        assert response.status_code == 403, path
        assert "restricted to loopback" in response.text
    for path in ACTIONS:
        assert remote.post(path, json={}).status_code == 403, path
