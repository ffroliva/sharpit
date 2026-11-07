from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from tests.masking.a10.conftest import plant_fails, scratch_package

from sharpit.engine.collectors.alembic import AlembicFiles
from sharpit.engine.collectors.alembic import _read as read_alembic
from sharpit.engine.collectors.mysql.querytext import mysql_query_text
from sharpit.engine.collectors.mysql.sections import _reason as mysql_section_reason
from sharpit.engine.collectors.postgresql.limits import RowLimits
from sharpit.engine.collectors.postgresql.querytext import query_text
from sharpit.engine.collectors.postgresql.sections import ReadBudget, ReadContext
from sharpit.engine.collectors.postgresql.sections import _describe as postgres_section_reason
from sharpit.engine.collectors.postgresql.service import PostgresState
from sharpit.engine.collectors.postgresql.service import _read_engine as read_postgres_engine
from sharpit.engine.masking import Exposure, Masker

pytestmark = pytest.mark.needs_sqlalchemy
MASKER = Masker(Exposure.MASKED, True)
NODE = "tests/masking/a10/test_collectors.py::test_postgresql_catalog_hides_unicode_space_before_dollar_quote"
MODULE = "engine/collectors/postgresql/querytext.py"
ANCHOR = "return truncate(statement_text(masker, sql, Dialect.POSTGRESQL), max_length)"


def test_postgresql_catalog_hides_unicode_space_before_dollar_quote() -> None:
    secret = "A10" + "QUERY" + "SECRET"
    shown = query_text(MASKER, f"SELECT\u2003$tag${secret}$tag$")
    assert secret not in (shown or "")


def test_postgresql_catalog_rule_fails_when_planted(tmp_path: Path) -> None:
    package = scratch_package(tmp_path)
    plant_fails(package, NODE, MODULE, ANCHOR, "return truncate(masker.mask_text(sql), max_length)")


def test_mysql_catalog_masks_a10_literal() -> None:
    token = "A10" + "QUERY" + "SECRET"
    shown = mysql_query_text(MASKER, f"SELECT '{token}'")
    assert token not in (shown or "")


def test_mysql_catalog_dialect_route_fails_when_planted(tmp_path: Path) -> None:
    package = scratch_package(tmp_path)
    plant_fails(
        package,
        "tests/masking/a10/test_collectors.py::test_mysql_catalog_masks_a10_literal",
        "engine/collectors/mysql/querytext.py",
        "return truncate(statement_text(masker, sql, dialect=Dialect.MYSQL_FAMILY), max_length)",
        "return truncate(masker.mask_text(sql), max_length)",
    )


def test_mysql_section_error_masks_a10_literal() -> None:
    token = "A10" + "QUERY" + "SECRET"
    shown = mysql_section_reason(MASKER, RuntimeError(f"failed\n[SQL: SELECT '{token}']"))
    assert token not in shown


def test_mysql_section_error_route_fails_when_planted(tmp_path: Path) -> None:
    package = scratch_package(tmp_path)
    plant_fails(
        package,
        "tests/masking/a10/test_collectors.py::test_mysql_section_error_masks_a10_literal",
        "engine/collectors/mysql/sections.py",
        "return error_text(masker, exc, Dialect.MYSQL_FAMILY, known=True) or type(exc).__name__",
        "return str(exc)",
    )


def test_postgresql_section_error_masks_a10_literal() -> None:
    token = "A10" + "QUERY" + "SECRET"
    shown = postgres_section_reason(
        ReadContext(None, MASKER, RowLimits(), ReadBudget.start(1)),
        "tables",
        RuntimeError(f"failed\n[SQL: SELECT '{token}']"),
    )
    assert token not in shown


def test_postgresql_section_error_route_fails_when_planted(tmp_path: Path) -> None:
    package = scratch_package(tmp_path)
    plant_fails(
        package,
        "tests/masking/a10/test_collectors.py::test_postgresql_section_error_masks_a10_literal",
        "engine/collectors/postgresql/sections.py",
        "masked = error_text(ctx.masker, exc, Dialect.POSTGRESQL, known=True)",
        "masked = str(exc)",
    )


def test_postgresql_service_error_masks_a10_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "A10" + "QUERY" + "SECRET"

    async def fail_read(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(f"failed\n[SQL: SELECT '{token}']")

    import sharpit.engine.collectors.postgresql.service as service

    monkeypatch.setattr(service.RowLimits, "from_settings", classmethod(lambda _cls, _settings: RowLimits()))
    monkeypatch.setattr(service.sqla, "run_db_read", fail_read)
    ctx = SimpleNamespace(masker=MASKER, settings=object(), lazy=lambda _key, _factory: None)
    result = asyncio.run(
        read_postgres_engine(
            ctx,
            PostgresState(),
            SimpleNamespace(worker=lambda: None),
            "primary",
            object(),
            ReadBudget.start(1),
            [],
        )
    )
    assert token not in str(result)


def test_postgresql_service_error_route_fails_when_planted(tmp_path: Path) -> None:
    package = scratch_package(tmp_path)
    plant_fails(
        package,
        "tests/masking/a10/test_collectors.py::test_postgresql_service_error_masks_a10_literal",
        "engine/collectors/postgresql/service.py",
        "error_text(ctx.masker, exc, Dialect.POSTGRESQL, known=True) or type(exc).__name__",
        "str(exc)",
    )


def test_mysql_service_error_masks_a10_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "A10" + "QUERY" + "SECRET"

    async def fail_read(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(f"failed\n[SQL: SELECT '{token}']")

    import sharpit.engine.collectors.mysql.service as service

    monkeypatch.setattr(service.RowLimits, "from_settings", classmethod(lambda _cls, _settings: RowLimits()))
    monkeypatch.setattr(service.sqla, "run_db_read", fail_read)
    ctx = SimpleNamespace(masker=MASKER, settings=object(), lazy=lambda _key, _factory: None)
    result = asyncio.run(
        service._read_engine(
            ctx,
            service.MySqlState(),
            SimpleNamespace(worker=lambda: None),
            "primary",
            object(),
            service.ReadBudget.start(1),
            [],
        )
    )
    assert token not in str(result)


def test_mysql_service_error_route_fails_when_planted(tmp_path: Path) -> None:
    package = scratch_package(tmp_path)
    plant_fails(
        package,
        "tests/masking/a10/test_collectors.py::test_mysql_service_error_masks_a10_literal",
        "engine/collectors/mysql/service.py",
        "error_text(ctx.masker, exc, Dialect.MYSQL_FAMILY, known=True) or type(exc).__name__",
        "str(exc)",
    )


@pytest.mark.asyncio
async def test_alembic_event_error_masks_a10_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "A10" + "QUERY" + "SECRET"

    async def fail_read(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(f"failed\n[SQL: SELECT '{token}']")

    monkeypatch.setattr("sharpit.engine.collectors.alembic.sqla.run_db_read", fail_read)
    ctx = SimpleNamespace(masker=MASKER, settings=SimpleNamespace(alembic_timeout=1))
    engine = sa.create_engine("sqlite://")
    try:
        read = await read_alembic(
            ctx,
            AlembicFiles("alembic.ini"),
            "primary",
            engine,
            SimpleNamespace(worker=lambda: None),
            object(),
        )
        assert read.reason is not None
        assert token not in read.reason
    finally:
        engine.dispose()


def test_alembic_error_route_fails_when_planted(tmp_path: Path) -> None:
    package = scratch_package(tmp_path)
    plant_fails(
        package,
        "tests/masking/a10/test_collectors.py::test_alembic_event_error_masks_a10_literal",
        "engine/collectors/alembic.py",
        "reason = error_text(ctx.masker, exc, dialect) or type(exc).__name__",
        "reason = str(exc)",
    )
