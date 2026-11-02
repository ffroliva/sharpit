from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import pytest
from tests.engine.postgresql.fakes import FakePgConnection, default_rows

from sharpit.engine.collectors.postgresql import queries
from sharpit.engine.collectors.postgresql.limits import RowLimits
from sharpit.engine.collectors.postgresql.queries import checkpoint_sql, statement_sql
from sharpit.engine.collectors.postgresql.sections import (
    COLLECTORS,
    SECTION_IDS,
    DatabaseData,
    ReadBudget,
    ReadContext,
    Rows,
    collect,
    is_false,
    vacuum_override,
    vacuum_threshold,
)
from sharpit.engine.masking import MASK, Exposure, Masker

PG_URL = os.environ.get("SHARPIT_TEST_POSTGRES_URL", "")
NEEDS_PG = pytest.mark.skipif(not PG_URL, reason="requires leased PostgreSQL via SHARPIT_TEST_POSTGRES_URL")
MASKED = Masker(Exposure.MASKED, True)


def _context(
    conn: FakePgConnection,
    masker: Masker = MASKED,
    limits: RowLimits | None = None,
    clock: list[float] | None = None,
) -> ReadContext:
    now = clock if clock is not None else [0.0]
    return ReadContext(conn, masker, limits or RowLimits(), ReadBudget.start(15.0, clock=lambda: now[0]))


def _run(section_id: str, ctx: ReadContext, data: DatabaseData) -> dict[str, Any]:
    collector = {c.id: c for c in COLLECTORS}[section_id]
    return collector.collect(ctx, data)


def test_statement_collector_picks_timing_columns_from_the_extension_not_the_server() -> None:
    # ported: PostgresCollectorsTests.statementCollectorPicksTimingColumnsFromTheExtensionNotTheServer
    old = statement_sql("pg_stat_statements", False)
    new = statement_sql("pg_stat_statements", True)
    assert "s.total_time as total_time" in old
    assert "s.mean_time as mean_time" in old
    assert "total_exec_time" not in old
    assert "s.total_exec_time as total_time" in new
    assert "s.mean_exec_time as mean_time" in new


def test_statement_collector_uses_the_catalog_resolved_view_and_refuses_an_unexpected_name() -> None:
    # ported: PostgresCollectorsTests.statementCollectorUsesTheCatalogResolvedViewAndRefusesAnUnexpectedName
    assert "from monitoring.pg_stat_statements s" in statement_sql("monitoring.pg_stat_statements", True)
    assert 'from "My Schema".pg_stat_statements s' in statement_sql('"My Schema".pg_stat_statements', True)
    evil = statement_sql("evil; drop table orders --", True)
    assert "from pg_stat_statements s" in evil
    assert "drop table" not in evil
    assert "from pg_stat_statements s" in statement_sql(None, True)


def test_replication_collector_picks_the_checkpoint_view_that_exists() -> None:
    # ported: PostgresCollectorsTests.replicationCollectorPicksTheCheckpointViewThatExists
    assert "pg_stat_bgwriter" in checkpoint_sql(False)
    assert "checkpoints_req" in checkpoint_sql(False)
    assert "pg_stat_checkpointer" not in checkpoint_sql(False)
    assert "num_requested" in checkpoint_sql(True)


def test_list_queries_read_one_past_the_bound_and_report_truncation() -> None:
    # ported: PostgresCollectorsTests.listQueriesReadOnePastTheBoundAndReportTruncation
    conn = FakePgConnection().with_rows(
        "TABLES",
        {"schema_name": "public", "table_name": "orders"},
        {"schema_name": "public", "table_name": "customers"},
    )
    data = DatabaseData("primary")
    section = _run("tables", _context(conn, limits=RowLimits(max_tables=1)), data)
    assert section["status"] == "AVAILABLE"
    assert section["rowCount"] == 1
    assert section["truncated"] is True
    assert [t["table"] for t in data.tables] == ["orders"]
    assert conn.sql[-1].rstrip().endswith("limit 2")


def test_exactly_the_row_limit_is_not_reported_as_truncated() -> None:
    # ported: PostgresInsightServiceTests.exactlyTheRowLimitIsNotReportedAsTruncated
    conn = FakePgConnection().with_rows("TABLES", {"schema_name": "public", "table_name": "orders"})
    section = _run("tables", _context(conn, limits=RowLimits(max_tables=1)), DatabaseData("primary"))
    assert section["rowCount"] == 1
    assert section["truncated"] is False


def test_missing_pg_stat_statements_extension_is_skipped_with_actionable_hint() -> None:
    # ported: PostgresCollectorsTests.missingPgStatStatementsExtensionIsSkippedWithActionableHint
    conn = FakePgConnection().with_rows("EXTENSION", {"relation": None, "exec_naming": 0})
    data = DatabaseData("primary")
    section = _run("statements", _context(conn), data)
    assert section["status"] == "SKIPPED"
    assert "pg_stat_statements extension is not installed" in section["reason"]
    assert "CREATE EXTENSION pg_stat_statements" in section["hint"]
    assert data.statements == []


def test_failed_collector_queries_keep_credential_redacted_reason() -> None:
    # ported: PostgresCollectorsTests.failedCollectorQueriesKeepCredentialRedactedReason
    conn = FakePgConnection().fail("INDEXES", "permission denied for postgresql://app:secret@db/app")
    data = DatabaseData("primary")
    section = _run("indexes", _context(conn), data)
    assert section["status"] == "FAILED"
    assert "Index usage statistics could not be read" in section["reason"]
    assert "@db/app" in section["reason"]
    assert "secret" not in section["reason"]
    assert data.indexes == []


def test_collectors_populate_data_and_report_partial_subsystems_explicitly() -> None:
    # ported: PostgresCollectorsTests.collectorsPopulateDataAndReportPartialSubsystemsExplicitly
    now = datetime(2024, 1, 1, tzinfo=UTC)
    conn = (
        FakePgConnection()
        .with_rows(
            "STATEMENTS",
            {
                "query_id": "42",
                "query": "select 'secret'",
                "calls": 7,
                "total_time": 70.0,
                "mean_time": 10.0,
                "max_time": 20.0,
                "rows_returned": 7,
                "shared_blks_hit": 9,
                "shared_blks_read": 1,
            },
        )
        .with_rows(
            "INDEXES",
            {
                "schema_name": "public",
                "table_name": "orders",
                "index_name": "orders_idx",
                "scans": 1,
                "tuples_read": 2,
                "size_bytes": 3,
                "is_unique": False,
                "is_primary": False,
                "constraint_backed": False,
            },
        )
        .with_rows(
            "TABLES",
            {
                "schema_name": "public",
                "table_name": "orders",
                "total_size": 100,
                "table_size": 80,
                "index_size": 20,
                "live_tuples": 10,
                "dead_tuples": 1,
                "sequential_scans": 1,
                "sequential_tuples": 10,
                "index_scans": 9,
            },
        )
        .with_rows(
            "VACUUM",
            {
                "schema_name": "public",
                "table_name": "orders",
                "live_tuples": 10,
                "dead_tuples": 1,
                "last_vacuum": now,
                "last_autovacuum": None,
                "last_analyze": None,
                "last_autoanalyze": None,
            },
        )
        .fail("SLOTS", "permission denied for view pg_replication_slots")
    )
    data = DatabaseData("primary")
    ctx = _context(conn)
    ids = ("settings", "vital-signs", "statements", "indexes", "tables", "vacuum", "replication")
    sections = [_run(i, ctx, data) for i in ids]
    assert [s["id"] for s in sections] == list(ids)
    assert {s["status"] for s in sections} == {"AVAILABLE"}
    assert "Replication slots could not be read" in sections[6]["reason"]
    assert "permission denied" in sections[6]["reason"]
    assert data.settings != []
    assert data.vital_signs is not None
    assert data.vital_signs["databaseName"] == "app"
    assert [s["query"] for s in data.statements] == ["select '******'"]
    assert [s["cacheHitRatio"] for s in data.statements] == [0.9]
    assert [i["index"] for i in data.indexes] == ["orders_idx"]
    assert [t["sequentialScanRatio"] for t in data.tables] == [0.1]
    assert [v["vacuumThreshold"] for v in data.vacuum] == [52]
    assert [v["lastVacuum"] for v in data.vacuum] == [int(now.timestamp() * 1000)]
    assert data.replication is not None
    assert data.replication["replicationSlots"] is None


def test_a_failed_query_does_not_poison_later_sections() -> None:
    # ported: PostgresCollectorsTests.aFailedQueryDoesNotPoisonTheSectionsReadAfterIt
    conn = FakePgConnection().fail("INDEXES", "permission denied for view pg_stat_user_indexes")
    ctx = _context(conn)
    data = DatabaseData("primary")
    indexes = _run("indexes", ctx, data)
    tables = _run("tables", ctx, data)
    assert indexes["status"] == "FAILED"
    assert tables["status"] == "AVAILABLE"
    assert tables["reason"] is None


def test_vital_signs_report_the_session_breakdown_as_unknown_when_backends_are_hidden() -> None:
    # ported: PostgresCollectorsTests.vitalSignsReportTheSessionBreakdownAsUnknownWhenBackendsAreHidden
    conn = FakePgConnection().with_rows(
        "ACTIVITY",
        {"active_sessions": 1, "idle_in_transaction": 0, "blocked_sessions": 0, "longest_transaction_seconds": None},
    )
    conn.with_rows("VITALS", {**default_rows("VITALS")[0], "backends": 40})
    data = DatabaseData("primary")
    data.statistics_restricted = True
    section = _run("vital-signs", _context(conn), data)
    assert "pg_stat_activity hides the state" in section["reason"]
    assert data.vital_signs is not None
    assert data.vital_signs["activeSessions"] is None
    assert data.vital_signs["idleInTransactionSessions"] is None
    assert data.vital_signs["blockedSessions"] is None
    assert data.vital_signs["longestTransactionSeconds"] is None
    assert data.vital_signs["connections"] == 40


def _session_address(masker: Masker) -> str | None:
    data = DatabaseData("primary")
    _run("sessions", _context(FakePgConnection(), masker), data)
    return data.sessions[0]["clientAddress"] if data.sessions else "<no row>"


def _replica_address(masker: Masker) -> str | None:
    conn = FakePgConnection().with_rows(
        "REPLICAS",
        {
            "application_name": "replica",
            "client_addr": "10.0.0.7/32",
            "state": "streaming",
            "sync_state": "async",
            "sent_lag": 0,
            "flush_lag": 0,
            "replay_lag": 0,
        },
    )
    data = DatabaseData("primary")
    _run("replication", _context(conn, masker), data)
    return data.replication["replicas"][0]["clientAddress"] if data.replication else "<no row>"


def test_session_client_address_follows_the_exposure_policy() -> None:
    # ported: PostgresCollectorsTests.sessionClientAddressFollowsTheExposurePolicy
    assert _session_address(MASKED) == "127.0.0.1"
    assert _session_address(Masker(Exposure.METADATA_ONLY, True)) == MASK


def test_replica_client_address_follows_the_exposure_policy() -> None:
    # ported: PostgresCollectorsTests.replicaClientAddressFollowsTheExposurePolicy
    assert _replica_address(MASKED) == "10.0.0.7/32"
    assert _replica_address(Masker(Exposure.METADATA_ONLY, True)) == MASK


def test_setting_values_are_withheld_under_metadata_only_but_still_drive_the_rules() -> None:
    # ported: PostgresCollectorsTests.settingValuesAreWithheldUnderMetadataOnlyButStillDriveTheRules
    data = DatabaseData("primary")
    _run("settings", _context(FakePgConnection(), Masker(Exposure.METADATA_ONLY, True)), data)
    assert data.settings != []
    assert {s["value"] for s in data.settings} == {MASK}
    assert data.setting("autovacuum_vacuum_threshold") == "50"


def test_settings_exclude_the_timeouts_overridden_by_sharpit() -> None:
    # ported: PostgresCollectorsTests.settingsExcludeTheTimeoutsOverriddenByBootui
    conn = FakePgConnection()
    _run("settings", _context(conn), DatabaseData("primary"))
    assert "statement_timeout" not in queries.NOTABLE_SETTINGS
    assert "lock_timeout" not in queries.NOTABLE_SETTINGS
    assert len(conn.sql) == 1
    assert "'autovacuum_vacuum_threshold'" in conn.sql[0]
    assert "'work_mem'" in conn.sql[0]
    assert "'idle_in_transaction_session_timeout'" not in conn.sql[0]


def test_a_standby_does_not_present_an_unread_replica_list_as_an_empty_observation() -> None:
    # ported: PostgresCollectorsTests.aStandbyDoesNotPresentAnUnreadReplicaListAsAnEmptyObservation
    conn = FakePgConnection().with_rows("RECOVERY", {"in_recovery": True, "has_checkpointer": False})
    data = DatabaseData("standby")
    section = _run("replication", _context(conn), data)
    assert data.replication is not None
    assert data.replication["replicasAvailable"] is False
    assert data.replication["replicas"] == []
    assert "replica list and lag were not read" in section["reason"]
    assert "cascading replicas" in section["reason"]
    assert not any("from pg_stat_replication" in sql for sql in conn.sql)


def test_a_failed_replica_query_is_unavailable_but_an_empty_successful_query_is_available() -> None:
    # ported: PostgresCollectorsTests.aFailedReplicaQueryIsUnavailableButAnEmptySuccessfulQueryIsAvailable
    empty = DatabaseData("primary")
    _run("replication", _context(FakePgConnection()), empty)
    assert empty.replication is not None
    assert empty.replication["replicasAvailable"] is True
    failed = DatabaseData("primary")
    section = _run("replication", _context(FakePgConnection().fail("REPLICAS", "permission denied")), failed)
    assert failed.replication is not None
    assert failed.replication["replicasAvailable"] is False
    assert "Replication statistics could not be read" in section["reason"]


_KINDS = {
    "settings": "SETTINGS",
    "sessions": "SESSIONS",
    "statements": "STATEMENTS",
    "indexes": "INDEXES",
    "tables": "TABLES",
    "vacuum": "VACUUM",
    "replication": "REPLICAS",
}


@pytest.mark.parametrize("section_id", list(_KINDS))
def test_every_list_collector_preserves_rows_and_the_budget_reason(section_id: str) -> None:
    # ported: PostgresCollectorsTests.everyListCollectorPreservesRowsAndTheBudgetReason
    clock = [0.0]
    kind = _KINDS[section_id]
    row = {"name": "work_mem", "setting": "4096"}
    conn = FakePgConnection().with_rows(kind, row, row)

    def expire(index: int) -> None:
        if index == 1:
            clock[0] = 15.0

    conn.on_row[kind] = expire
    data = DatabaseData("primary")
    data.statistics_restricted = True
    section = _run(section_id, _context(conn, clock=clock), data)
    assert section["status"] == "AVAILABLE"
    assert section["rowCount"] == 1
    assert section["truncated"] is False
    assert "read budget ran out while reading" in (section["reason"] or "")
    if section_id in {"sessions", "statements", "replication"}:
        assert "pg_monitor" in section["reason"]
    if section_id == "vacuum":
        assert "settings could not be read" in section["reason"]


def test_a_budget_exhausted_before_the_first_row_does_not_produce_an_available_empty_list() -> None:
    # ported: PostgresCollectorsTests.aBudgetExhaustedBeforeTheFirstRowDoesNotProduceAnAvailableEmptyList
    clock = [0.0]
    conn = FakePgConnection().with_rows("TABLES", {"table_name": "orders"})
    conn.on_row["TABLES"] = lambda _: clock.__setitem__(0, 15.0)
    data = DatabaseData("primary")
    section = _run("tables", _context(conn, clock=clock), data)
    assert section["status"] == "FAILED"
    assert "read budget ran out while reading Table statistics" in section["reason"]
    assert section["truncated"] is False
    assert data.tables == []


def test_live_session_ages_are_measured_from_the_statement_clock() -> None:
    # ported: PostgresCollectorsTests.liveSessionAgesAreMeasuredFromTheStatementClockRatherThanTheTransactionClock
    assert "clock_timestamp()" in queries.SESSIONS_SQL
    assert "now()" not in queries.SESSIONS_SQL
    assert "clock_timestamp()" in queries.ACTIVITY_SQL
    assert "now()" not in queries.ACTIVITY_SQL


def test_the_session_list_is_scoped_to_the_database_the_panel_reports() -> None:
    # ported: PostgresCollectorsTests.theSessionListIsScopedToTheDatabaseThePanelReports
    assert "a.datname = current_database()" in queries.SESSIONS_SQL
    assert "datname = current_database()" in queries.ACTIVITY_SQL


def test_no_query_text_contains_a_percent_sign() -> None:
    # derived: exec_driver_sql hands the text to psycopg, which reads % as a placeholder
    texts = [v for k, v in vars(queries).items() if k.endswith("_SQL") and isinstance(v, str)]
    texts += [statement_sql("pg_stat_statements", True), checkpoint_sql(True), checkpoint_sql(False)]
    assert len(texts) >= 10
    assert [t for t in texts if "%" in t] == []


def test_vacuum_due_honours_per_table_reloptions_overrides() -> None:
    # ported: PostgresHelpersTests.vacuumDueHonoursPerTableReloptionsOverrides
    assert vacuum_override("10", 50.0) == 10.0
    assert vacuum_override(None, 50.0) == 50.0
    assert vacuum_override("not-a-number", 50.0) == 50.0
    assert is_false("false") is True
    assert is_false("off") is True
    assert is_false("n") is True
    assert is_false("0") is True
    assert is_false("true") is False
    assert is_false(None) is False
    assert is_false("o") is False


def test_vacuum_threshold_floors_so_the_comparison_matches_postgresql() -> None:
    # ported: PostgresHelpersTests.vacuumThresholdFloorsSoTheComparisonMatchesPostgreSql
    assert vacuum_threshold(5000, 50.0, 0.19992, -1.0) == 1049
    assert vacuum_threshold(1000, 50.0, 0.2, -1.0) == 250
    assert vacuum_threshold(None, 50.0, 0.2, -1.0) is None


def test_vacuum_threshold_honours_the_postgresql_18_cap() -> None:
    # ported: PostgresHelpersTests.vacuumThresholdHonoursThePostgreSql18Cap
    assert vacuum_threshold(1_000_000_000, 50.0, 0.2, 100_000_000.0) == 100_000_000
    assert vacuum_threshold(1_000_000_000, 50.0, 0.2, -1.0) == 200_000_050


def test_rows_distinguish_empty_available_from_failed_and_copy_rows() -> None:
    # ported: PostgresHelpersTests.rowsDistinguishEmptyAvailableFromFailedAndCopyRows
    mutable = ["one"]
    rows = Rows.of(mutable, truncated=True)
    mutable.append("two")
    assert rows.rows == ["one"]
    assert rows.available is True
    assert rows.truncated is True
    assert Rows.failed("refused").available is False
    assert Rows.partial([], "budget").available is False
    assert Rows.partial(["one"], "budget").available is True


def test_collect_probes_the_role_then_runs_every_section_in_order() -> None:
    # ported: PostgresInsightServiceTests.aRoleThatCannotReadOtherBackendsDegradesTheSessionListInsteadOfLookingQuiet
    conn = FakePgConnection().with_rows("ROLE", {"role_name": "app", "monitoring": False})
    data = collect(conn, MASKED, RowLimits(), ReadBudget.start(15.0))
    assert data.role == "app"
    assert data.statistics_restricted is True
    assert [s["id"] for s in data.sections] == [c.id for c in COLLECTORS]
    assert sorted(c.id for c in COLLECTORS) == sorted(SECTION_IDS)
    sessions = data.section("sessions")
    assert sessions is not None
    assert "pg_monitor" in (sessions["reason"] or "")


def test_an_exhausted_budget_skips_the_remaining_sections() -> None:
    # ported: PostgresInsightServiceTests.anExhaustedReadBudgetIsReportedInsteadOfLookingLikeACleanRead
    clock = [0.0]
    conn = FakePgConnection()
    conn.on_row["VITALS"] = lambda _: clock.__setitem__(0, 15.0)
    data = collect(conn, MASKED, RowLimits(), ReadBudget.start(15.0, clock=lambda: clock[0]))
    skipped = [s["id"] for s in data.sections if s["status"] == "SKIPPED"]
    assert skipped == ["sessions", "statements", "indexes", "tables", "vacuum", "replication"]
    assert {s["reason"] for s in data.sections[2:]} == {"The read budget ran out before this section was read."}


@NEEDS_PG
def test_sections_on_real_server() -> None:
    import asyncio  # noqa: PLC0415

    import sqlalchemy as sa  # noqa: PLC0415

    from sharpit.engine.sqla import run_db_read  # noqa: PLC0415

    url = PG_URL.replace("postgresql://", "postgresql+psycopg://", 1) if "+" not in PG_URL.split("://")[0] else PG_URL
    engine = sa.create_engine(url)
    try:
        data = asyncio.run(
            run_db_read(
                engine,
                lambda conn: collect(conn, MASKED, RowLimits(), ReadBudget.start(15.0)),
                5.0,
                wall_timeout=15.0,
                read_only=True,
            )
        )
    finally:
        engine.dispose()
    assert [s["id"] for s in data.sections] == [c.id for c in COLLECTORS]
    bad = [s for s in data.sections if s["status"] == "FAILED" or (s["status"] == "SKIPPED" and not s["reason"])]
    assert bad == []
    assert data.vital_signs is not None
    assert data.vital_signs["databaseName"]
