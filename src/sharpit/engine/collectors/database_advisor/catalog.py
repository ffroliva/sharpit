"""The database advisor's facts (0.5.0 spec §5.8): each registered engine's catalog, its pool and its URL keys.

The catalog is read only through ``sqla.run_db_read(read_only=True)`` (F5b's verified path: PostgreSQL, MySQL/MariaDB,
SQLite; any other dialect is refused before a statement runs). The pool and URL facts come from the engine object, so
they need no connection: the pool class and its numbers, and the presence of an allow-listed URL query key. A URL value
is never read, and neither is ``url.password``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sharpit.engine import sqla
from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.daemon_executor import DaemonExecutor
from sharpit.engine.sqla.inspect import CatalogBounds, catalog, error_text

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext
    from sharpit.engine.singleflight import Flight

URL_KEYS = frozenset({"connect_timeout", "charset", "sslmode"})  # presence only, never a value
SCAN_BUDGET = 20.0
CATALOG_TIMEOUT = 5.0  # per statement, clamped to what is left of the scan budget
WALL_MARGIN = 1.0
BUDGET_RAN_OUT = "The scan budget ran out before this datasource was read."
LABELS = {"postgresql": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB", "sqlite": "SQLite"}
_clock = time.monotonic  # test seam: the scan budget's clock


@dataclass(frozen=True)
class Pool:
    """A pool's effective numbers, read from the live object; ``None`` where the pool class has no such number."""

    kind: str
    max_size: int | None  # pool size plus overflow; None when unbounded or not a fixed-size pool
    unbounded: bool  # an overflow of -1: no maximum at all
    recycle: int | None  # seconds; -1 means connections are never retired for age
    pre_ping: bool | None


@dataclass(frozen=True)
class Source:
    name: str
    dialect: str
    driver: str
    status: str  # AVAILABLE | PARTIAL | FAILED
    message: str | None
    catalog: dict[str, Any] = field(default_factory=dict[str, Any])
    pool: Pool | None = None
    url_keys: frozenset[str] = frozenset()
    echo: bool = False

    @property
    def tables(self) -> list[dict[str, Any]]:
        return self.catalog.get("tables", [])

    @property
    def server(self) -> dict[str, str]:
        return self.catalog.get("server", {})


Hit = tuple[str, str, str]  # (target, message, identity); the identity never holds a value
Outcome = list[Hit] | str  # the findings on one source, or why that source was not evaluated


@dataclass(frozen=True)
class Rule:
    definition: RuleDefinition
    check: Callable[[Source], Outcome]


def unreadable(source: Source) -> str | None:
    """Why a schema rule cannot look at ``source``, else None."""
    return None if source.status != "FAILED" else f"Datasource {source.name} could not be read."


def engine_facts(engine: Any) -> tuple[str, str, Pool | None, frozenset[str], bool]:
    """``(dialect, driver, pool, url keys, echo)`` from the engine object alone; defensive, never connects."""
    sync = getattr(engine, "sync_engine", engine)
    dialect = getattr(sync, "dialect", None)
    url = getattr(sync, "url", None)
    query: Any = getattr(url, "query", None) or {}
    keys = frozenset(key for key in query if key in URL_KEYS)  # iterates the names only
    return (
        str(getattr(dialect, "name", "") or ""),
        str(getattr(dialect, "driver", "") or ""),
        _pool(getattr(sync, "pool", None)),
        keys,
        bool(getattr(sync, "echo", False)),
    )


def _pool(pool: Any) -> Pool | None:
    if pool is None:
        return None
    recycle = getattr(pool, "_recycle", None)
    pre_ping = getattr(pool, "_pre_ping", None)
    overflow = getattr(pool, "_max_overflow", None)
    size = getattr(pool, "size", None)
    max_size, unbounded = None, False
    try:
        if isinstance(overflow, int) and callable(size):
            unbounded = overflow < 0
            max_size = None if unbounded else int(size()) + overflow
    except Exception:  # noqa: BLE001 - an unreadable number stays unknown
        max_size = None
    return Pool(
        type(pool).__name__,
        max_size,
        unbounded,
        recycle if isinstance(recycle, int) else None,
        pre_ping if isinstance(pre_ping, bool) else None,
    )


def bounds_of(ctx: SharpitContext) -> CatalogBounds:
    s = ctx.settings
    return CatalogBounds(
        s.database_advisor_max_tables,
        s.database_advisor_max_columns,
        s.database_advisor_max_indexes_per_table,
        s.database_advisor_max_vendor_rows,
        SCAN_BUDGET,
    )


async def read_sources(ctx: SharpitContext, flight: Flight) -> list[Source]:
    """Every registered engine's facts, one engine after another, inside one cooperative scan budget."""
    registry = ctx.capture.engine_registry
    engines: Sequence[tuple[str, Any]] = registry.engines() if registry is not None else []
    bounds = bounds_of(ctx)
    start = _clock()
    sources: list[Source] = []
    for name, engine in engines:
        dialect, driver, pool, keys, echo = engine_facts(engine)
        remaining = SCAN_BUDGET - (_clock() - start)
        if remaining <= 0:
            sources.append(Source(name, dialect, driver, "FAILED", BUDGET_RAN_OUT, {}, pool, keys, echo))
            continue
        status, message, found = await _read(ctx, flight, engine, CatalogBounds(**{**vars(bounds),
                                             "budget": remaining}))  # fmt: skip
        sources.append(Source(name, dialect, driver, status, message, found, pool, keys, echo))
    return sources


async def _read(
    ctx: SharpitContext, flight: Flight, engine: Any, bounds: CatalogBounds
) -> tuple[str, str | None, dict[str, Any]]:
    executor = ctx.lazy("database-advisor.executor", lambda: DaemonExecutor(2, thread_name_prefix="sharpit-dbadv"))
    try:
        found = await sqla.run_db_read(
            engine,
            lambda conn: catalog(conn, bounds),
            min(CATALOG_TIMEOUT, bounds.budget),
            executor=executor,
            done=flight.worker(),
            wall_timeout=bounds.budget + WALL_MARGIN,
            read_only=True,
        )
    except sqla.ReadOnlyUnavailable as exc:
        return "FAILED", exc.reason, {}
    except TimeoutError:
        return "FAILED", BUDGET_RAN_OUT, {}
    except Exception as exc:  # noqa: BLE001 - a failed engine is reported for that engine, never raised
        return "FAILED", error_text(exc), {}
    partial = found["truncated"] or not found["complete"]
    return ("PARTIAL" if partial else "AVAILABLE"), None, found
