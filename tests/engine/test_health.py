"""Health (F8, spec §7.8): status aggregation, user checks, engine pings, masking and the cached GET.

``# ported:`` cites BootUI ``HealthServiceTests`` (the guidance and DISABLED root) and Spring Boot's
``SimpleStatusAggregator`` default order; the rest is derived. Engine cases import SQLAlchemy lazily and carry the
``needs_sqlalchemy`` mark one by one, so the user-check cases still run in the no-sqlalchemy job.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import textwrap
import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from conftest import golden
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.health import (
    DISABLED_REASON,
    ENGINES_ONLY_REASON,
    NEVER_CHECKED,
    HealthService,
    _with_guidance,  # pyright: ignore[reportPrivateUsage]
    aggregate,
    health_service,
    node,
)
from sharpit.engine.masking import MASK
from sharpit.fastapi.adapter import SharpitHandle

SECRET = "hunter2"
DSN = f"postgresql://app:{SECRET}@db.internal/app"
_HANDLES: list[SharpitHandle] = []


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _service(**options: Any) -> HealthService:
    handle = install(FastAPI(), enabled="ON", show_banner=False, **options)
    _HANDLES.append(handle)
    return health_service(handle.context)


def _check(service: HealthService) -> dict[str, Any]:
    return asyncio.run(service.check())


def _components(root: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in root["components"]}


def test_hung_health_worker_does_not_block_interpreter_exit():
    code = textwrap.dedent(
        """
        import asyncio
        import threading
        from fastapi import FastAPI
        from sharpit import install
        from sharpit.engine.collectors.health import health_service

        handle = install(FastAPI(), enabled="ON", show_banner=False, health_timeout=0.05,
                health_checks={"hung": lambda: threading.Event().wait(60)})
        report = asyncio.run(health_service(handle.context).check())
        assert report["components"][0]["details"]["error"].startswith("timed out")
        print("ready to exit", flush=True)
        """
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=6)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ready to exit"


# --- aggregation and guidance (ported) --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["UP", "DOWN"], "DOWN"),
        (["UP", "OUT_OF_SERVICE"], "OUT_OF_SERVICE"),
        (["OUT_OF_SERVICE", "DOWN"], "DOWN"),
        (["UNKNOWN", "UP"], "UP"),
        (["UNKNOWN"], "UNKNOWN"),
        ([], "UNKNOWN"),
    ],
)
def test_aggregate_spring_default_order(statuses: list[str], expected: str):
    # ported: Spring Boot SimpleStatusAggregator default order DOWN, OUT_OF_SERVICE, UP, UNKNOWN; empty -> UNKNOWN
    assert aggregate(statuses) == expected


def test_guidance_when_only_healthy_engine_pings():
    # ported: HealthServiceTests.addsGuidanceWhenOnlyDefaultContributorsArePresent (+ detectsDefaultsNested...)
    root = node("application", "UP", None, [node("db", "UP", None, [node("sqlite+pysqlite:///", "UP")])])
    shown = _with_guidance(root)
    assert (shown["status"], shown["available"], shown["unavailableReason"]) == ("UP", True, None)
    assert shown["guidanceReason"] == ENGINES_ONLY_REASON
    assert [s["title"] for s in shown["setup"]] == ["Add your own health checks"]


def test_engine_failure_visible_without_guidance():
    # ported: HealthServiceTests.keepsDefaultContributorFailuresVisibleWithoutGuidance
    root = node("application", "DOWN", None, [node("db", "DOWN", None, [node("e", "DOWN", {"error": "x"})])])
    shown = _with_guidance(root)
    assert (shown["guidanceReason"], shown["setup"], shown["available"]) == (None, [], True)


def test_user_check_passes_through():
    # ported: HealthServiceTests.passesThroughWhenANonDefaultContributorIsPresent
    root = node("application", "UP", None, [node("db", "UP", None, [node("e", "UP")]), node("cache", "UP")])
    assert _with_guidance(root)["guidanceReason"] is None


def test_root_without_components_passes_through():
    # ported: HealthServiceTests.passesThroughWhenRootHasNoComponents
    root = node("application", "UNKNOWN")
    assert _with_guidance(root) == root


def test_disabled_when_nothing_to_check():
    # ported: HealthServiceTests.rendersDisabledRootWhenProviderIsNull (no engine, no check is sharpit's "no provider")
    service = _service()
    for report in (service.report(), service.report(for_mcp=True), _check(service)):
        assert (report["name"], report["status"], report["available"]) == ("application", "DISABLED", False)
        assert (report["unavailableReason"], report["guidanceReason"], report["components"]) == (
            DISABLED_REASON,
            None,
            [],
        )
        snippets = [s for step in report["setup"] for s in step["snippets"]]
        assert any("engines=" in s for s in snippets) and any("health_checks=" in s for s in snippets)


# ported: HealthNodeDto (contract §7 / spec §7.8)
def test_shape_keys_match_bootui():
    sample = golden("health")
    service = _service(health_checks={"ok": lambda: True})
    for report in (service.report(), _check(service)):
        assert list(report) == list(sample)
        assert list(report["components"][0]) == list(sample["components"][0])


# --- user checks --------------------------------------------------------------------------------------------------


def test_bool_str_dict_results():
    checks: dict[str, Callable[[], object]] = {
        "yes": lambda: True,
        "no": lambda: False,
        "word": lambda: " out_of_service ",
        "mapping": lambda: {"status": "UP", "version": 3, "region": "eu"},
    }
    report = _check(_service(health_checks=checks))
    parts = _components(report)
    assert {n: c["status"] for n, c in parts.items()} == {
        "yes": "UP",
        "no": "DOWN",
        "word": "OUT_OF_SERVICE",
        "mapping": "UP",
    }
    assert report["status"] == "DOWN" and report["guidanceReason"] is None
    details = parts["mapping"]["details"]
    assert (details["version"], details["region"]) == (3, "eu") and isinstance(details["checkedAt"], int)


@pytest.mark.parametrize("result", ["MAYBE", {"version": 1}, None, 42])
def test_unknown_status_string(result: object):
    report = _check(_service(health_checks={"odd": lambda: result}))
    part = _components(report)["odd"]
    assert part["status"] == "UNKNOWN" and part["details"]["error"].startswith("unknown health status ")


def test_unknown_status_masked_before_cut():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghij"
    raw = "a" * 973 + " " + jwt  # repr's 1000-char cut lands inside the token's second segment
    part = _components(_check(_service(health_checks={"c": lambda: raw})))["c"]
    assert part["status"] == "UNKNOWN" and "eyJhbGciOiJIUzI1NiJ9" not in part["details"]["error"]


def test_raising_check_down_masked():
    def boom() -> bool:
        raise ConnectionError(f"cannot reach {DSN} password={SECRET}")

    part = _components(_check(_service(health_checks={"db2": boom})))["db2"]
    assert part["status"] == "DOWN" and part["details"]["error"].startswith("ConnectionError: cannot reach")
    assert SECRET not in str(part)


def test_async_call_object_awaited():
    class Probe:
        async def __call__(self) -> str:
            await asyncio.sleep(0)
            return "UP"

    async def coroutine() -> dict[str, Any]:
        return {"status": "DOWN", "reason": "disk"}

    report = _check(_service(health_checks={"object": Probe(), "wrapper": lambda: coroutine()}))
    parts = _components(report)
    assert (parts["object"]["status"], parts["wrapper"]["status"]) == ("UP", "DOWN")
    assert parts["wrapper"]["details"]["reason"] == "disk"


def test_awaitable_timeout_down():
    async def slow() -> bool:
        await asyncio.sleep(10)
        return True

    part = _components(_check(_service(health_timeout=0.05, health_checks={"slow": lambda: slow()})))["slow"]
    assert (part["status"], part["details"]["error"]) == ("DOWN", "timed out after 0.05s; still running")


def test_details_masked_nested_and_dsn():
    class Client:
        def __repr__(self) -> str:
            return f"Client(password={SECRET})"

    def check() -> dict[str, Any]:
        return {
            "status": "UP",
            "password": SECRET,
            "nested": {"api_key": SECRET, "dsn": DSN, "items": [{"token": SECRET}, DSN]},
            "client": Client(),
            "long": Client(),
            "count": 3,
        }

    details = _components(_check(_service(health_checks={"c": check})))["c"]["details"]
    assert details["password"] == MASK and details["nested"]["api_key"] == MASK
    assert details["nested"]["items"][0]["token"] == MASK
    assert SECRET not in str(details) and "db.internal/app" in details["nested"]["dsn"]
    assert details["client"].startswith("Client(") and details["count"] == 3


def test_metadata_only_health_details():
    def check() -> dict[str, Any]:
        return {"status": "UP", "dsn": DSN, "count": 3, "nested": {"note": "x"}}

    def boom() -> bool:
        raise RuntimeError(DSN)

    report = _check(_service(expose_values="METADATA_ONLY", health_checks={"c": check, "b": boom}))
    parts = _components(report)
    assert parts["c"]["status"] == "UP" and parts["b"]["status"] == "DOWN"
    assert (parts["c"]["details"]["dsn"], parts["c"]["details"]["count"]) == (None, None)
    assert parts["c"]["details"]["nested"] == {"note": None} and parts["b"]["details"]["error"] is None
    assert SECRET not in str(report)


def test_get_never_runs_checks():
    calls: list[int] = []
    service = _service(health_checks={"spy": lambda: calls.append(1) or True})
    report = service.report()
    assert (report["status"], _components(report)["spy"]["status"], report["guidanceReason"]) == (
        "UNKNOWN",
        "UNKNOWN",
        None,
    )
    assert service.report(for_mcp=True)["guidanceReason"] == NEVER_CHECKED
    assert calls == [] and service.last_status is None
    _check(service)
    assert calls == [1] and service.last_status == "UP"
    assert service.report()["status"] == "UP" and service.report(for_mcp=True)["guidanceReason"] is None


def _health_threads() -> list[str]:
    return [t.name for t in threading.enumerate() if t.name.startswith("sharpit-health")]


def test_executor_created_on_first_check_only():
    service = _service(health_checks={"ok": lambda: True})
    service.report()
    assert service._executor is None  # pyright: ignore[reportPrivateUsage]
    _check(service)
    assert service._executor is not None and _health_threads()  # pyright: ignore[reportPrivateUsage]


# --- engine pings -------------------------------------------------------------------------------------------------


@pytest.mark.needs_sqlalchemy
def test_engine_ping_not_traced():
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine("sqlite://")
    service = _service(engines=[engine], health_checks={"ok": lambda: True})
    report = _check(service)
    db = _components(report)["db"]
    (ping,) = db["components"]
    assert (db["status"], ping["status"]) == ("UP", "UP")
    assert (ping["details"]["database"], ping["details"]["validationQuery"]) == ("sqlite", "dialect ping")
    recorder = _HANDLES[-1].context.capture.sql_trace
    assert recorder is not None and recorder.report([])["entries"] == []


@pytest.mark.needs_sqlalchemy
def test_engine_ping_aiosqlite_up():
    pytest.importorskip("aiosqlite")
    engine = pytest.importorskip("sqlalchemy.ext.asyncio").create_async_engine("sqlite+aiosqlite://")

    async def main(service: HealthService) -> dict[str, Any]:
        try:
            return await service.check()
        finally:
            await engine.dispose()

    report = asyncio.run(main(_service(engines=[engine])))
    (ping,) = _components(report)["db"]["components"]
    assert ping["status"] == "UP", ping


@pytest.mark.needs_sqlalchemy
def test_engine_ping_failure_down_masked(tmp_path: Any):
    sa = pytest.importorskip("sqlalchemy")
    missing = tmp_path / "no-such-dir" / "app.db"  # sqlite cannot create a file in a missing directory
    engine = sa.create_engine(f"sqlite:///{missing}")
    (ping,) = _components(_check(_service(engines=[engine])))["db"]["components"]
    assert ping["status"] == "DOWN" and ping["details"]["error"].startswith("OperationalError")


@pytest.mark.needs_sqlalchemy
def test_engines_only_guidance():
    sa = pytest.importorskip("sqlalchemy")
    service = _service(engines=[sa.create_engine("sqlite://")])
    assert service.report()["guidanceReason"] == ENGINES_ONLY_REASON  # UNKNOWN counts as healthy (BootUI)
    assert service.report(for_mcp=True)["guidanceReason"] == NEVER_CHECKED
    report = _check(service)
    assert (report["status"], report["guidanceReason"]) == ("UP", ENGINES_ONLY_REASON)
