"""A10: ORM reports read the dialect proved by the execution event."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from tests.masking.a10.conftest import plant_fails, scratch_package

from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqla import orm
from sharpit.engine.sqla.dialect_source import EngineDialectSource
from sharpit.engine.sqltext import Dialect, DialectContext, resolve, statement_text

pytestmark = pytest.mark.needs_sqlalchemy
ROOT = Path(__file__).resolve().parents[3]
NODE = "tests/masking/a10/test_orm.py::test_a_binds_map_session_gives_one_answer"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)


@pytest.fixture
def keyed_masker(monkeypatch: pytest.MonkeyPatch) -> Iterator[Masker]:
    masker = Masker(Exposure.MASKED, True, identity_key=b"k" * 32)
    monkeypatch.setattr(orm, "_relationship_masker", lambda: masker)
    orm._masked_fingerprint.cache_clear()
    try:
        yield masker
    finally:
        orm._masked_fingerprint.cache_clear()


def test_a_binds_map_session_gives_one_answer(monkeypatch: pytest.MonkeyPatch, keyed_masker: Masker) -> None:
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    token = "A10" + "QUERY" + "SECRET"
    seen: list[str] = []
    shown: list[str] = []
    owners: list[object] = []
    dialect_of = orm._dialect_of

    def record_owner(owner: object) -> Dialect:
        owners.append(owner)
        return dialect_of(owner)

    monkeypatch.setattr(orm, "_dialect_of", record_owner)

    def on_load(_target: User, context: Any) -> None:
        sql = 'SELECT "password" FROM users'
        statement, _has_limit = orm._unbounded_read_statement_shape(context, sql)
        expected = statement_text(keyed_masker, sql, Dialect.SQLITE)
        secret_statement, _has_limit = orm._unbounded_read_statement_shape(context, f"SELECT '{token}' FROM users")
        shown.append(secret_statement)
        seen.append(orm._masked_fingerprint(statement, Dialect.SQLITE) or "")
        seen.append(orm._masked_fingerprint(expected or "", Dialect.SQLITE) or "")

    sa.event.listen(User, "load", on_load)
    try:
        with Session(binds={User: engine}) as bound:
            bound.add(User(id=1))
            bound.commit()
            bound.get(User, 1)
        with Session(bind=engine) as plain:
            plain.get(User, 1)
        assert len(seen) == 4
        assert all(seen)
        assert token not in shown[0]
        assert seen[0] == seen[1]
        assert seen[2] == seen[3]
        assert seen[0] == seen[2]
        assert owners[0] is engine
    finally:
        sa.event.remove(User, "load", on_load)
        engine.dispose()


def test_explicit_query_bind_matches_a_plain_session(keyed_masker: Masker) -> None:
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sql = 'SELECT "password" FROM users'
    seen: list[tuple[str, str | None]] = []

    def on_load(_target: User, context: Any) -> None:
        statement, _has_limit = orm._unbounded_read_statement_shape(context, sql)
        seen.append((statement, orm._masked_fingerprint(statement, Dialect.SQLITE)))

    sa.event.listen(User, "load", on_load)
    try:
        with Session(bind=engine) as plain:
            plain.add(User(id=1))
            plain.commit()
            plain.get(User, 1)
        with Session() as routed:
            routed.scalars(sa.select(User), bind_arguments={"bind": engine}).all()

        assert len(seen) == 2
        assert seen[0][0] == statement_text(keyed_masker, sql, Dialect.SQLITE)
        assert seen[0][1]
        assert seen[1][1]
        assert seen[0] == seen[1]
    finally:
        sa.event.remove(User, "load", on_load)
        engine.dispose()


def test_session_bind_remains_a_dialect_source_without_event_dialect() -> None:
    engine = sa.create_engine("mysql+pymysql://user:password@localhost/db")
    try:
        statement = 'SELECT "id" FROM "payments"'
        event = SimpleNamespace(
            session=SimpleNamespace(bind=engine),
            engine=engine,
            statement=statement,
            compiled=SimpleNamespace(statement=statement),
        )
        expected = statement_text(
            Masker(Exposure.MASKED, True),
            event.statement,
            resolve(event, (EngineDialectSource(),), DialectContext(lambda: None)),
        )

        actual, _has_limit = orm._unbounded_read_statement_shape(event, event.compiled.statement)

        assert actual == expected
    finally:
        engine.dispose()


def test_a_binds_map_regression_plant_fails(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    plant_fails(
        copy,
        NODE,
        "engine/sqla/orm.py",
        "session.get_bind(mapper=mapper)",
        "None",
    )
