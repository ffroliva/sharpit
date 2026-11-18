"""Incomplete Database Advisor discovery (BootUI 2.4.0 #1600 parity).

Incomplete evidence (missing driver metadata, failed ORM model discovery, or cut/failed PostgreSQL
relation inventory) is reported as WARNING diagnostics and never reads as a clean scan (SCANNED),
keeping the report status PARTIAL. Absent SQLAlchemy ORM models remain a neutral INFO skip.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import DeclarativeBase

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.collectors.database_advisor import report, rules_orm
from sharpit.engine.collectors.database_advisor.catalog import Source
from sharpit.engine.collectors.database_advisor.report import DatabaseAdvisorService
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


def _catalog(conn: Any) -> dict[str, Any]:
    masker = Masker("MASKED", True, None)
    return sqla_inspect.catalog(conn, sqla_inspect.CatalogBounds(), masker)


def test_sqlite_driver_version_yields_complete_true() -> None:
    # SQLite driver version comes from sqlite3.sqlite_version -> complete=True, SCANNED
    engine = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    with engine.connect() as conn:
        out = _catalog(conn)

    assert out["complete"] is True
    assert not any("driver version" in d["message"] for d in out["diagnostics"])

    source = Source("primary", "sqlite", "pysqlite", "AVAILABLE", None, {**out, "orm": rules_orm.facts(())})
    evaluated = report.evaluate([source])
    assert evaluated.status == "SCANNED"
    assert evaluated.evidence["coverageComplete"] is True


@pytest.mark.asyncio
async def test_aiosqlite_driver_version_yields_complete_true() -> None:
    # aiosqlite engine driver version unwraps to aiosqlite -> complete=True, SCANNED
    pytest.importorskip("aiosqlite")
    from sqlalchemy.ext.asyncio import create_async_engine

    from sharpit.engine import sqla

    ae = create_async_engine("sqlite+aiosqlite://", poolclass=sa.pool.AsyncAdaptedQueuePool)
    async with ae.begin() as conn:
        await conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")

    masker = Masker("MASKED", True, None)
    out = await sqla.run_db_read(
        ae,
        lambda conn: sqla_inspect.catalog(conn, sqla_inspect.CatalogBounds(), masker),
        5.0,
        read_only=True,
    )

    assert out["complete"] is True
    assert not any("driver version" in d["message"] for d in out["diagnostics"])

    source = Source("primary", "sqlite", "aiosqlite", "AVAILABLE", None, {**out, "orm": rules_orm.facts(())})
    evaluated = report.evaluate([source])
    assert evaluated.status == "SCANNED"
    assert evaluated.evidence["coverageComplete"] is True


def test_fake_driver_with_no_version_anywhere_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    # fake driver with no version anywhere -> WARNING diagnostic, complete=False
    engine = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    with engine.connect() as conn:
        monkeypatch.setattr(conn.dialect, "dbapi", type("FakeDbApi", (), {})())
        monkeypatch.setattr(conn.dialect, "driver", "nonexistent_fake_driver_without_pkg")

        out = _catalog(conn)

    assert out["complete"] is False
    assert any("The database driver version was unavailable." in d["message"] for d in out["diagnostics"])


def test_null_driver_name_is_reported_as_incomplete_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: SchemaIntrospectorTests.nullDriverNameIsReportedAsIncompleteEvidence
    engine = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    with engine.connect() as conn:
        monkeypatch.setattr(conn.dialect, "driver", None)

        out = _catalog(conn)

    assert out["complete"] is False
    expected = "The database driver name was unavailable; driver settings are not evaluated."
    assert any(expected in d["message"] for d in out["diagnostics"])


def test_a_null_url_is_a_warning_and_makes_evidence_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: SchemaIntrospectorDriverEvidenceTests.aNullUrlIsAWarningAndMakesEvidenceIncomplete
    engine = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    with engine.connect() as conn:
        monkeypatch.setattr(conn.engine, "url", None)

        out = _catalog(conn)

    assert out["complete"] is False
    expected = "The driver reported no database URL; driver settings configured in it are not evaluated."
    assert any(expected in d["message"] for d in out["diagnostics"])


def test_scan_with_findings_has_usable_true() -> None:
    # BootUI DatabaseAdvisorScanner.doScan parity: usable when any rule evaluated, even with findings
    engine = _engine("CREATE TABLE items (val TEXT)")
    with engine.connect() as conn:
        out = _catalog(conn)

    source = Source("primary", "sqlite", "pysqlite", "AVAILABLE", None, {**out, "orm": rules_orm.facts(())})
    evaluated = report.evaluate([source])
    assert len(evaluated.findings) > 0
    assert evaluated.evidence["usable"] is True


def test_distinguishes_absent_jpa_from_a_zero_entity_discovery_failure() -> None:
    # ported: DatabaseAdvisorScannerTests.distinguishesAbsentJpaFromAZeroEntityDiscoveryFailure
    table = {
        "name": "users",
        "schema": None,
        "truncated": False,
        "columns": [],
        "primaryKey": ["id"],
        "foreignKeys": [],
        "indexes": [],
    }
    source_clean = Source(
        "primary",
        "sqlite",
        "pysqlite",
        "AVAILABLE",
        None,
        {
            "dialect": "sqlite",
            "tables": [table],
            "tableCount": 1,
            "truncated": False,
            "complete": True,
            "diagnostics": [],
            "server": {},
            "orm": rules_orm.facts(()),
        },
    )
    absent = report.evaluate([source_clean])
    assert any(d["source"] == "SQLAlchemy metadata" and d["level"] == "INFO" for d in absent.detail.diagnostics)
    assert absent.status == "SCANNED"

    source_failed = Source(
        "primary",
        "sqlite",
        "pysqlite",
        "AVAILABLE",
        None,
        {
            "dialect": "sqlite",
            "tables": [table],
            "tableCount": 1,
            "truncated": False,
            "complete": True,
            "diagnostics": [],
            "server": {},
            "orm": {"skipped": "metamodel unavailable", "known_absent": False, "errors": ["metamodel unavailable"]},
        },
    )
    failed = report.evaluate([source_failed])
    assert failed.status == "PARTIAL"
    assert failed.evidence["coverageComplete"] is False
    assert any(d["source"] == "SQLAlchemy metadata" and d["level"] == "WARNING" for d in failed.detail.diagnostics)


def test_unconfigured_mappers_neutral_info_skip_stays_scanned() -> None:
    # UNCONFIGURED mappers (scanned before first query): neutral INFO skip, scan stays SCANNED
    class Base(DeclarativeBase):
        pass

    class User(Base):
        __tablename__ = "users"
        id = sa.Column(sa.Integer, primary_key=True)

    orm_facts = rules_orm.facts((Base,))
    assert orm_facts["known_absent"] is True

    table = {
        "name": "users",
        "schema": None,
        "truncated": False,
        "columns": [],
        "primaryKey": ["id"],
        "foreignKeys": [],
        "indexes": [],
    }
    source = Source(
        "primary",
        "sqlite",
        "pysqlite",
        "AVAILABLE",
        None,
        {
            "dialect": "sqlite",
            "tables": [table],
            "tableCount": 1,
            "truncated": False,
            "complete": True,
            "diagnostics": [],
            "server": {},
            "orm": orm_facts,
        },
    )
    res = report.evaluate([source])
    assert res.status == "SCANNED"
    assert any(d["source"] == "SQLAlchemy metadata" and d["level"] == "INFO" for d in res.detail.diagnostics)


def test_models_with_no_declarative_base_or_registry_warns_and_partial() -> None:
    # models= holding no declarative base or registry: discovery failure -> WARNING and PARTIAL
    class Dummy:
        pass

    orm_facts = rules_orm.facts((Dummy(),))
    assert orm_facts["known_absent"] is False
    assert any("Dummy" in str(err) for err in orm_facts["errors"])

    table = {
        "name": "users",
        "schema": None,
        "truncated": False,
        "columns": [],
        "primaryKey": ["id"],
        "foreignKeys": [],
        "indexes": [],
    }
    source = Source(
        "primary",
        "sqlite",
        "pysqlite",
        "AVAILABLE",
        None,
        {
            "dialect": "sqlite",
            "tables": [table],
            "tableCount": 1,
            "truncated": False,
            "complete": True,
            "diagnostics": [],
            "server": {},
            "orm": orm_facts,
        },
    )
    res = report.evaluate([source])
    assert res.status == "PARTIAL"
    assert any(
        d["source"] == "SQLAlchemy metadata" and d["level"] == "WARNING" and "Dummy" in d["message"]
        for d in res.detail.diagnostics
    )


def test_postgres_relation_inventory_warning_only_on_dedicated_signal() -> None:
    # Generic incomplete (e.g. driver version or budget) does NOT trigger PostgreSQL relation inventory warning
    source_generic = Source(
        "ds",
        "postgresql",
        "psycopg2",
        "AVAILABLE",
        None,
        {
            "dialect": "postgresql",
            "tables": [],
            "tableCount": 0,
            "truncated": False,
            "complete": False,
            "diagnostics": [{"level": "WARNING", "message": "The database driver version was unavailable."}],
            "server": {},
            "orm": {"tables": []},
        },
    )
    res_generic = report.evaluate([source_generic])
    msgs = [d["message"] for d in res_generic.detail.diagnostics]
    assert not any("PostgreSQL relation inventory is incomplete" in m for m in msgs)

    # Dedicated relation_inventory_complete=False DOES trigger the warning
    source_dedicated = Source(
        "ds",
        "postgresql",
        "psycopg2",
        "AVAILABLE",
        None,
        {
            "dialect": "postgresql",
            "tables": [],
            "tableCount": 0,
            "truncated": False,
            "complete": False,
            "relation_inventory_complete": False,
            "diagnostics": [],
            "server": {},
            "orm": {"tables": []},
        },
    )
    res_dedicated = report.evaluate([source_dedicated])
    assert any("PostgreSQL relation inventory is incomplete" in d["message"] for d in res_dedicated.detail.diagnostics)


def test_complete_empty_relation_inventory_does_not_make_an_otherwise_complete_datasource_partial() -> None:
    # ported: SchemaIntrospectorTests.completeEmptyRelationInventoryDoesNotMakeAnOtherwiseCompleteDatasourcePartial
    source = Source(
        "ds",
        "postgresql",
        "psycopg2",
        "AVAILABLE",
        None,
        {
            "dialect": "postgresql",
            "tables": [],
            "tableCount": 0,
            "truncated": False,
            "complete": True,
            "diagnostics": [],
            "server": {},
            "orm": {"tables": []},
        },
    )
    evaluated = report.evaluate([source])
    assert evaluated.status == "SCANNED"
    assert evaluated.evidence["coverageComplete"] is True
    assert not any("PostgreSQL relation inventory is incomplete" in d["message"] for d in evaluated.detail.diagnostics)


def test_limitations_parity_with_bootui() -> None:
    # Limitations are strictly distinct WARNING/ERROR diagnostics, no duplicated scope note lines
    source = Source(
        "ds",
        "sqlite",
        "pysqlite",
        "AVAILABLE",
        None,
        {
            "dialect": "sqlite",
            "tables": [],
            "tableCount": 0,
            "truncated": False,
            "complete": False,
            "diagnostics": [{"level": "WARNING", "message": "A diagnostic warning"}],
            "server": {},
            "orm": {"tables": []},
        },
    )
    evaluated = report.evaluate([source])
    assert evaluated.evidence["limitations"] == ["ds: A diagnostic warning"]
    assert not any("was read only in part" in lim for lim in evaluated.evidence["limitations"])


def test_orm_discovery_error_uses_type_name_not_raw_str_exc() -> None:
    # No raw str(exc) in ORM error: use type(exc).__name__
    from sharpit.engine.collectors.database_advisor.report import _with_app_facts

    class ExplodingContext:
        @property
        def models(self) -> Any:
            raise RuntimeError("secret_db_credentials_in_traceback")

        @property
        def capture(self) -> Any:
            return type("Capture", (), {"sql_trace": None})()

    source = Source("primary", "sqlite", "pysqlite", "AVAILABLE", None, {"tables": []})
    result = _with_app_facts(ExplodingContext(), [source])  # type: ignore[arg-type]
    orm_info = result[0].catalog.get("orm", {})
    assert "secret_db_credentials_in_traceback" not in str(orm_info)
    assert "RuntimeError" in str(orm_info)


def test_masking_through_production_path(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    # Masking test through production DatabaseAdvisorService.scan path
    masker = Masker("MASKED", True, None)
    secret_pw = "super_secret_password_123"
    leak = f"Driver error connecting to postgresql://user:{secret_pw}@localhost/db"
    source = Source(
        "ds",
        "postgresql",
        "psycopg2",
        "AVAILABLE",
        None,
        {
            "dialect": "postgresql",
            "tables": [],
            "tableCount": 0,
            "truncated": False,
            "complete": False,
            "diagnostics": [{"level": "WARNING", "message": leak}],
            "server": {},
            "orm": {
                "skipped": leak,
                "known_absent": False,
                "errors": [leak],
            },
        },
    )
    service = DatabaseAdvisorService(DismissalStore(tmp_path), masker, max_retained=5)
    report_dict = service.scan([source])
    report_json = json.dumps(report_dict)

    assert secret_pw not in report_json
    assert secret_pw not in caplog.text
