"""Database connection pools panel (F7, spec §7.7): SQLAlchemy pool counters in BootUI's Hikari shape.

Only counters are read (``size()``, ``checkedin()``, ...): nothing borrows a connection, so a GET never connects.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from sharpit.engine import sqla

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext


def _queue_pool(pool: object) -> bool:
    sa = sqla.sqlalchemy_module()
    return sa is not None and isinstance(pool, sa.pool.QueuePool)  # AsyncAdaptedQueuePool is a subclass


def _snapshot(pool: Any) -> dict[str, Any]:
    """``HikariPoolSnapshotDto``; SQLAlchemy keeps no waiter count, so ``pending`` is null."""
    idle, active = pool.checkedin(), pool.checkedout()
    return {
        "timestamp": round(time.time() * 1000),
        "active": active,
        "idle": idle,
        "total": idle + active,
        "pending": None,
    }


def _ms(seconds: float) -> int | None:
    return None if seconds < 0 else round(seconds * 1000)


def _pool_dto(ctx: SharpitContext, name: str, engine: Any) -> dict[str, Any]:
    """``HikariPoolDto`` for one registered engine; ``engine`` is the sync ``Engine``."""
    pool = engine.pool
    kind = type(pool).__name__
    counted = _queue_pool(pool)
    isolation = engine.get_execution_options().get("isolation_level") or getattr(
        engine.dialect, "_on_connect_isolation_level", None
    )
    # BootUI maskUsername: shown only with masking off or FULL; a sensitive key gives exactly that through mask()
    username, _ = ctx.masker.mask("password", engine.url.username) if engine.url.username else (None, False)
    return {
        "beanName": name,
        "poolName": name,
        "jdbcUrl": name,  # the registry's display name: no userinfo, no query string (§6.2)
        "username": username,
        "driverClassName": f"{engine.url.get_backend_name()}+{engine.dialect.driver} ({kind})",
        "minimumIdle": None,
        "maximumPoolSize": (pool.size() + pool._max_overflow if pool._max_overflow >= 0 else None) if counted else None,  # noqa: SLF001
        "connectionTimeoutMs": _ms(pool._timeout) if counted else None,  # noqa: SLF001
        "idleTimeoutMs": None,
        "maxLifetimeMs": _ms(pool._recycle),  # noqa: SLF001 - every Pool has it; -1 means never recycled
        "validationTimeoutMs": None,
        "keepaliveTimeMs": None,
        "readOnly": False,
        "autoCommit": isolation == "AUTOCOMMIT",
        "available": counted,
        "unavailableReason": None if counted else f"{kind} keeps no pool statistics",
        "snapshot": _snapshot(pool) if counted else None,
    }


def _engines(ctx: SharpitContext) -> list[tuple[str, Any]]:
    registry = ctx.capture.engine_registry
    return registry.engines() if registry is not None and sqla.sqlalchemy_module() is not None else []


def pools_report(ctx: SharpitContext) -> dict[str, Any]:
    """``HikariPoolsReport {hikariPresent, total, pools}``; ``hikariPresent`` = SQLAlchemy 2.0+ imported."""
    pools = [_pool_dto(ctx, name, engine) for name, engine in _engines(ctx)]
    return {"hikariPresent": sqla.sqlalchemy_module() is not None, "total": len(pools), "pools": pools}


def pool_snapshot(ctx: SharpitContext, name: str) -> dict[str, Any] | None:
    """The pool's counters now, or None for an unknown name or a pool that keeps no statistics."""
    engine = next((e for n, e in _engines(ctx) if n == name), None)
    return _snapshot(engine.pool) if engine is not None and _queue_pool(engine.pool) else None
