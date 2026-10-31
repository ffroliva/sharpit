"""Database connection pools (F7, spec §7.7): SQLAlchemy pool counters in BootUI's Hikari shape.

Derived cases: BootUI reads HikariCP's MXBean; sharpit reads SQLAlchemy's pool counters and never borrows a connection.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.pools import pool_snapshot, pools_report
from sharpit.engine.masking import MASK
from sharpit.fastapi.adapter import SharpitHandle

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

_HANDLES: list[SharpitHandle] = []
POOL_KEYS = (
    "beanName", "poolName", "jdbcUrl", "username", "driverClassName", "minimumIdle", "maximumPoolSize",
    "connectionTimeoutMs", "idleTimeoutMs", "maxLifetimeMs", "validationTimeoutMs", "keepaliveTimeMs", "readOnly",
    "autoCommit", "available", "unavailableReason", "snapshot",
)  # fmt: skip


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _ctx(*engines: Any, **options: Any) -> Any:
    handle = install(FastAPI(), enabled="ON", show_banner=False, engines=list(engines), **options)
    _HANDLES.append(handle)
    return handle.context


def _queue_engine(tmp_path: Path, name: str = "app.db", **kw: Any) -> Any:
    return sa.create_engine(f"sqlite:///{tmp_path / name}", poolclass=sa.QueuePool, **kw)


def test_queue_pool_counters(tmp_path: Path):
    engine = _queue_engine(tmp_path, pool_size=3, max_overflow=2, pool_timeout=7, pool_recycle=30)
    ctx = _ctx(engine)
    conn = engine.connect()
    try:
        (pool,) = pools_report(ctx)["pools"]
        assert (pool["available"], pool["unavailableReason"]) == (True, None)
        assert (pool["maximumPoolSize"], pool["connectionTimeoutMs"], pool["maxLifetimeMs"]) == (5, 7000, 30000)
        assert pool["driverClassName"] == "sqlite+pysqlite (QueuePool)"
        snap = pool["snapshot"]
        assert (snap["active"], snap["idle"], snap["total"], snap["pending"]) == (1, 0, 1, None)
    finally:
        conn.close()
    assert pool_snapshot(ctx, pool["poolName"]) is not None
    assert pool_snapshot(ctx, pool["poolName"])["idle"] == 1  # type: ignore[index]


def test_unlimited_overflow_and_no_recycle_null(tmp_path: Path):
    (pool,) = pools_report(_ctx(_queue_engine(tmp_path, max_overflow=-1)))["pools"]
    assert (pool["maximumPoolSize"], pool["maxLifetimeMs"]) == (None, None)


def test_async_adapted_queue_pool(tmp_path: Path):
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'a.db'}")
    (pool,) = pools_report(_ctx(engine))["pools"]
    assert pool["available"] is True
    assert pool["driverClassName"] == "sqlite+aiosqlite (AsyncAdaptedQueuePool)"
    assert pool["snapshot"]["total"] == 0


@pytest.mark.parametrize("poolclass", ["NullPool", "StaticPool", "SingletonThreadPool"])
def test_null_pool_unavailable(tmp_path: Path, poolclass: str):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'n.db'}", poolclass=getattr(sa.pool, poolclass))
    ctx = _ctx(engine)
    (pool,) = pools_report(ctx)["pools"]
    assert (pool["available"], pool["unavailableReason"], pool["snapshot"]) == (
        False,
        f"{poolclass} keeps no pool statistics",
        None,
    )
    assert pool_snapshot(ctx, pool["poolName"]) is None


def test_names_unique_and_no_query(tmp_path: Path):
    first, second = _queue_engine(tmp_path, "same.db"), _queue_engine(tmp_path, "same.db")
    for engine in (first, second):  # set after create_engine: pysqlite warns on an unknown query argument
        engine.url = engine.url.update_query_dict({"timeout": "5", "password": "hunter2"})
    pools = pools_report(_ctx(first, second))["pools"]
    names = [p["poolName"] for p in pools]
    assert len(set(names)) == 2
    assert names[1] == names[0] + "#2"
    assert all("?" not in p["jdbcUrl"] and "hunter2" not in str(p) for p in pools)
    assert all(p["beanName"] == p["poolName"] == p["jdbcUrl"] for p in pools)


@pytest.mark.parametrize(
    ("exposure", "mask_secrets", "shown"),
    [("MASKED", True, MASK), ("MASKED", False, "scott"), ("FULL", True, "scott"), ("METADATA_ONLY", True, None)],
)
def test_username_masked(tmp_path: Path, exposure: str, mask_secrets: bool, shown: str | None):
    # BootUI ConnectionPoolService.maskUsername: hidden unless masking is off or exposure is FULL
    engine = _queue_engine(tmp_path)
    engine.url = engine.url.set(username="scott")  # pysqlite refuses userinfo at create_engine
    (pool,) = pools_report(_ctx(engine, expose_values=exposure, mask_secrets=mask_secrets))["pools"]
    assert pool["username"] == shown


def test_snapshot_unknown_none(tmp_path: Path):
    assert pool_snapshot(_ctx(_queue_engine(tmp_path)), "nope") is None


def test_report_borrows_no_connection(tmp_path: Path):
    engine = _queue_engine(tmp_path)
    checkouts: list[int] = []
    sa.event.listen(engine, "checkout", lambda *_a: checkouts.append(1))
    sa.event.listen(engine, "connect", lambda *_a: checkouts.append(2))
    ctx = _ctx(engine)
    (pool,) = pools_report(ctx)["pools"]
    pool_snapshot(ctx, pool["poolName"])
    assert checkouts == []


def test_autocommit_from_isolation_level(tmp_path: Path):
    plain, auto = _queue_engine(tmp_path, "p.db"), _queue_engine(tmp_path, "a.db", isolation_level="AUTOCOMMIT")
    assert [p["autoCommit"] for p in pools_report(_ctx(plain, auto))["pools"]] == [False, True]


def test_shape_keys_match_bootui(tmp_path: Path):
    # ported: HikariPoolsReport, HikariPoolDto, HikariPoolSnapshotDto
    report = pools_report(_ctx(_queue_engine(tmp_path)))
    assert tuple(report) == ("hikariPresent", "total", "pools")
    assert (report["hikariPresent"], report["total"]) == (True, 1)
    assert tuple(report["pools"][0]) == POOL_KEYS
    assert tuple(report["pools"][0]["snapshot"]) == ("timestamp", "active", "idle", "total", "pending")
