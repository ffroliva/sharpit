"""``postgresql_report`` / ``refresh_postgresql`` (port of BootUI ``PostgresInsightServiceTests``).

The PostgreSQL engines are ``FakePgEngine``s driven through the real ``sqla.run_db_read(read_only=True)``, so every
read below also passes the read-only pin of ``bounded_read_only``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from tests.engine.postgresql.fakes import FakePgConnection, FakePgEngine, FakeRegistry, default_rows

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.postgresql import service
from sharpit.engine.collectors.postgresql.service import OPERATION, postgresql_report, refresh_postgresql
from sharpit.engine.context import SharpitContext
from sharpit.engine.masking import MASK
from sharpit.engine.singleflight import ActionBusy, SingleFlight
from sharpit.engine.sqla import READ_ONLY_REFUSED
from sharpit.settings import load_settings

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
NO_PG = (
    "No PostgreSQL datasource was found. This panel reads PostgreSQL's own statistics views, "
    "so it has nothing to report for other database products."
)


class _Introspector:
    def app_info(self) -> Any:
        return None

    def routes(self) -> list[Any]:
        return []

    def providers(self) -> list[Any]:
        return []


def _ctx(*engines: tuple[str, Any], **options: Any) -> SharpitContext:
    ctx = SharpitContext(load_settings({"config_scan": False, **options}, {}), ACTIVATION, _Introspector())
    ctx.capture.engine_registry = FakeRegistry(*engines) if engines else None  # type: ignore[assignment]
    return ctx


def _read(ctx: SharpitContext) -> dict[str, Any]:
    return asyncio.run(refresh_postgresql(ctx))


def _section(database: dict[str, Any], section_id: str) -> dict[str, Any]:
    return next(s for s in database["sections"] if s["id"] == section_id)


def test_initial_report_touches_neither_discovery_nor_database() -> None:
    # ported: PostgresInsightServiceTests.initialReportTouchesNeitherDiscoveryNorDatabase
    engine = FakePgEngine()
    ctx = _ctx(("primary", engine))
    report = postgresql_report(ctx)
    assert report["status"] == "NOT_READ"
    assert report["readAt"] is None
    assert report["databases"] == []
    assert ctx.capture.engine_registry.calls == 0  # type: ignore[union-attr]
    assert engine.connects == 0


def test_report_keys_match_the_bootui_records() -> None:
    # ported: PostgresqlSerializationTest (PostgresInsightReport / PostgresDatabaseDto record components)
    report = _read(_ctx(("primary", FakePgEngine())))
    assert list(report) == [
        "localOnly",
        "disclaimer",
        "status",
        "message",
        "readAt",
        "databasesRead",
        "truncated",
        "databases",
        "diagnostics",
        "limitations",
    ]
    assert list(report["databases"][0]) == [
        "name",
        "databaseName",
        "serverVersion",
        "serverMajorVersion",
        "role",
        "monitoringRole",
        "status",
        "message",
        "vitalSigns",
        "sections",
        "sessions",
        "statements",
        "indexes",
        "tables",
        "vacuum",
        "replication",
        "settings",
        "changes",
        "truncated",
    ]


def test_a_complete_read_is_read() -> None:
    # ported: PostgresInsightServiceTests.readsEverySectionFromAHealthyServer
    engine = FakePgEngine()
    report = _read(_ctx(("primary", engine)))
    database = report["databases"][0]
    assert report["status"] == "READ"
    assert report["message"] is None
    assert report["databasesRead"] == 1
    assert database["status"] == "READ"
    assert database["serverVersion"] == "16.4"
    assert database["serverMajorVersion"] == 16
    assert database["role"] == "sharpit"
    assert database["monitoringRole"] is True
    assert engine.conn.sql[0] == "SET TRANSACTION READ ONLY"
    assert engine.conn.rolled_back == 1


def test_no_engine_is_disabled() -> None:
    # ported: PostgresInsightServiceTests.noDataSourceIsDisabled
    report = _read(_ctx())
    assert report["status"] == "DISABLED"
    assert report["message"] == NO_PG
    assert report["databases"] == []


def test_non_postgres_engine_is_skipped() -> None:
    # ported: PostgresInsightServiceTests.nonPostgresDatasourceIsReportedHonestlyWithoutADatabaseReport
    engine = FakePgEngine(FakePgConnection("sqlite"))
    report = _read(_ctx(("sqlite:///app.db", engine)))
    assert report["status"] == "DISABLED"
    assert report["message"] == NO_PG
    assert report["diagnostics"] == [
        {
            "source": "sqlite:///app.db",
            "level": "INFO",
            "message": "Skipped: this datasource is SQLite, not PostgreSQL.",
        }
    ]
    assert engine.connects == 0


def test_datasource_that_refuses_connections_produces_error_and_diagnostic() -> None:
    # ported: PostgresInsightServiceTests.datasourceThatRefusesConnectionsProducesErrorAndDiagnostic
    engine = FakePgEngine(refuse="connection refused for postgresql://app:secret@db/app")
    report = _read(_ctx(("primary", engine)))
    assert report["status"] == "ERROR"
    assert report["message"] == "No PostgreSQL datasource could be read."
    assert [d["status"] for d in report["databases"]] == ["ERROR"]
    assert [d["level"] for d in report["diagnostics"]] == ["ERROR"]
    assert "connection refused" in report["diagnostics"][0]["message"]
    assert "secret" not in report["diagnostics"][0]["message"]


def test_an_autocommit_connection_is_skipped_before_any_catalog_sql() -> None:
    # ported: PostgresInsightServiceTests.aDatasourceConnectionAlreadyInManualCommitModeIsSkipped
    # (sharpit analogue: an AUTOCOMMIT connection reports transaction_read_only 'off' after the pin)
    engine = FakePgEngine()
    engine.conn.read_only_setting = "off"
    report = _read(_ctx(("primary", engine)))
    database = report["databases"][0]
    assert database["status"] == "ERROR"
    assert database["message"] == READ_ONLY_REFUSED
    assert database["sections"] == []
    assert [d["message"] for d in report["diagnostics"]] == [READ_ONLY_REFUSED]
    assert [sql for sql in engine.conn.sql if "pg_" in sql and "current_setting" not in sql] == []


def test_configured_row_limits_reach_every_collector() -> None:
    # ported: PostgresInsightServiceTests.configuredRowLimitsReachEveryCollector
    engine = FakePgEngine()
    options = {
        "postgresql_max_sessions": 3,
        "postgresql_max_statements": 4,
        "postgresql_max_indexes": 5,
        "postgresql_max_tables": 6,
        "postgresql_max_vacuum_tables": 7,
        "postgresql_max_replicas": 8,
        "postgresql_max_settings": 9,
    }
    _read(_ctx(("primary", engine), **options))
    limits = sorted(
        int(sql.rsplit(None, 1)[1]) for sql in engine.conn.sql if sql.rstrip().rsplit(None, 2)[-2] == "limit"
    )
    assert limits == [4, 5, 6, 7, 8, 9, 10]


def test_statement_text_goes_through_exposure_policy() -> None:
    # ported: PostgresInsightServiceTests.statementTextGoesThroughExposurePolicy
    row = {"query_id": "1", "query": "select * from users where password = 'hunter2'", "calls": 1}
    masked = FakePgEngine()
    masked.conn.with_rows("STATEMENTS", row)
    hidden = FakePgEngine()
    hidden.conn.with_rows("STATEMENTS", row)
    shown = _read(_ctx(("primary", masked)))["databases"][0]["statements"]
    withheld = _read(_ctx(("primary", hidden), expose_values="METADATA_ONLY"))["databases"][0]["statements"]
    assert [s["query"] for s in shown] == ["select * from users where password = '******'"]
    assert [s["query"] for s in withheld] == [MASK]


def test_a_role_that_cannot_read_other_backends_degrades_the_session_list_instead_of_looking_quiet() -> None:
    # ported: PostgresInsightServiceTests.aRoleThatCannotReadOtherBackendsDegradesTheSessionListInsteadOfLookingQuiet
    engine = FakePgEngine()
    engine.conn.with_rows("ROLE", {"role_name": "app", "monitoring": False})
    report = _read(_ctx(("primary", engine)))
    database = report["databases"][0]
    assert database["monitoringRole"] is False
    assert database["status"] == "PARTIAL"
    assert "pg_monitor" in _section(database, "sessions")["reason"]
    assert report["status"] == "PARTIAL"


def test_an_absent_statement_extension_is_reported_as_a_skipped_section_rather_than_an_empty_one() -> None:
    # ported: PostgresInsightServiceTests.anAbsentStatementExtensionIsReportedAsASkippedSectionRatherThanAnEmptyOne
    engine = FakePgEngine()
    engine.conn.with_rows("EXTENSION", {"relation": None, "exec_naming": 0})
    report = _read(_ctx(("primary", engine)))
    database = report["databases"][0]
    assert _section(database, "statements")["status"] == "SKIPPED"
    assert _section(database, "indexes")["status"] == "AVAILABLE"
    assert database["status"] == "PARTIAL"
    assert any(text.startswith("primary/statements: The pg_stat_statements") for text in report["limitations"])
    assert {"source": "primary/statements", "level": "WARNING"} in [
        {"source": d["source"], "level": d["level"]} for d in report["diagnostics"]
    ]


def test_an_exhausted_read_budget_is_reported_instead_of_looking_like_a_clean_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ported: PostgresInsightServiceTests.anExhaustedReadBudgetIsReportedInsteadOfLookingLikeACleanRead
    clock = [0.0]
    monkeypatch.setattr(service, "_clock", lambda: clock[0])
    first = FakePgEngine()
    first.conn.on_row["VITALS"] = lambda _: clock.__setitem__(0, 100.0)
    second = FakePgEngine()
    report = _read(_ctx(("first", first), ("second", second)))
    assert report["status"] == "PARTIAL"
    assert report["message"] == "The read budget ran out before every datasource was read; see the diagnostics."
    assert _section(report["databases"][0], "tables")["status"] == "SKIPPED"
    assert second.connects == 0
    assert {
        "source": "second",
        "level": "WARNING",
        "message": "The read budget ran out before this datasource was read.",
    } in report["diagnostics"]
    assert "second: The read budget ran out before this datasource was read." in report["limitations"]


def _vitals(**changes: Any) -> dict[str, Any]:
    return {**default_rows("VITALS")[0], **changes}


def test_in_memory_previous_read_delta_appears_only_from_second_read_and_is_not_persisted() -> None:
    # ported: PostgresInsightServiceTests.inMemoryPreviousReadDeltaAppearsOnlyFromSecondReadAndIsNotPersisted
    engine = FakePgEngine()
    ctx = _ctx(("primary", engine))
    assert _read(ctx)["databases"][0]["changes"] == []
    engine.conn.with_rows("VITALS", _vitals(deadlocks=3))
    changes = _read(ctx)["databases"][0]["changes"]
    assert changes == [{"metric": "Deadlocks", "previous": "0", "current": "3", "direction": "UP"}]
    assert _read(_ctx(("primary", engine)))["databases"][0]["changes"] == []


def test_a_partial_read_keeps_the_baseline_of_the_sections_it_could_not_read() -> None:
    # ported: PostgresInsightServiceTests.aPartialReadKeepsTheBaselineOfTheSectionsItCouldNotRead
    engine = FakePgEngine()
    ctx = _ctx(("primary", engine))
    _read(ctx)
    engine.conn.fail("VITALS", "permission denied for view pg_stat_database")
    assert _read(ctx)["databases"][0]["changes"] == []
    engine.conn.failures.clear()
    engine.conn.with_rows("VITALS", _vitals(deadlocks=5))
    changes = _read(ctx)["databases"][0]["changes"]
    assert [(c["metric"], c["previous"], c["current"]) for c in changes] == [("Deadlocks", "0", "5")]


def test_get_returns_the_last_read_report_after_a_read() -> None:
    # ported: PostgresqlControllerTests.getReturnsTheLastReadReportAfterARead
    ctx = _ctx(("primary", FakePgEngine()))
    report = _read(ctx)
    assert postgresql_report(ctx) == report


def test_concurrent_read_is_busy() -> None:
    ctx = _ctx(("primary", FakePgEngine()))
    release = ctx.lazy(f"singleflight:{OPERATION}", SingleFlight).try_acquire("other")
    assert release is not None
    with pytest.raises(ActionBusy):
        _read(ctx)
    release()
    assert _read(ctx)["status"] == "READ"
