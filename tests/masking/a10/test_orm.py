"""A10: ORM reports read the dialect proved by the execution event."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from tests.masking.a10.conftest import plant_fails, scratch_package

from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqla import orm
from sharpit.engine.sqla.dialect_source import EngineDialectSource
from sharpit.engine.sqltext import DialectContext, resolve, statement_text

pytestmark = pytest.mark.needs_sqlalchemy
ROOT = Path(__file__).resolve().parents[3]
NODE = "tests/masking/a10/test_orm.py::test_a_binds_map_session_gives_one_answer"


def test_a_binds_map_session_gives_one_answer() -> None:
    engine = sa.create_engine("mysql+pymysql://user:password@localhost/db")
    try:
        statement = 'SELECT "id" FROM "payments"'
        event = SimpleNamespace(
            session=SimpleNamespace(bind=None),
            dialect=engine.dialect,
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
        "\n".join(
            (
                "from sharpit.engine.capture.statement import masked_shape",
                "",
                "    dialect = _dialect_of(",
                "        context",
                '        if getattr(context, "dialect", None) is not None',
                '        else getattr(getattr(context, "session", None), "bind", None)',
                "    )",
            )
        ),
        "\n".join(
            (
                "from sharpit.engine.capture.statement import masked_shape",
                "",
                "    dialect = _dialect_of(",
                '        getattr(getattr(context, "session", None), "bind", None)',
                "    )",
            )
        ),
    )
