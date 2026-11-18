"""Incomplete Database Advisor discovery (BootUI 2.4.0 #1600 parity).

Incomplete evidence (missing driver metadata, failed ORM model discovery, or cut/failed PostgreSQL
relation inventory) is reported as WARNING diagnostics and never reads as a clean scan (SCANNED),
keeping the report status PARTIAL. Absent SQLAlchemy ORM models remain a neutral INFO skip.
"""

from __future__ import annotations

from typing import Any

import pytest

from sharpit.engine.collectors.database_advisor import report, rules_orm
from sharpit.engine.collectors.database_advisor.catalog import Source
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


def test_missing_driver_metadata_is_reported_as_incomplete_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: SchemaIntrospectorTests.missingDriverMetadataIsReportedAsIncompleteEvidence
    engine = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    with engine.connect() as conn:
        monkeypatch.setattr(conn.dialect.dbapi, "__version__", None, raising=False)
        monkeypatch.setattr(conn.engine, "url", None)

        out = _catalog(conn)

    assert out["complete"] is False
    assert any(d["level"] == "WARNING" and "driver version" in d["message"] for d in out["diagnostics"])
    assert any(d["level"] == "WARNING" and "JDBC URL" in d["message"] for d in out["diagnostics"])


def test_null_driver_name_is_reported_as_incomplete_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: SchemaIntrospectorTests.nullDriverNameIsReportedAsIncompleteEvidence
    engine = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    with engine.connect() as conn:
        monkeypatch.setattr(conn.dialect, "driver", None)

        out = _catalog(conn)

    assert out["complete"] is False
    assert any(d["level"] == "WARNING" and "driver name" in d["message"] for d in out["diagnostics"])


def test_null_driver_version_is_reported_as_incomplete_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: SchemaIntrospectorTests.nullDriverVersionIsReportedAsIncompleteEvidence
    engine = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    with engine.connect() as conn:
        monkeypatch.setattr(conn.dialect.dbapi, "__version__", None, raising=False)

        out = _catalog(conn)

    assert out["complete"] is False
    assert any(d["level"] == "WARNING" and "driver version" in d["message"] for d in out["diagnostics"])


def test_a_null_url_is_a_warning_and_makes_evidence_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: SchemaIntrospectorDriverEvidenceTests.aNullUrlIsAWarningAndMakesEvidenceIncomplete
    engine = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    with engine.connect() as conn:
        monkeypatch.setattr(conn.engine, "url", None)

        out = _catalog(conn)

    assert out["complete"] is False
    assert any(d["level"] == "WARNING" and "no JDBC URL" in d["message"] for d in out["diagnostics"])


def test_distinguishes_absent_jpa_from_a_zero_entity_discovery_failure() -> None:
    # ported: DatabaseAdvisorScannerTests.distinguishesAbsentJpaFromAZeroEntityDiscoveryFailure
    source_clean = Source("primary", "sqlite", "pysqlite", "AVAILABLE", None, {
        "dialect": "sqlite",
        "tables": [{"name": "users", "schema": None, "truncated": False, "columns": [], "primaryKey": ["id"], "foreignKeys": [], "indexes": []}],
        "tableCount": 1,
        "truncated": False,
        "complete": True,
        "diagnostics": [],
        "server": {},
        "orm": rules_orm.facts(()),
    })
    absent = report.evaluate([source_clean])
    assert any(d["source"] == "SQLAlchemy metadata" and d["level"] == "INFO" for d in absent.detail.diagnostics)
    assert absent.status == "SCANNED"

    source_failed = Source("primary", "sqlite", "pysqlite", "AVAILABLE", None, {
        "dialect": "sqlite",
        "tables": [{"name": "users", "schema": None, "truncated": False, "columns": [], "primaryKey": ["id"], "foreignKeys": [], "indexes": []}],
        "tableCount": 1,
        "truncated": False,
        "complete": True,
        "diagnostics": [],
        "server": {},
        "orm": {"skipped": "metamodel unavailable", "known_absent": False, "errors": ["metamodel unavailable"]},
    })
    failed = report.evaluate([source_failed])
    assert failed.status == "PARTIAL"
    assert failed.evidence["coverageComplete"] is False
    assert any(d["source"] == "SQLAlchemy metadata" and d["level"] == "WARNING" for d in failed.detail.diagnostics)

