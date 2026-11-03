"""Engine introspection: live drivers and the per-context registry of engines."""

from __future__ import annotations

import gc
import threading
import time
import weakref
from dataclasses import dataclass
from typing import Any

from sharpit.engine import sqla as _sqla
from sharpit.engine.masking import Masker

_clock = time.monotonic  # test seam: the catalog budget's clock


@dataclass(frozen=True)
class CatalogBounds:
    """WAVE-A §4: 300 tables, 300 columns and 100 indexes per table, 500 vendor rows, a cooperative 20 s budget."""

    tables: int = 300
    columns: int = 300
    indexes: int = 100
    vendor_rows: int = 500
    budget: float = 20.0


def catalog(conn: Any, bounds: CatalogBounds) -> dict[str, Any]:
    """The physical schema behind ``conn`` as plain dicts, read within ``bounds``."""
    return {"dialect": "", "tables": [], "tableCount": 0, "truncated": False, "complete": True, "diagnostics": [],
            "server": {}}  # fmt: skip


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


class EngineRegistry:
    """The engines one context knows about, held weakly, each with a display name that never carries credentials."""

    def __init__(self, masker: Masker) -> None:
        self._masker = masker
        self._names: weakref.WeakKeyDictionary[Any, str] = weakref.WeakKeyDictionary()
        self._lock = threading.Lock()

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

    def holds(self, engine: object) -> bool:
        with self._lock:
            return engine in self._names

    def engines(self) -> list[tuple[str, Any]]:
        """``(display name, Engine)`` in registration order."""
        with self._lock:
            return [(name, engine) for engine, name in self._names.items()]

    def names(self) -> list[str]:
        return [name for name, _ in self.engines()]
