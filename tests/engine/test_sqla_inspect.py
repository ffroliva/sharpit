"""Bounded catalog reads for the database advisor (0.5.0 plan A-dbadv-1 Task 2; WAVE-A §4 bounds).

``sqla.inspect.catalog(conn, bounds)`` reads the physical schema through SQLAlchemy's inspector into plain dicts: at
most 300 tables, 300 columns and 100 indexes per table, inside the cooperative 20-second budget. A bound that is
reached sets ``truncated``; a budget that runs out leaves a diagnostic, never a crash.
"""

from __future__ import annotations

import asyncio
import itertools
from typing import Any

import pytest

from sharpit.engine import sqla
from sharpit.engine.masking import Masker
from sharpit.engine.sqla import inspect as sqla_inspect

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")
QueuePool = pytest.importorskip("sqlalchemy.pool").QueuePool


def _engine(*ddl: str) -> Any:
    engine = sa.create_engine(
        "sqlite://", poolclass=QueuePool, pool_size=1, max_overflow=0, connect_args={"check_same_thread": False}
    )
    with engine.begin() as conn:
        for statement in ddl:
            conn.exec_driver_sql(statement)
    return engine


def _read(engine: Any, bounds: Any) -> dict[str, Any]:
    masker = Masker("MASKED", True, None)
    return asyncio.run(sqla.run_db_read(engine, lambda c: sqla_inspect.catalog(c, bounds, masker), 5.0, read_only=True))


def test_table_bound_truncates() -> None:
    engine = _engine(*(f"CREATE TABLE t{n:04d} (id INTEGER PRIMARY KEY)" for n in range(1000)))

    out = _read(engine, sqla_inspect.CatalogBounds())

    assert len(out["tables"]) == 300
    assert out["truncated"] is True
    assert out["tableCount"] == 1000


def test_index_bound_per_table() -> None:
    columns = ", ".join(f"c{n} INTEGER" for n in range(6))
    indexes = (f"CREATE INDEX ix_{n} ON wide (c{n})" for n in range(6))
    engine = _engine(f"CREATE TABLE wide (id INTEGER PRIMARY KEY, {columns})", *indexes)

    out = _read(engine, sqla_inspect.CatalogBounds(indexes=3))

    assert [len(t["indexes"]) for t in out["tables"]] == [3]
    assert out["truncated"] is True


def test_column_bound_per_table() -> None:
    columns = ", ".join(f"c{n} INTEGER" for n in range(10))
    engine = _engine(f"CREATE TABLE wide (id INTEGER PRIMARY KEY, {columns})")

    out = _read(engine, sqla_inspect.CatalogBounds(columns=4))

    assert [[c["name"] for c in t["columns"]] for t in out["tables"]] == [["id", "c0", "c1", "c2"]]
    assert out["truncated"] is True


def test_catalog_inside_read_only_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    # scenario row 23: a write attempted from inside the scan is refused by the server ("readonly database")
    engine = _engine("CREATE TABLE probe (id INTEGER PRIMARY KEY)")
    inspector_class = sa.engine.reflection.Inspector
    original = inspector_class.get_columns
    refused: list[str] = []

    def get_columns(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            self.bind.exec_driver_sql("INSERT INTO probe VALUES (1)")
        except Exception as exc:  # noqa: BLE001 - the test asserts on the refusal
            refused.append(str(exc))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(inspector_class, "get_columns", get_columns)
    _read(engine, sqla_inspect.CatalogBounds())

    assert len(refused) == 1
    assert "attempt to write a readonly database" in refused[0]
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM probe").scalar() == 0


def test_catalog_timeout_is_a_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(*(f"CREATE TABLE t{n} (id INTEGER PRIMARY KEY)" for n in range(5)))
    ticks = itertools.count(0, 15)  # every look at the clock is 15 s later: the 20 s budget runs out after one table
    monkeypatch.setattr(sqla_inspect, "_clock", lambda: float(next(ticks)))

    out = _read(engine, sqla_inspect.CatalogBounds())

    assert len(out["tables"]) < 5
    assert out["complete"] is False
    assert [d["level"] for d in out["diagnostics"]] == ["WARNING"]
    assert "budget" in out["diagnostics"][0]["message"]
