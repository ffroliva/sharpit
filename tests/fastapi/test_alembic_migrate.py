"""Alembic migrate action (W8 M1): ``POST {api}/alembic/migrate`` runs ``python -m alembic upgrade heads`` in a child.

Contract: ``docs/superpowers/plans/2026-11-09-sharpit-0.6.0/W8-write-actions.md`` Task M1. Unit tests inject the runner
(``alembic_cli.run_alembic``); one test runs the real Alembic against a temp SQLite project.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors import alembic_cli

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")

LOCAL = ("127.0.0.1", 50000)
MIGRATE = "/sharpit/api/alembic/migrate"
REPORT = "/sharpit/api/alembic/migrations"
CONFIRM = "Action requires confirm=true because it mutates the application database."
NO_TARGET = "No Alembic configuration matched the requested database."
KEYS = [
    "status",
    "message",
    "beanName",
    "migrationsExecuted",
    "schemasCleaned",
    "schemasDropped",
    "migrationPath",
    "warnings",
]
INI = """\
[alembic]
script_location = %(here)s/migrations
sqlalchemy.url = sqlite:///{db}

[loggers]
keys = root,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_alembic]
level = {level}
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %%(levelname)-5.5s [%%(name)s] %%(message)s
"""
ENV = """\
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
fileConfig(config.config_file_name)
section = config.get_section(config.config_ini_section)
engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
"""
REVISION = '''\
"""{doc}"""

from alembic import op

revision = "{rev}"
down_revision = {down}


def upgrade():
    op.execute("CREATE TABLE {table} (id INTEGER)")


def downgrade():
    op.execute("DROP TABLE {table}")
'''


class Spy:
    """Stands in for ``alembic_cli.run_alembic``: records every call, answers with a scripted result."""

    def __init__(self, result: alembic_cli.RunResult | None = None) -> None:
        self.calls: list[tuple[list[str], str]] = []
        self.result = result or alembic_cli.RunResult(0, "", None)

    def __call__(self, argv: list[str], cwd: str, *_a: Any, **_k: Any) -> alembic_cli.RunResult:
        self.calls.append((list(argv), cwd))
        return self.result


def _project(root: Path, *, level: str = "INFO") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    ini = root / "alembic.ini"
    ini.write_text(INI.format(db=(root / "app.db").as_posix(), level=level), encoding="utf-8")
    versions = root / "migrations" / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    (root / "migrations" / "env.py").write_text(ENV, encoding="utf-8")
    first = REVISION.format(doc="first", rev="a1", down="None", table="t1")
    second = REVISION.format(doc="second", rev="b2", down='"a1"', table="t2")
    (versions / "a1_first.py").write_text(first, encoding="utf-8")
    (versions / "b2_second.py").write_text(second, encoding="utf-8")
    return ini


def _engine(ini: Path, *, suffix: str = "app.db") -> Any:
    return sa.create_engine(f"sqlite:///{(ini.parent / suffix).as_posix()}")


def _client(ini: Path, engines: list[Any] | None = None, **options: Any) -> TestClient:
    app = FastAPI()
    settings = {"enabled": "ON", "show_banner": False, "alembic_config": str(ini), **options}
    install(app, engines=[_engine(ini)] if engines is None else engines, **settings)
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _name(client: TestClient) -> str:
    body = client.get(REPORT).json()
    return body["databases"][0]["name"]


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    recorded = Spy()
    monkeypatch.setattr(alembic_cli, "run_alembic", recorded)
    return recorded


@pytest.fixture
def ini(tmp_path: Path) -> Path:
    return _project(tmp_path / "project")


def _post(client: TestClient, body: Any = None, **kwargs: Any) -> Any:
    return client.post(MIGRATE, json=body, **kwargs)


# ported: FlywayServiceTests.migrateRequiresConfirmation
def test_migrate_requires_confirmation(ini: Path, spy: Spy):
    client = _client(ini)
    resp = _post(client, {"beanName": _name(client)})
    assert resp.status_code == 400
    assert resp.json()["status"] == "blocked"
    assert resp.json()["message"] == CONFIRM
    assert resp.json()["beanName"] == _name(client)
    assert spy.calls == []


@pytest.mark.parametrize("confirm", ["true", 1, "yes", [True], {"a": 1}, None, False])
def test_migrate_confirm_must_be_json_true_exactly(ini: Path, spy: Spy, confirm: Any):
    client = _client(ini)
    resp = _post(client, {"beanName": _name(client), "confirm": confirm})
    assert resp.status_code == 400
    assert spy.calls == []


# ported: FlywayServiceTests.migrateUnknownNameIsNotFound
def test_migrate_unknown_name_is_not_found(ini: Path, spy: Spy):
    resp = _post(_client(ini), {"beanName": "nope", "confirm": True})
    assert resp.status_code == 404
    assert resp.json()["status"] == "unavailable"
    assert resp.json()["message"] == NO_TARGET
    assert resp.json()["beanName"] is None
    assert spy.calls == []


# ported: FlywayServiceTests.migrateWithBlankNameAndMultipleTargetsIsNotFound
def test_migrate_blank_name_with_several_targets_is_not_found(ini: Path, spy: Spy):
    engines = [_engine(ini), _engine(ini, suffix="other.db")]
    resp = _post(_client(ini, engines), {"confirm": True})
    assert resp.status_code == 404
    assert resp.json()["status"] == "unavailable"
    assert spy.calls == []


# ported: FlywayServiceTests.migrateWithBlankNameAndSingleTargetResolvesIt
@pytest.mark.parametrize("name", [None, "", "   "])
def test_migrate_blank_name_with_single_target_resolves_it(ini: Path, spy: Spy, name: str | None):
    spy.result = alembic_cli.RunResult(0, "INFO [alembic.runtime.migration] Running upgrade  -> a1, first\n", None)
    client = _client(ini)
    resp = _post(client, {"beanName": name, "confirm": True})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert resp.json()["message"] == "Alembic applied 1 migration(s)."
    assert resp.json()["beanName"] == _name(client)
    assert len(spy.calls) == 1


# ported: FlywayServiceTests.migrateUpToDateMessageWhenZeroExecuted
def test_migrate_up_to_date_message_when_zero_executed(ini: Path, spy: Spy):
    spy.result = alembic_cli.RunResult(0, "INFO  [alembic.runtime.migration] Context impl SQLiteImpl.\n", None)
    client = _client(ini)
    resp = _post(client, {"beanName": _name(client), "confirm": True})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Alembic schema is already up to date."
    assert resp.json()["migrationsExecuted"] == 0


def test_migrate_executed_is_null_when_logging_hides_the_lines(ini: Path, spy: Spy):
    client = _client(ini)
    resp = _post(client, {"beanName": _name(client), "confirm": True})
    assert resp.status_code == 200
    assert resp.json()["migrationsExecuted"] is None


# ported: FlywayServiceTests.migrateOnNullProviderIsNotFound
def test_migrate_without_alembic_config_is_not_found(tmp_path: Path, spy: Spy):
    ini = tmp_path / "missing" / "alembic.ini"
    resp = _post(_client(ini), {"confirm": True})
    assert resp.status_code == 404
    assert resp.json()["message"] == NO_TARGET
    assert spy.calls == []


# ported: FlywayControllerTests.migrateMapsBlockedStatusOntoResponseEntity
def test_migrate_blocked_status_maps_onto_the_response(ini: Path, spy: Spy):
    client = _client(ini)
    resp = _post(client, {"beanName": _name(client)})
    assert (resp.status_code, resp.json()["status"]) == (400, "blocked")


# ported: FlywayControllerTests.migrateMapsSuccessStatusOntoResponseEntity
def test_migrate_success_status_maps_onto_the_response(ini: Path, spy: Spy):
    client = _client(ini)
    resp = _post(client, {"beanName": _name(client), "confirm": True})
    assert (resp.status_code, resp.json()["status"]) == (200, "success")


def test_migrate_result_emits_every_key(ini: Path, spy: Spy):
    client = _client(ini)
    ok = _post(client, {"beanName": _name(client), "confirm": True}).json()
    refused = _post(client, {"beanName": "nope"}).json()
    assert list(ok) == KEYS
    assert list(refused) == KEYS
    assert (ok["schemasCleaned"], ok["schemasDropped"], ok["warnings"], ok["migrationPath"]) == ([], [], [], None)


@pytest.mark.parametrize("raw", [b"[1]", b"not json", b'"x"'])
def test_migrate_body_must_be_a_json_object(ini: Path, spy: Spy, raw: bytes):
    resp = _client(ini).post(MIGRATE, content=raw, headers={"content-type": "application/json"})
    assert resp.status_code == 400
    assert spy.calls == []


def test_migrate_empty_body_needs_confirmation(ini: Path, spy: Spy):
    resp = _client(ini).post(MIGRATE)
    assert resp.status_code == 400
    assert resp.json()["message"] == CONFIRM
    assert spy.calls == []


def test_alembic_argv_is_fixed_and_shell_free(ini: Path, monkeypatch: pytest.MonkeyPatch):
    seen: list[dict[str, Any]] = []

    class Proc:
        pid = 0
        returncode = 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, None]:
            return b"", None

        def poll(self) -> int:
            return 0

        def kill(self) -> None: ...

    def popen(argv: Any, **kwargs: Any) -> Proc:
        seen.append({"argv": argv, **kwargs})
        return Proc()

    monkeypatch.setattr(alembic_cli.subprocess, "Popen", popen)
    client = _client(ini)
    name = _name(client)
    _post(client, {"beanName": name, "confirm": True})
    (call,) = seen
    assert call["argv"] == [sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "heads"]
    assert call["shell"] is False
    assert call["stdin"] is alembic_cli.subprocess.DEVNULL
    assert call["cwd"] == str(ini.parent)
    assert name not in call["argv"]


def test_alembic_request_text_never_reaches_argv(ini: Path, spy: Spy):
    client = _client(ini)
    hostile = "x; rm -rf / --config evil.ini"
    resp = _post(client, {"beanName": hostile, "confirm": True, "command": "downgrade", "ini": "evil.ini"})
    assert resp.status_code == 404
    assert spy.calls == []
    _post(client, {"beanName": _name(client), "confirm": True, "command": "downgrade", "ini": "evil.ini"})
    (argv, _cwd) = spy.calls[0]
    assert argv[-2:] == ["upgrade", "heads"]
    assert "evil.ini" not in argv


def test_alembic_output_masked_and_capped(ini: Path, spy: Spy):
    secret = "postgresql://u:s3cret@h/db"
    noise = "x" * 6000
    spy.result = alembic_cli.RunResult(1, f"{noise}\nOperationalError: could not connect to {secret}\n", None)
    client = _client(ini)
    resp = _post(client, {"beanName": _name(client), "confirm": True})
    assert resp.status_code == 500
    assert resp.json()["status"] == "failed"
    assert "s3cret" not in resp.text
    assert "could not connect" in resp.json()["message"]
    assert len(resp.json()["message"].encode()) <= alembic_cli.MAX_ERROR_BYTES


def test_alembic_failure_without_output_names_the_exit_code(ini: Path, spy: Spy):
    spy.result = alembic_cli.RunResult(3, "", None)
    client = _client(ini)
    resp = _post(client, {"beanName": _name(client), "confirm": True})
    assert (resp.status_code, resp.json()["status"]) == (500, "failed")
    assert resp.json()["message"] == "Alembic failed with exit code 3."


def test_alembic_timeout_reports_failed_and_releases_the_lock(ini: Path, spy: Spy):
    spy.result = alembic_cli.RunResult(None, "", "timeout")
    client = _client(ini)
    body = {"beanName": _name(client), "confirm": True}
    first = _post(client, body)
    assert first.status_code == 500
    assert "did not finish" in first.json()["message"]
    spy.result = alembic_cli.RunResult(0, "", None)
    assert _post(client, body).status_code == 200  # the lock was released


def test_alembic_oserror_is_masked_and_releases_the_lock(ini: Path, spy: Spy):
    spy.result = alembic_cli.RunResult(None, "OSError: cannot start postgresql://u:s3cret@h/db", "error")
    client = _client(ini)
    body = {"beanName": _name(client), "confirm": True}
    resp = _post(client, body)
    assert resp.status_code == 500
    assert "s3cret" not in resp.text
    spy.result = alembic_cli.RunResult(0, "", None)
    assert _post(client, body).status_code == 200


def test_alembic_runner_exception_releases_the_lock(ini: Path, monkeypatch: pytest.MonkeyPatch):
    def boom(*_a: Any, **_k: Any) -> alembic_cli.RunResult:
        raise RuntimeError("postgresql://u:s3cret@h/db")

    monkeypatch.setattr(alembic_cli, "run_alembic", boom)
    client = _client(ini)
    body = {"beanName": _name(client), "confirm": True}
    resp = _post(client, body)
    assert resp.status_code == 500
    assert "s3cret" not in resp.text
    monkeypatch.setattr(alembic_cli, "run_alembic", Spy())
    assert _post(client, body).status_code == 200


def test_alembic_second_call_while_running_is_409(ini: Path, monkeypatch: pytest.MonkeyPatch):
    client = _client(ini)
    body = {"beanName": _name(client), "confirm": True}
    inner: list[Any] = []

    def reenter(*_a: Any, **_k: Any) -> alembic_cli.RunResult:
        inner.append(_post(client, body))  # the first call still holds the flight
        return alembic_cli.RunResult(0, "", None)

    monkeypatch.setattr(alembic_cli, "run_alembic", reenter)
    assert _post(client, body).status_code == 200
    assert inner[0].status_code == 409
    assert inner[0].json()["operation"] == "alembic-migrate"


def test_alembic_report_flags_are_real(ini: Path):
    client = _client(ini)
    (database,) = client.get(REPORT).json()["databases"]
    assert database["migrateEnabled"] is True
    assert database["migrateDisabledReason"] is None


def test_alembic_report_flags_off_without_a_config(tmp_path: Path):
    client = _client(tmp_path / "none" / "alembic.ini")
    assert client.get(REPORT).json()["databases"] == []


def test_alembic_get_never_runs_alembic(ini: Path, spy: Spy):
    client = _client(ini)
    client.get(REPORT)
    client.post("/sharpit/api/alembic/refresh")
    assert spy.calls == []


# refusals: every gate, and the runner never ran ------------------------------------------------------------------


def _refused(ini: Path, spy: Spy, make: Callable[[Path], TestClient], headers: dict[str, str] | None = None) -> Any:
    client = make(ini)
    resp = client.post(MIGRATE, json={"confirm": True}, headers=headers or {})
    assert spy.calls == []
    return resp


def test_migrate_inactive_is_404_and_spawns_nothing(ini: Path, spy: Spy):
    resp = _refused(ini, spy, lambda i: _client(i, enabled="OFF"))
    assert resp.status_code == 404


def test_migrate_foreign_host_is_refused_and_spawns_nothing(ini: Path, spy: Spy):
    resp = _refused(ini, spy, _client, {"Host": "evil.example"})
    assert resp.status_code == 403


def test_migrate_cross_origin_is_refused_and_spawns_nothing(ini: Path, spy: Spy):
    resp = _refused(ini, spy, _client, {"Origin": "http://evil.example"})
    assert resp.status_code == 403


def test_migrate_remote_without_token_is_refused_and_spawns_nothing(ini: Path, spy: Spy):
    def remote(i: Path) -> TestClient:
        client = _client(i, allow_non_localhost=True, authentication_token="t0k3n")
        return TestClient(client.app, base_url="http://localhost", client=("10.0.0.5", 5), follow_redirects=False)

    assert _refused(ini, spy, remote).status_code == 401


def test_migrate_panel_disabled_is_403_and_spawns_nothing(ini: Path, spy: Spy):
    resp = _refused(ini, spy, lambda i: _client(i, panels={"alembic": {"enabled": False}}))
    assert resp.status_code == 403
    assert resp.json()["reason"] == "Panel is disabled via SHARPIT_PANELS_ALEMBIC_ENABLED=false"


def test_alembic_migrate_refused_read_only_no_spawn(ini: Path, spy: Spy):
    resp = _refused(ini, spy, lambda i: _client(i, read_only=True))
    assert resp.status_code == 403
    assert resp.json()["reason"] == "sharpit is read-only via SHARPIT_READ_ONLY=true"


def test_alembic_migrate_refused_panel_read_only_no_spawn(ini: Path, spy: Spy):
    resp = _refused(ini, spy, lambda i: _client(i, panels={"alembic": {"read_only": True}}))
    assert resp.status_code == 403
    assert resp.json()["reason"] == "Panel is read-only via SHARPIT_PANELS_ALEMBIC_READ_ONLY=true"


def test_migrate_wrong_method_never_runs(ini: Path, spy: Spy):
    client = _client(ini)
    assert client.get(MIGRATE).status_code in (404, 405)
    assert spy.calls == []


def test_migrate_has_no_mcp_or_cli_tool(ini: Path):
    from sharpit.engine.tools import TOOLS

    assert not [t for t in TOOLS if "migrate" in t.name]


# the real Alembic, a temp SQLite project -------------------------------------------------------------------------


def _tables(ini: Path) -> set[str]:
    with _engine(ini).connect() as conn:
        return {r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_migrate_runs_the_real_alembic_against_a_temp_sqlite(ini: Path):
    client = _client(ini)
    body = {"beanName": _name(client), "confirm": True}
    first = _post(client, body)
    assert first.status_code == 200, first.text
    assert first.json()["message"] == "Alembic applied 2 migration(s)."
    assert first.json()["migrationsExecuted"] == 2
    assert {"t1", "t2", "alembic_version"} <= _tables(ini)
    again = _post(client, body)
    assert again.status_code == 200
    assert again.json()["message"] == "Alembic schema is already up to date."


def test_migrate_real_failure_is_500_with_the_output(tmp_path: Path):
    ini = _project(tmp_path / "broken")
    (ini.parent / "migrations" / "versions" / "b2_second.py").write_text(
        REVISION.format(doc="second", rev="b2", down='"a1"', table="t1"), encoding="utf-8"
    )  # CREATE TABLE t1 again: fails
    client = _client(ini)
    resp = _post(client, {"beanName": _name(client), "confirm": True})
    assert resp.status_code == 500
    assert resp.json()["status"] == "failed"
    assert "already exists" in resp.json()["message"]


def test_migrate_real_alembic_logging_off_gives_null_count(tmp_path: Path):
    ini = _project(tmp_path / "quiet", level="WARNING")
    client = _client(ini)
    resp = _post(client, {"beanName": _name(client), "confirm": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["migrationsExecuted"] is None
