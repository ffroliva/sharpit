"""Alembic clean action (W8 M2): ``POST {api}/alembic/clean`` runs ``python -m alembic downgrade base`` in a child.

Contract: ``docs/superpowers/plans/2026-11-09-sharpit-0.6.0/W8-write-actions.md`` Task M2. Off by default
(``SHARPIT_ALEMBIC_CLEAN_ENABLED``); migrate and clean share one single-flight. Unit tests inject the runner; one test
runs the real Alembic against a temp SQLite project.
"""

from __future__ import annotations

import io
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.fastapi.test_alembic_migrate import (
    CONFIRM,
    KEYS,
    MIGRATE,
    NO_TARGET,
    REPORT,
    Spy,
    _client,
    _engine,
    _name,
    _project,
    _tables,
)

from sharpit.engine.collectors import alembic, alembic_cli

pytestmark = pytest.mark.needs_sqlalchemy
pytest.importorskip("sqlalchemy")

CLEAN = "/sharpit/api/alembic/clean"
DISABLED = "Alembic clean is disabled. Set SHARPIT_ALEMBIC_CLEAN_ENABLED=true to allow it."
ON = {"alembic_clean_enabled": True}


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    recorded = Spy()
    monkeypatch.setattr(alembic_cli, "run_alembic", recorded)
    return recorded


@pytest.fixture
def ini(tmp_path: Path) -> Path:
    return _project(tmp_path / "project")


def _clean(client: TestClient, body: Any = None, **kwargs: Any) -> Any:
    return client.post(CLEAN, json=body, **kwargs)


def _on(ini: Path, **options: Any) -> TestClient:
    return _client(ini, **ON, **options)


# ported: FlywayServiceTests.cleanChecksDisabledBeforeConfirmation
# ported: SpringFlywayProviderTests.cleanRequiresFlywayToAllowClean
# ported: FlywayControllerTests.cleanMapsForbiddenStatusOntoResponseEntity
def test_clean_checks_disabled_before_confirmation(ini: Path, spy: Spy):
    client = _client(ini)
    confirmed = _clean(client, {"beanName": _name(client), "confirm": True})
    assert (confirmed.status_code, confirmed.json()["status"]) == (403, "blocked")
    resp = _clean(client, {"beanName": _name(client)})  # no confirm: the 403 still comes first
    assert resp.status_code == 403
    assert resp.json()["status"] == "blocked"
    assert resp.json()["message"] == DISABLED
    assert resp.json()["beanName"] == _name(client)
    assert spy.calls == []


def test_alembic_clean_disabled_by_default_no_spawn(ini: Path, spy: Spy):
    client = _client(ini)
    for body in ({"confirm": True}, {"beanName": _name(client), "confirm": True}, None):
        assert _clean(client, body).status_code == 403
    assert spy.calls == []


def test_clean_unknown_name_is_404_even_when_disabled(ini: Path, spy: Spy):
    resp = _clean(_client(ini), {"beanName": "nope", "confirm": True})
    assert resp.status_code == 404
    assert resp.json()["message"] == NO_TARGET
    assert resp.json()["beanName"] is None
    assert spy.calls == []


def test_clean_with_several_databases_is_404(ini: Path, spy: Spy):
    client = _client(ini, [_engine(ini), _engine(ini, suffix="o.db")], **ON)
    resp = _clean(client, {"confirm": True})
    assert resp.status_code == 404
    assert resp.json()["message"] == NO_TARGET
    assert spy.calls == []


def test_clean_without_alembic_installed_is_404(ini: Path, spy: Spy, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(alembic, "_installed", lambda: False)
    resp = _clean(_on(ini), {"confirm": True})
    assert resp.status_code == 404
    assert resp.json()["status"] == "unavailable"
    assert spy.calls == []


# ported: FlywayServiceTests.cleanRequiresConfirmationWhenEnabled
def test_clean_requires_confirmation_when_enabled(ini: Path, spy: Spy):
    client = _on(ini)
    resp = _clean(client, {"beanName": _name(client)})
    assert resp.status_code == 400
    assert resp.json()["status"] == "blocked"
    assert resp.json()["message"] == CONFIRM
    assert spy.calls == []


@pytest.mark.parametrize("confirm", ["true", 1, "yes", [True], {"a": 1}, None, False])
def test_clean_confirm_must_be_json_true_exactly(ini: Path, spy: Spy, confirm: Any):
    client = _on(ini)
    assert _clean(client, {"beanName": _name(client), "confirm": confirm}).status_code == 400
    assert spy.calls == []


@pytest.mark.parametrize("name", [["x"], {"a": 1}])
def test_clean_structured_bean_name_is_400(ini: Path, spy: Spy, name: Any):
    assert _clean(_on(ini), {"beanName": name, "confirm": True}).status_code == 400
    assert spy.calls == []


# ported: FlywayServiceTests.cleanSuccessReturnsSchemas
# ported: SpringFlywayProviderTests.cleanRunsWhenFlywayAllowsItAndRequestIsConfirmed
# ported: FlywayControllerTests.cleanMapsSuccessStatusOntoResponseEntity
def test_clean_success_returns_the_cleaned_schema(ini: Path, spy: Spy):
    client = _on(ini)
    name = _name(client)
    resp = _clean(client, {"beanName": name, "confirm": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["message"] == f"Alembic cleaned schema(s) for {name}."
    assert body["beanName"] == name
    assert (body["schemasCleaned"], body["schemasDropped"]) == ([name], [])
    assert (body["migrationsExecuted"], body["migrationPath"], body["warnings"]) == (None, None, [])
    assert list(body) == KEYS
    assert len(spy.calls) == 1


def test_clean_blank_name_with_single_target_resolves_it(ini: Path, spy: Spy):
    client = _on(ini)
    resp = _clean(client, {"beanName": "  ", "confirm": True})
    assert resp.status_code == 200
    assert resp.json()["beanName"] == _name(client)


def test_clean_argv_is_downgrade_base(ini: Path, spy: Spy):
    client = _on(ini)
    _clean(client, {"beanName": _name(client), "confirm": True, "command": "upgrade", "ini": "evil.ini"})
    assert spy.calls == [([sys.executable, "-m", "alembic", "-c", str(ini), "downgrade", "base"], str(ini.parent))]


def test_clean_argv_is_shell_free_through_the_real_runner(ini: Path, monkeypatch: pytest.MonkeyPatch):
    seen: list[dict[str, Any]] = []

    class Proc:
        pid = None
        returncode = 0
        stdout = io.BytesIO(b"")

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def kill(self) -> None: ...

    def popen(argv: Any, **kwargs: Any) -> Proc:
        seen.append({"argv": argv, **kwargs})
        return Proc()

    monkeypatch.setattr(alembic_cli.subprocess, "Popen", popen)
    client = _on(ini)
    _clean(client, {"beanName": _name(client), "confirm": True})
    assert len(seen) == 1
    assert seen[0]["argv"] == [sys.executable, "-m", "alembic", "-c", str(ini), "downgrade", "base"]
    assert seen[0]["shell"] is False
    assert seen[0]["stdin"] is alembic_cli.subprocess.DEVNULL
    assert seen[0]["cwd"] == str(ini.parent)


def test_clean_output_masked_and_capped(ini: Path, spy: Spy):
    secret = "postgresql://u:s3cret@h/db"
    spy.result = alembic_cli.RunResult(1, f"{'x' * 6000}\nOperationalError: could not connect to {secret}\n", None)
    client = _on(ini)
    resp = _clean(client, {"beanName": _name(client), "confirm": True})
    assert (resp.status_code, resp.json()["status"]) == (500, "failed")
    assert "s3cret" not in resp.text
    assert "could not connect" in resp.json()["message"]
    assert len(resp.json()["message"].encode()) <= alembic.MAX_ERROR_BYTES
    assert resp.json()["schemasCleaned"] == []


def test_clean_timeout_reports_failed_and_releases_the_lock(ini: Path, spy: Spy):
    spy.result = alembic_cli.RunResult(None, "", "timeout")
    client = _on(ini)
    body = {"beanName": _name(client), "confirm": True}
    first = _clean(client, body)
    assert first.status_code == 500
    assert "did not finish" in first.json()["message"]
    spy.result = alembic_cli.RunResult(0, "", None)
    assert _clean(client, body).status_code == 200


def test_clean_runner_exception_is_masked_and_releases_the_lock(ini: Path, monkeypatch: pytest.MonkeyPatch):
    def boom(*_a: Any, **_k: Any) -> alembic_cli.RunResult:
        raise RuntimeError("postgresql://u:s3cret@h/db")

    monkeypatch.setattr(alembic_cli, "run_alembic", boom)
    client = _on(ini)
    body = {"beanName": _name(client), "confirm": True}
    resp = _clean(client, body)
    assert resp.status_code == 500
    assert "s3cret" not in resp.text
    monkeypatch.setattr(alembic_cli, "run_alembic", Spy())
    assert _clean(client, body).status_code == 200


# one flight for both actions -------------------------------------------------------------------------------------


def test_alembic_migrate_and_clean_share_one_flight(ini: Path, monkeypatch: pytest.MonkeyPatch):
    client = _on(ini)
    body = {"beanName": _name(client), "confirm": True}
    inner: list[Any] = []
    calls: list[list[str]] = []

    def reenter(argv: list[str], *_a: Any, **_k: Any) -> alembic_cli.RunResult:
        calls.append(argv)
        inner.append(_clean(client, body))  # the migrate still holds the flight
        return alembic_cli.RunResult(0, "", None)

    monkeypatch.setattr(alembic_cli, "run_alembic", reenter)
    first = client.post(MIGRATE, json=body)
    assert first.status_code == 200  # the migrate is unaffected
    assert inner[0].status_code == 409
    assert inner[0].json()["operation"] == "alembic-clean"
    assert inner[0].json()["activeOperation"] == "alembic-migrate"
    assert len(calls) == 1  # the clean never started a process
    assert _clean(client, body).status_code == 200  # released afterwards


def test_alembic_clean_blocks_a_migrate_while_it_runs(ini: Path, monkeypatch: pytest.MonkeyPatch):
    client = _on(ini)
    body = {"beanName": _name(client), "confirm": True}
    inner: list[Any] = []

    def reenter(*_a: Any, **_k: Any) -> alembic_cli.RunResult:
        inner.append(client.post(MIGRATE, json=body))
        return alembic_cli.RunResult(0, "", None)

    monkeypatch.setattr(alembic_cli, "run_alembic", reenter)
    assert _clean(client, body).status_code == 200
    assert inner[0].status_code == 409
    assert inner[0].json()["activeOperation"] == "alembic-clean"


# the report ------------------------------------------------------------------------------------------------------


def test_alembic_report_clean_flags_real(ini: Path):
    (off,) = _client(ini).get(REPORT).json()["databases"]
    assert (off["cleanEnabled"], off["cleanDisabledReason"]) == (False, DISABLED)
    (on,) = _on(ini).get(REPORT).json()["databases"]
    assert (on["cleanEnabled"], on["cleanDisabledReason"]) == (True, None)


def test_report_clean_gives_the_target_reason_when_the_action_would_404(ini: Path):
    client = _client(ini, [_engine(ini), _engine(ini, suffix="o.db")], **ON)
    client.post("/sharpit/api/alembic/refresh")
    databases = client.get(REPORT).json()["databases"]
    assert [d["cleanEnabled"] for d in databases] == [False, False]
    assert [d["cleanDisabledReason"] for d in databases] == [NO_TARGET, NO_TARGET]


def test_alembic_clean_get_never_runs_alembic(ini: Path, spy: Spy):
    client = _on(ini)
    client.get(REPORT)
    client.post("/sharpit/api/alembic/refresh")
    assert client.get(CLEAN).status_code == 405
    assert spy.calls == []


# refusals: every gate, with clean enabled, and the runner never ran ----------------------------------------------


def _refused(ini: Path, spy: Spy, make: Callable[[Path], TestClient], headers: dict[str, str] | None = None) -> Any:
    resp = make(ini).post(CLEAN, json={"confirm": True}, headers=headers or {})
    assert spy.calls == []
    return resp


def test_clean_inactive_is_404_and_spawns_nothing(ini: Path, spy: Spy):
    assert _refused(ini, spy, lambda i: _on(i, enabled="OFF")).status_code == 404


def test_clean_foreign_host_is_refused_and_spawns_nothing(ini: Path, spy: Spy):
    assert _refused(ini, spy, _on, {"Host": "evil.example"}).status_code == 403


def test_clean_cross_origin_is_refused_and_spawns_nothing(ini: Path, spy: Spy):
    assert _refused(ini, spy, _on, {"Origin": "http://evil.example"}).status_code == 403


def test_clean_remote_without_token_is_refused_and_spawns_nothing(ini: Path, spy: Spy):
    def remote(i: Path) -> TestClient:
        client = _on(i, allow_non_localhost=True, authentication_token="t0k3n")
        return TestClient(client.app, base_url="http://localhost", client=("10.0.0.5", 5), follow_redirects=False)

    assert _refused(ini, spy, remote).status_code == 401


def test_clean_panel_disabled_is_403_and_spawns_nothing(ini: Path, spy: Spy):
    resp = _refused(ini, spy, lambda i: _on(i, panels={"alembic": {"enabled": False}}))
    assert resp.status_code == 403
    assert resp.json()["reason"] == "Panel is disabled via SHARPIT_PANELS_ALEMBIC_ENABLED=false"


def test_alembic_clean_refused_read_only_no_spawn(ini: Path, spy: Spy):
    resp = _refused(ini, spy, lambda i: _on(i, read_only=True))
    assert resp.status_code == 403
    assert resp.json()["reason"] == "sharpit is read-only via SHARPIT_READ_ONLY=true"


def test_alembic_clean_refused_panel_read_only_no_spawn(ini: Path, spy: Spy):
    resp = _refused(ini, spy, lambda i: _on(i, panels={"alembic": {"read_only": True}}))
    assert resp.status_code == 403
    assert resp.json()["reason"] == "Panel is read-only via SHARPIT_PANELS_ALEMBIC_READ_ONLY=true"


def test_clean_has_no_mcp_or_cli_tool():
    from sharpit.engine.tools import TOOLS

    assert not [t for t in TOOLS if "clean" in t.name]


# the real Alembic, a temp SQLite project -------------------------------------------------------------------------


def test_clean_runs_the_real_alembic_downgrade_base(ini: Path):
    client = _on(ini)
    body = {"beanName": _name(client), "confirm": True}
    assert client.post(MIGRATE, json=body).status_code == 200
    assert {"t1", "t2"} <= _tables(ini)
    resp = _clean(client, body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"].startswith("Alembic cleaned schema(s) for ")
    assert not {"t1", "t2"} & _tables(ini)


# ported: FlywayServiceTests.cleanExceptionIs500
def test_clean_real_failure_is_500_with_the_output(tmp_path: Path):
    ini = _project(tmp_path / "broken")
    client = _on(ini)
    body = {"beanName": _name(client), "confirm": True}
    versions = ini.parent / "migrations" / "versions"
    assert client.post(MIGRATE, json=body).status_code == 200
    (versions / "b2_second.py").write_text("raise RuntimeError('boom from the revision')\n", encoding="utf-8")
    resp = _clean(client, body)
    assert resp.status_code == 500
    assert "boom from the revision" in resp.json()["message"]
