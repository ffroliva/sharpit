"""Engine introspection: live drivers and the per-context registry of engines."""

from __future__ import annotations

import gc
import threading
import time
import weakref
from dataclasses import dataclass
from typing import Any, cast

from sharpit.engine import sqla as _sqla
from sharpit.engine.masking import Masker
from sharpit.engine.sqla.dialect_source import engine_dialect
from sharpit.engine.sqltext import Dialect, dialect_of_name
from sharpit.engine.sqltext import error_text as sql_error_text

_clock = time.monotonic  # test seam: the catalog budget's clock


@dataclass(frozen=True)
class CatalogBounds:
    """WAVE-A §4: 300 tables, 300 columns and 100 indexes per table, 500 vendor rows, a cooperative 20 s budget."""

    tables: int = 300
    columns: int = 300
    indexes: int = 100
    vendor_rows: int = 500
    budget: float = 20.0


# the server limits the pool rules compare with (BootUI ``ServerSettings``): names only, from an allow-list
_SERVER_SQL = {
    "postgresql": "SELECT name, setting FROM pg_settings WHERE name IN ('max_connections', "
    "'superuser_reserved_connections', 'reserved_connections', 'idle_session_timeout')",
    "mysql": "SHOW SESSION VARIABLES WHERE Variable_name IN ('wait_timeout', 'max_connections')",
    "mariadb": "SHOW SESSION VARIABLES WHERE Variable_name IN ('wait_timeout', 'max_connections')",
}


def error_text(exc: BaseException, masker: Masker, dialect: Dialect | None = None) -> str:
    """An error's first line only: SQLAlchemy appends the statement and its parameters on the lines after it."""
    resolved = Dialect.UNSUPPORTED if dialect is None else dialect
    lines = (sql_error_text(masker, exc, resolved, keep_frames=False) or "").strip().splitlines()
    return lines[0] if lines else type(exc).__name__


def catalog(conn: Any, bounds: CatalogBounds, masker: Masker) -> dict[str, Any]:
    """The physical schema behind ``conn`` as plain dicts, read within ``bounds`` (run it inside the read-only read).

    Tables past ``bounds.tables``, columns and indexes past their per-table bounds are not kept and set ``truncated``.
    The budget is cooperative: it is checked between tables, so one slow catalog call can overrun it.
    """
    start = _clock()
    dialect = conn.dialect.name
    dialect_enum = dialect_of_name(dialect) or Dialect.UNSUPPORTED
    diagnostics: list[dict[str, str]] = []
    inspector = _sqla.sqlalchemy_module().inspect(conn)  # type: ignore[union-attr]  # callers hold a SQLAlchemy conn
    names: list[str] = inspector.get_table_names()
    truncated, complete = len(names) > bounds.tables, True
    tables: list[dict[str, Any]] = []
    for name in names[: bounds.tables]:
        if _clock() - start > bounds.budget:
            complete = False
            diagnostics.append(_warning(f"The {bounds.budget:g}-second scan budget ran out after {len(tables)} of "
                                        f"{len(names)} tables; the rest were not read."))  # fmt: skip
            break
        try:
            table, cut = _table(conn, inspector, name, bounds)
        except Exception as exc:  # noqa: BLE001 - one unreadable table is a diagnostic; never a failed scan
            complete = False
            diagnostics.append(_warning(f"Table {name} could not be read: {error_text(exc, masker, dialect_enum)}"))
            continue
        tables.append(table)
        truncated |= cut
    return {
        "dialect": dialect,
        "tables": tables,
        "tableCount": len(names),
        "truncated": truncated,
        "complete": complete,
        "diagnostics": diagnostics,
        "server": _server(conn, dialect, bounds, diagnostics, masker),
    }


def _warning(message: str) -> dict[str, str]:
    return {"level": "WARNING", "message": message}


def _type_text(conn: Any, column_type: Any) -> str:
    try:
        return str(column_type.compile(dialect=conn.dialect)).upper()
    except Exception:  # noqa: BLE001 - a type the dialect cannot render is still named
        return type(column_type).__name__.upper()


def _texts(options: Any) -> dict[str, str]:
    """Reflected FK/index options as sorted text, so two definitions compare by value."""
    items = cast("dict[str, object]", options or {}).items()
    return {str(k): str(v) for k, v in sorted(items)}


def _table(conn: Any, inspector: Any, name: str, bounds: CatalogBounds) -> tuple[dict[str, Any], bool]:
    columns: list[dict[str, Any]] = inspector.get_columns(name)
    indexes: list[dict[str, Any]] = inspector.get_indexes(name)
    cut = len(columns) > bounds.columns or len(indexes) > bounds.indexes
    table: dict[str, Any] = {
        "schema": None,  # the connection's default schema only
        "name": name,
        "truncated": cut,  # a rule never claims an absence from this table's cut inventory
        "columns": [
            {
                "name": c["name"],
                "type": _type_text(conn, c["type"]),
                "nullable": bool(c.get("nullable", True)),
                "autoincrement": c.get("autoincrement") is True or bool(c.get("identity")),
            }
            for c in columns[: bounds.columns]
        ],
        "primaryKey": list(inspector.get_pk_constraint(name).get("constrained_columns") or []),
        "foreignKeys": [
            {
                "name": fk.get("name"),
                "columns": list(fk["constrained_columns"]),
                "referredSchema": fk.get("referred_schema"),
                "referredTable": fk["referred_table"],
                "referredColumns": list(fk["referred_columns"]),
                "options": _texts(fk.get("options")),
            }
            for fk in inspector.get_foreign_keys(name)
        ],
        "indexes": [
            {
                "name": ix.get("name"),
                "columns": list(ix.get("column_names") or []),  # None marks an expression key part
                "unique": bool(ix.get("unique")),
                "options": _texts(ix.get("dialect_options")),
            }
            for ix in indexes[: bounds.indexes]
        ],
    }
    return table, cut


def _server(
    conn: Any, dialect: str, bounds: CatalogBounds, diagnostics: list[dict[str, str]], masker: Masker
) -> dict[str, str]:
    sql = _SERVER_SQL.get(dialect)
    if sql is None:
        return {}
    try:
        if dialect == "postgresql":  # a failed statement must not abort the read's transaction
            with conn.begin_nested():
                rows = conn.exec_driver_sql(sql).fetchmany(bounds.vendor_rows)
        else:
            rows = conn.exec_driver_sql(sql).fetchmany(bounds.vendor_rows)
    except Exception as exc:  # noqa: BLE001 - the pool rules then skip with the reason
        dialect_enum = dialect_of_name(dialect) or Dialect.UNSUPPORTED
        diagnostics.append(_warning(f"Server settings could not be read: {error_text(exc, masker, dialect_enum)}"))
        return {}
    return {str(row[0]).lower(): str(row[1]) for row in rows}


def _engine_class() -> type | None:
    sa = _sqla.sqlalchemy_module()
    return sa.engine.Engine if sa is not None else None


def live_engine_drivers() -> set[str]:
    """Drivers of live SQLAlchemy Engine objects; inspect once without importing SQLAlchemy."""
    sa = _sqla.sqlalchemy_module()
    if sa is None:
        return set()
    engine_class = sa.engine.Engine
    drivers: set[str] = set()
    try:
        for obj in gc.get_objects():
            if type(obj) is engine_class:
                drivers.add(obj.dialect.driver)
    except Exception:  # noqa: BLE001 - best-effort evidence must not affect the host
        return drivers
    return drivers


def maximum_pool_size(pool: Any) -> int | None:
    """A queue pool's maximum size (its size plus its overflow), else ``None``: other pools and an unbounded overflow
    have none. Counters only: nothing borrows a connection."""
    sa = _sqla.sqlalchemy_module()
    if sa is None or not isinstance(pool, sa.pool.QueuePool) or pool._max_overflow < 0:  # noqa: SLF001
        return None
    return pool.size() + pool._max_overflow  # noqa: SLF001


class EngineRegistry:
    """The engines one context knows about, held weakly, each with a display name that never carries credentials."""

    def __init__(self, masker: Masker) -> None:
        self._masker = masker
        self._names: weakref.WeakKeyDictionary[Any, str] = weakref.WeakKeyDictionary()
        self._bases: weakref.WeakKeyDictionary[Any, str] = weakref.WeakKeyDictionary()  # name before any "#n"
        self._lock = threading.RLock()
        self._snapshot: tuple[tuple[weakref.ReferenceType[Any], str], ...] = ()
        self._pool_names: weakref.WeakKeyDictionary[Any, str] = weakref.WeakKeyDictionary()  # pool -> engine name

    def add(self, engine: object) -> None:
        """Register a sync ``Engine`` or an ``AsyncEngine`` (its ``sync_engine``); anything else is ignored."""
        engine_class = _engine_class()
        sync: Any = getattr(engine, "sync_engine", engine)
        if engine_class is None or not isinstance(sync, engine_class):
            return
        with self._lock:
            if sync in self._names:
                return
            url = sync.url
            host = f"{url.host}:{url.port}" if url.host and url.port else url.host or ""
            name = f"{url.get_backend_name()}+{sync.dialect.driver}://{host}/{url.database or ''}"
            name = self._masker.mask_text(name) or name
            taken = set(self._names.values())
            unique, n = name, 1
            while unique in taken:
                n += 1
                unique = f"{name}#{n}"
            self._names[sync] = unique
            self._bases[sync] = name
            self._snapshot = tuple((weakref.ref(key), value) for key, value in self._names.items())

    def holds(self, engine: object) -> bool:
        return any(ref() is engine for ref, _ in self._snapshot)

    def name_of_pool(self, pool: object) -> str | None:
        """The display name of the registered engine that owns ``pool`` (what the connection-pools panel shows).
        Called per checkout: a pool already matched is a dict hit; a miss scans the engines and learns a match."""
        if pool is None:
            return None
        known = self._pool_names.get(pool)
        if known is not None:
            return known
        for ref, name in self._snapshot:
            engine = ref()
            if engine is not None and engine.pool is pool:
                self._pool_names[pool] = (
                    name  # a disposed engine gets a new pool: that one misses once, the old one dies
                )
                return name
        return None

    def pool_size_of(self, name: str) -> int | None:
        """The maximum pool size of the registered engine displayed as ``name`` (``DataSourcePoolSizes.apply``)."""
        engine = next((e for n, e in self.engines() if n == name), None)
        return None if engine is None else maximum_pool_size(engine.pool)

    def engines(self) -> list[tuple[str, Any]]:
        """``(display name, Engine)`` in registration order."""
        return [(name, engine) for ref, name in self._snapshot if (engine := ref()) is not None]

    def database_names(self) -> list[str]:
        """One display name per database: engines on the same masked URL (``name#2``...) count once, first name wins."""
        seen: set[str] = set()
        names: list[str] = []
        for name, engine in self.engines():
            base = self._bases.get(engine, name)
            if base not in seen:
                seen.add(base)
                names.append(name)
        return names

    def has_engines(self) -> bool:
        return any(ref() is not None for ref, _ in self._snapshot)

    def names(self) -> list[str]:
        return [name for name, _ in self.engines()]

    def family(self) -> Dialect | None:
        """The live engines' current dialects, with no lock: ``engine.dialect`` can change after ``add``."""
        families = {engine_dialect(engine) for _, engine in self.engines()}
        family = families.pop() if len(families) == 1 else None
        return None if family is Dialect.UNSUPPORTED else family
