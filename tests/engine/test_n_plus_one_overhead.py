from __future__ import annotations

import time

import pytest

sa = pytest.importorskip("sqlalchemy")
from sqlalchemy.orm import Session  # noqa: E402
from tests.overhead import check_budget, paired  # noqa: E402

from sharpit.engine import sqla  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

STATEMENTS = 1_000
ORM_HOOK_BUDGET = 0.0


def _workload(engine: object) -> float:
    completed = 0

    def count_statement(*_args: object, **_kwargs: object) -> None:
        nonlocal completed
        completed += 1

    sa.event.listen(engine, "before_cursor_execute", count_statement)
    try:
        start = time.perf_counter()
        with Session(engine) as session:
            for _ in range(STATEMENTS):
                session.execute(sa.select(1)).scalar_one()
        elapsed = time.perf_counter() - start
    finally:
        sa.event.remove(engine, "before_cursor_execute", count_statement)
    assert completed == STATEMENTS
    return elapsed / completed


def test_sqlalchemy_orm_hook_overhead_budget() -> None:
    engine = sa.create_engine("sqlite://")
    try:

        def off() -> float:
            return _workload(engine)

        def on() -> float:
            sa.event.listen(Session, "do_orm_execute", sqla.do_orm_execute)
            try:
                return _workload(engine)
            finally:
                sa.event.remove(Session, "do_orm_execute", sqla.do_orm_execute)

        result = paired(off, on, rounds=5)
        check_budget("SQLAlchemy ORM hooks", result, ORM_HOOK_BUDGET, "µs/statement", 1e-6)
    finally:
        if sa.event.contains(Session, "do_orm_execute", sqla.do_orm_execute):
            sa.event.remove(Session, "do_orm_execute", sqla.do_orm_execute)
        engine.dispose()
