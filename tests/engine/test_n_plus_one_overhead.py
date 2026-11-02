"""F6 ORM observer budget: paired 1,000-SELECT SQLAlchemy sessions; see overhead-budgets.md."""

from __future__ import annotations

import time

import pytest

sa = pytest.importorskip("sqlalchemy")
from sqlalchemy.orm import Session  # noqa: E402
from tests.overhead import check_budget, paired  # noqa: E402

from sharpit.engine import sqla  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

STATEMENTS = 1_000
ORM_HOOK_BUDGET = 35e-6


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


def test_sqlalchemy_lazy_relationship_hook_overhead_budget() -> None:
    orm = pytest.importorskip("sqlalchemy.orm")
    engine = sa.create_engine("sqlite://")
    Base = orm.declarative_base()

    class Parent(Base):
        __tablename__ = "budget_parent"
        id = sa.Column(sa.Integer, primary_key=True)
        children = orm.relationship("Child")

    class Child(Base):
        __tablename__ = "budget_child"
        id = sa.Column(sa.Integer, primary_key=True)
        parent_id = sa.Column(sa.Integer, sa.ForeignKey("budget_parent.id"))

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(sa.insert(Parent.__table__), [{"id": i} for i in range(STATEMENTS)])
        connection.execute(sa.insert(Child.__table__), [{"id": i, "parent_id": i} for i in range(STATEMENTS)])

    def workload() -> float:
        completed = 0

        def count_lazy_load(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
            nonlocal completed
            if "FROM budget_child" in statement:
                completed += 1

        sa.event.listen(engine, "before_cursor_execute", count_lazy_load)
        try:
            start = time.perf_counter()
            with Session(engine) as session:
                for parent in session.scalars(sa.select(Parent)):
                    list(parent.children)
            elapsed = time.perf_counter() - start
        finally:
            sa.event.remove(engine, "before_cursor_execute", count_lazy_load)
        assert completed == STATEMENTS, f"expected {STATEMENTS} lazy loads, got {completed}"
        return elapsed / completed

    try:
        sqla.detach_session()

        def off() -> float:
            return workload()

        def on() -> float:
            assert sqla.attach_session() is True
            token = sqla.TEST.set(("n_plus_one_overhead", 1, "call"))
            try:
                return workload()
            finally:
                sqla.TEST.reset(token)
                sqla.detach_session()

        result = paired(off, on, rounds=5)
        check_budget("SQLAlchemy lazy relationship hooks", result, ORM_HOOK_BUDGET, "µs/lazy load", 1e-6)
    finally:
        sqla.detach_session()
        engine.dispose()
