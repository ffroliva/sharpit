"""Scheduled Tasks panel (W5b lane C): in-process schedulers read from module globals, never a remote store.

Celery and arq are not in the ``test`` extra, so their objects here are stand-ins registered in ``sys.modules`` with the
attribute shapes the C0 spike measured on celery 5 and arq 0.28 (``vars(app)["configured"]``/``["_conf"]`` as a
ChainMap, ``crontab._orig_*``, the ``CronJob`` dataclass fields). APScheduler 3 is real.
"""

from __future__ import annotations

import json
import sys
from collections import ChainMap, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from types import ModuleType
from typing import Any

import pytest
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi.testclient import TestClient

import sharpit
from conftest import golden
from fastapi import FastAPI
from sharpit.engine.collectors.scheduled import Discovery, build_report, discover

HOST = "w5bc_host_app"
API = "/sharpit/api/scheduled"
ABSENT = {"schedulingPresent": False, "total": 0, "tasks": []}
SECRETS = ("hunter2-kwarg-secret", "tok-arg-secret", "job-id-secret-xyz")


def hourly_report() -> None:
    """A scheduled function (module level, so its qualified name is stable)."""


def every_five() -> None:
    """A second scheduled function."""


def with_credentials(*_args: object, **_kwargs: object) -> None:
    """A job whose args and kwargs hold credentials."""


async def arq_tick(_ctx: object) -> None:
    """An arq cron coroutine."""


def _task(runnable: str | None, trigger: str = "CRON", expression: str | None = "0 0 * * * ?") -> dict[str, Any]:
    return {
        "runnable": runnable,
        "triggerType": trigger,
        "expression": expression,
        "initialDelayMs": None,
        "timeUnit": None,
    }


def _module(monkeypatch: pytest.MonkeyPatch, name: str = HOST, **globals_: object) -> ModuleType:
    module = ModuleType(name)
    vars(module).update(globals_)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _send(no_side_effects: Any, app: FastAPI, send: Callable[[TestClient], Any]) -> Any:
    """TestClient's portal opens a socketpair: the network opens for the client only (the safety sweep covers GETs)."""
    no_side_effects.unblock_network()
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            return send(client)
    finally:
        no_side_effects.block_network()
        no_side_effects.rebaseline()


def _install(no_side_effects: Any, **options: object) -> FastAPI:
    app = FastAPI()
    sharpit.install(
        app, enabled="ON", show_banner=False, app_package=HOST, state_dir=str(no_side_effects.state_dir), **options
    )
    return app


class _Exploding:
    """A lazy proxy: evaluating it (``__class__``, any attribute, ``__dict__``) raises, as Celery's ``current_app``."""

    def __getattribute__(self, name: str) -> Any:
        raise RuntimeError(f"lazy proxy evaluated: {name}")


class _RemoteStore:
    """A remote job store stand-in (SQLAlchemy, Redis): any attribute access, ``vars()`` included, raises."""

    def __getattribute__(self, name: str) -> Any:
        raise RuntimeError(f"remote job store touched: {name}")


# --- Celery / arq / APScheduler 4 stand-ins (shapes from the C0 spike) -----------------------------------------------


class _Celery:
    def __init__(self, main: str, configured: bool, conf: object) -> None:
        self.main = main
        self.configured = configured
        self._conf = conf


class _Crontab:
    def __init__(self, minute: object = "*", hour: object = "*") -> None:
        self._orig_minute = minute
        self._orig_hour = hour
        self._orig_day_of_month = "*"
        self._orig_month_of_year = "*"
        self._orig_day_of_week = "*"


class _Solar:
    """``celery.schedules.solar`` (needs ``ephem``): ``event``, ``lat`` and ``lon`` as instance attributes."""

    def __init__(self, event: str, lat: float, lon: float) -> None:
        self.event = event
        self.lat = lat
        self.lon = lon

    def __str__(self) -> str:
        raise AssertionError("str() called on a schedule")


@dataclass
class _CronJob:
    name: str
    coroutine: Any
    month: Any = None
    day: Any = None
    weekday: Any = None
    hour: Any = None
    minute: Any = None
    second: Any = 0
    microsecond: int = 123456
    run_at_startup: bool = False
    job_id: str | None = None


class _Aps4Scheduler:
    def __getattribute__(self, name: str) -> Any:
        raise RuntimeError(f"APScheduler 4 scheduler touched: {name}")


@pytest.fixture
def fake_celery(monkeypatch: pytest.MonkeyPatch) -> None:
    _module(monkeypatch, "celery.app.base", Celery=_Celery)
    _module(monkeypatch, "celery.schedules", crontab=_Crontab, solar=_Solar)


@pytest.fixture
def fake_arq(monkeypatch: pytest.MonkeyPatch) -> None:
    _module(monkeypatch, "arq.cron", CronJob=_CronJob)


# --- ported: the report wrapping ------------------------------------------------------------------------------------


# ported: ScheduledTasksServiceTests.reportIsAbsentWhenProviderIsNull
def test_report_is_absent_when_no_scheduler_is_found() -> None:
    assert build_report(None) == ABSENT


# ported: ScheduledTasksServiceTests.reportIsAbsentWhenProviderUnavailable
def test_report_is_absent_when_the_source_is_unavailable() -> None:
    assert build_report(Discovery(False, [_task("com.example.Job")], [])) == ABSENT


# ported: ScheduledTasksServiceTests.reportIsPresentWithZeroTasksWhenProviderAvailableButEmpty
def test_report_is_present_with_zero_tasks_when_a_scheduler_is_empty() -> None:
    assert build_report(Discovery(True, [], [])) == {"schedulingPresent": True, "total": 0, "tasks": []}


# ported: ScheduledTasksServiceTests.sortsByRunnableWithNullsLastAndReportsTotal
def test_sorts_by_runnable_with_nulls_last_and_reports_total() -> None:
    tasks = [_task("com.example.Zeta"), _task(None, "FIXED_RATE", "1000"), _task("com.example.Alpha", "FIXED_RATE")]

    report = build_report(Discovery(True, tasks, []))

    assert report["schedulingPresent"] is True
    assert report["total"] == 3
    assert [t["runnable"] for t in report["tasks"]] == ["com.example.Alpha", "com.example.Zeta", None]


# --- ported: the route ----------------------------------------------------------------------------------------------


# ported: ScheduledControllerTests.delegatesToServiceAndSerializesReport
def test_route_serializes_an_apscheduler_cron_job(no_side_effects: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = BackgroundScheduler()
    scheduler.add_job(every_five, "cron", minute="0/5")
    _module(monkeypatch, scheduler=scheduler)
    app = _install(no_side_effects)

    response = _send(no_side_effects, app, lambda client: client.get(API))

    assert response.status_code == 200
    body = response.json()
    assert body["schedulingPresent"] is True
    assert body["total"] == 1
    assert body["tasks"][0]["triggerType"] == "CRON"
    assert body["tasks"][0]["expression"] == "0 0/5 * * * *"
    assert body["tasks"][0]["runnable"] == f"{__name__}.every_five"


# ported: ScheduledControllerTests.serializesAbsentReport
def test_route_serializes_the_absent_report(no_side_effects: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _module(monkeypatch, settings={"debug": True})
    app = _install(no_side_effects)

    response = _send(no_side_effects, app, lambda client: client.get(API))

    assert response.status_code == 200
    assert response.json() == ABSENT


# --- safety ---------------------------------------------------------------------------------------------------------


def test_scheduled_never_reads_a_remote_jobstore(no_side_effects: Any) -> None:
    scheduler = BackgroundScheduler()
    memory = MemoryJobStore()
    donor = BackgroundScheduler()
    vars(memory)["_jobs"].append((donor.add_job(every_five, "interval", seconds=30), None))
    vars(scheduler)["_jobstores"].update({"default": memory, "remote": _RemoteStore()})
    host = ModuleType(HOST)
    vars(host)["scheduler"] = scheduler

    found = discover([host])

    assert [t["runnable"] for t in found.tasks] == [f"{__name__}.every_five"]
    assert any("remote" in reason for reason in found.limitations)
    assert any("_RemoteStore" in reason for reason in found.limitations)
    assert no_side_effects.violations == []


def test_scheduler_discovery_never_evaluates_a_lazy_proxy(
    no_side_effects: Any, fake_celery: None, fake_arq: None
) -> None:
    scheduler = BackgroundScheduler()
    scheduler.add_job(hourly_report, "cron", hour="*")
    host = ModuleType(HOST)
    vars(host).update(current_app=_Exploding(), scheduler=scheduler)

    found = discover([host])

    assert found.present is True
    assert [t["runnable"] for t in found.tasks] == [f"{__name__}.hourly_report"]
    assert no_side_effects.violations == []


def test_celery_unconfigured_app_is_not_loaded(fake_celery: None) -> None:
    pending = _Celery("proj", configured=False, conf=_Exploding())
    configured = _Celery(
        "ready",
        configured=True,
        conf=ChainMap(
            {"beat_schedule": {"hourly": {"task": "proj.tasks.hourly", "schedule": _Crontab(minute=0)}}},
            {"timezone": "UTC"},
        ),
    )
    host = ModuleType(HOST)
    vars(host).update(app=pending, ready=configured)

    found = discover([host])

    assert vars(pending)["configured"] is False
    assert any("proj" in reason for reason in found.limitations)
    assert found.tasks == [
        {"runnable": "proj.tasks.hourly", "triggerType": "CRON", "expression": "0 * * * *", "initialDelayMs": None,
         "timeUnit": None}
    ]  # fmt: skip


def test_celery_interval_schedules_are_fixed_rate(fake_celery: None) -> None:
    beat = {
        "ten": {"task": "proj.tasks.ten", "schedule": 10.0},
        "td": {"task": "proj.tasks.td", "schedule": timedelta(seconds=1.5)},
    }
    host = ModuleType(HOST)
    vars(host)["app"] = _Celery("proj", configured=True, conf=ChainMap({"beat_schedule": beat}))

    found = discover([host])

    assert sorted((t["runnable"], t["triggerType"], t["expression"], t["timeUnit"]) for t in found.tasks) == [
        ("proj.tasks.td", "FIXED_RATE", "1500", "ms"),
        ("proj.tasks.ten", "FIXED_RATE", "10000", "s"),
    ]


def test_arq_cron_jobs_from_worker_settings(fake_arq: None) -> None:
    class WorkerSettings:
        cron_jobs = [_CronJob("cron:arq_tick", arq_tick, hour={12, 9}, minute=0, job_id="job-id-secret-xyz")]

    host = ModuleType(HOST)
    vars(host)["WorkerSettings"] = WorkerSettings

    found = discover([host])

    assert found.present is True
    assert found.tasks == [_task(f"{__name__}.arq_tick", "CRON", "0 0 9,12 * * *")]


def test_apscheduler4_scheduler_is_partial_and_never_read(monkeypatch: pytest.MonkeyPatch) -> None:
    _module(monkeypatch, "apscheduler._schedulers.sync", Scheduler=_Aps4Scheduler)
    host = ModuleType(HOST)
    vars(host)["scheduler"] = _Aps4Scheduler()

    found = discover([host])

    assert found.tasks == []
    assert any("APScheduler 4" in reason for reason in found.limitations)


def test_scheduled_emits_function_name_only(no_side_effects: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        with_credentials, "interval", seconds=60, args=("tok-arg-secret",), kwargs={"password": "hunter2-kwarg-secret"},
        id="job-id-secret-xyz", name="tok-arg-secret",
    )  # fmt: skip
    _module(monkeypatch, scheduler=scheduler)
    app = _install(no_side_effects, mcp_enabled="ON")
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "get_scheduled_tasks", "arguments": {}},
    }

    bodies = _send(
        no_side_effects,
        app,
        lambda client: {
            "json": client.get(API).text,
            "mcp": json.dumps(client.post("/sharpit/api/mcp", json=call).json()),
            "cli": client.post("/sharpit/api/cli/tools/get_scheduled_tasks", json={}).text,
        },
    )

    for via, body in bodies.items():
        assert f"{__name__}.with_credentials" in body, via
        assert not [secret for secret in SECRETS if secret in body], via


def test_scheduled_reports_pending_jobs_of_unstarted_scheduler(no_side_effects: Any) -> None:
    scheduler = BackgroundScheduler()
    scheduler.add_job(hourly_report, "interval", seconds=90)
    scheduler.add_job(every_five, "interval", seconds=1.5)
    scheduler.add_job(every_five, "date", run_date="2030-01-01 00:00:00")
    host = ModuleType(HOST)
    vars(host)["scheduler"] = scheduler

    found = discover([host])

    assert sorted((t["runnable"], t["triggerType"], t["expression"], t["timeUnit"]) for t in found.tasks) == [
        (f"{__name__}.every_five", "FIXED_RATE", "1500", "ms"),
        (f"{__name__}.every_five", "ONE_SHOT", None, "s"),
        (f"{__name__}.hourly_report", "FIXED_RATE", "90000", "s"),
    ]
    assert scheduler.state == 0
    assert vars(scheduler)["_jobstores"] == {}
    assert no_side_effects.violations == []


def test_scheduled_golden_shape_23(no_side_effects: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = BackgroundScheduler()
    scheduler.add_job(hourly_report, "cron", minute=0)
    _module(monkeypatch, scheduler=scheduler)
    app = _install(no_side_effects)

    payload = _send(no_side_effects, app, lambda client: client.get(API).json())

    gold = golden("2.3.0/scheduled/captured")
    assert list(payload) == list(gold)
    assert list(payload["tasks"][0]) == list(gold["tasks"][0])


def test_scheduled_has_no_write_routes(no_side_effects: Any) -> None:
    app = _install(no_side_effects)

    routes = [r for r in _mounted_routes(app) if getattr(r, "path", "").endswith("/api/scheduled")]
    writes = [r for r in routes if set(getattr(r, "methods", None) or ()) - {"GET", "HEAD"}]

    assert len(routes) == 1
    assert writes == []


def _mounted_routes(app: FastAPI) -> list[Any]:
    found: list[Any] = []
    for route in app.routes:
        found.append(route)
        found.extend(getattr(getattr(route, "app", None), "routes", None) or ())
    return found


# --- council round 2 -------------------------------------------------------------------------------------------------


def _preconf_app(source: object) -> _Celery:
    """An app whose ``app.conf.beat_schedule = ...`` ran before its config loaded (celery 5's measured shape)."""
    app = _Celery("early", configured=False, conf=_Exploding())
    beat = {"nightly": {"task": "proj.tasks.nightly", "schedule": _Crontab(minute=30, hour=2)}}
    vars(app).update(_preconf={"deprecated_settings": set(), "beat_schedule": beat}, _config_source=source)
    vars(app)["_pending_defaults"] = deque()
    return app


def test_celery_preconf_beat_schedule_is_read_before_config_loads(fake_celery: None) -> None:
    app = _preconf_app(None)
    host = ModuleType(HOST)
    vars(host)["app"] = app

    found = discover([host])

    assert vars(app)["configured"] is False
    assert found.limitations == []
    assert found.present is True
    assert found.tasks == [_task("proj.tasks.nightly", "CRON", "30 2 * * *")]


def test_celery_preconf_is_not_read_when_a_config_source_is_pending(fake_celery: None) -> None:
    host = ModuleType(HOST)
    vars(host)["app"] = _preconf_app("proj.celeryconfig")

    found = discover([host])

    assert found.tasks == []
    assert any("early" in reason for reason in found.limitations)


def test_celery_solar_is_one_shot_with_its_description(fake_celery: None) -> None:
    beat = {"dawn": {"task": "proj.tasks.dawn", "schedule": _Solar("sunrise", 51.5, -0.1)}}
    host = ModuleType(HOST)
    vars(host)["app"] = _Celery("proj", configured=True, conf=ChainMap({"beat_schedule": beat}))

    found = discover([host])

    assert found.tasks == [_task("proj.tasks.dawn", "ONE_SHOT", "solar: sunrise at latitude 51.5, longitude: -0.1")]


@pytest.mark.parametrize(
    ("fields", "expression"),
    [
        ({"minute": "0/5", "hour": "9-17", "day_of_week": "mon-fri"}, "0 0/5 9-17 * * MON-FRI"),
        ({"day_of_week": "0-4/2"}, "0 0 0 * * MON-FRI/2"),
        ({"day_of_week": "*/2"}, "0 0 0 * * MON/2"),
        ({"day_of_week": "sun,wed"}, "0 0 0 * * SUN,WED"),
        ({"day": "last"}, "0 0 0 L * *"),
        ({"month": "jan-mar", "minute": "*/15"}, "0 */15 * * 1-3 *"),
    ],
)
def test_apscheduler_cron_is_spring_six_fields(fields: dict[str, str], expression: str) -> None:
    scheduler = BackgroundScheduler()
    scheduler.add_job(hourly_report, CronTrigger(**fields))  # pyright: ignore[reportArgumentType]
    host = ModuleType(HOST)
    vars(host)["scheduler"] = scheduler

    found = discover([host])

    assert found.tasks == [_task(f"{__name__}.hourly_report", "CRON", expression)]


@pytest.mark.parametrize("fields", [{"year": "2030"}, {"week": "3"}, {"day": "2nd fri"}])
def test_apscheduler_cron_without_a_spring_form_is_one_shot_null(fields: dict[str, str]) -> None:
    scheduler = BackgroundScheduler()
    scheduler.add_job(hourly_report, CronTrigger(**fields))  # pyright: ignore[reportArgumentType]
    host = ModuleType(HOST)
    vars(host)["scheduler"] = scheduler

    found = discover([host])

    assert found.tasks == [_task(f"{__name__}.hourly_report", "ONE_SHOT", None)]
