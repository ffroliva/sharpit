"""Vendor rules over the vendor facts (plan A-dbadv-2 Task 2): hand-made facts, plus leased-server reads.

The leased tests need ``SHARPIT_TEST_POSTGRES_URL`` (``postgresql+psycopg://...``) or ``SHARPIT_TEST_MYSQL_URL``
(``mysql://user:pass@host:port/db``, read with pymysql) whose user may create tables; without them they skip (the
coordinator runs them on leased servers; a skip is ``unverified``).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from typing import Any

import pytest

from sharpit.engine import sqla
from sharpit.engine.collectors.database_advisor import rules_vendor
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Source
from sharpit.engine.masking import Masker
from sharpit.engine.sqla import inspect as sqla_inspect
from sharpit.engine.sqla.inspect import CatalogBounds

PG_URL = os.environ.get("SHARPIT_TEST_POSTGRES_URL", "")
MYSQL_URL = os.environ.get("SHARPIT_TEST_MYSQL_URL", "")
PG_IDS = ("DB-PG-001", "DB-PG-002", "DB-PG-003", "DB-PG-004", "DB-PG-005", "DB-PG-006", "DB-SERVER-001")
MYSQL_IDS = ("DB-SCHEMA-010", "DB-MYSQL-001", "DB-MYSQL-002", "DB-MYSQL-003", "DB-MYSQL-004", "DB-SERVER-008")


def _fact(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"rows": list(rows), "truncated": False}


def _source(dialect: str, **facts: dict[str, Any]) -> Source:
    catalog = {"dialect": dialect, "tables": [], "truncated": False, "complete": True, "vendor": facts}
    return Source("db", dialect, "driver", "AVAILABLE", None, catalog)


def _check(rule_id: str, source: Source) -> Outcome:
    return next(r for r in rules_vendor.RULES if r.definition.id == rule_id).check(source)


def _targets(outcome: Outcome) -> list[str] | str:
    return [target for target, _message, _identity in outcome] if isinstance(outcome, list) else outcome


def _sequence(last: int | None, low: int = 1, high: int = 100, step: int = 1) -> dict[str, Any]:
    return {"seq": "s", "last_value": last, "min_value": low, "max_value": high, "increment_by": step}


def test_unsupported_dialect_skips_vendor_rules() -> None:
    sqlite = Source("db", "sqlite", "pysqlite", "AVAILABLE", None, {"tables": [], "vendor": {}})
    postgres = _source("postgresql")
    mysql_server = _source("mysql")

    assert all(isinstance(rule.check(sqlite), str) for rule in rules_vendor.RULES)
    assert all(isinstance(_check(rule_id, postgres), str) for rule_id in MYSQL_IDS)
    assert all(isinstance(_check(rule_id, mysql_server), str) for rule_id in PG_IDS)


def test_vendor_rules_skip_when_the_vendor_catalog_was_not_read() -> None:
    source = Source("db", "postgresql", "psycopg", "AVAILABLE", None, {"tables": []})

    assert isinstance(_check("DB-PG-005", source), str)


def test_vendor_rule_skips_a_failed_catalog_read() -> None:
    source = _source("postgresql", unlogged={"error": "permission denied for view pg_class"})

    assert isinstance(_check("DB-PG-005", source), str)


def test_truncated_vendor_inventory_is_not_treated_as_complete() -> None:
    # ported: VendorCatalogReaderTests.postgresServerSettingsRespectTheRowBound
    source = _source("mysql", utf8mb3={"rows": [], "truncated": True})

    assert isinstance(_check("DB-MYSQL-002", source), str)


def test_schema_010_invisible_index() -> None:
    source = _source("mysql", invisible=_fact({"tbl": "orders", "idx": "ix_code"}))

    assert _targets(_check("DB-SCHEMA-010", source)) == ["db/orders.ix_code"]


def test_pg_001_invalid_index() -> None:
    source = _source("postgresql", invalidIndexes=_fact({"tbl": "orders", "idx": "ix_code"}))

    assert _targets(_check("DB-PG-001", source)) == ["db/orders.ix_code"]


def test_pg_002_sequence_nearing_exhaustion() -> None:
    source = _source("postgresql", sequences=_fact(_sequence(90)))

    assert _targets(_check("DB-PG-002", source)) == ["db/s"]


def test_pg_002_descending_sequence_nearing_exhaustion() -> None:
    source = _source("postgresql", sequences=_fact(_sequence(-90, low=-100, high=-1, step=-1)))

    assert _targets(_check("DB-PG-002", source)) == ["db/s"]


def test_pg_002_unread_or_young_sequence_is_not_reported() -> None:
    source = _source("postgresql", sequences=_fact(_sequence(None), _sequence(10)))

    assert _check("DB-PG-002", source) == []


def test_pg_003_not_valid_constraint() -> None:
    source = _source("postgresql", notValid=_fact({"tbl": "orders", "name": "orders_total_check"}))

    assert _targets(_check("DB-PG-003", source)) == ["db/orders.orders_total_check"]


def test_pg_003_reports_not_null_constraints_as_not_null() -> None:
    # ported: DatabaseAdvisorVendorRulesTests.postgresUnvalidatedConstraintRuleReportsForeignKeyCheckAndNotNullConstraints  # noqa: E501
    source = _source(
        "postgresql", notValid=_fact({"tbl": "orders", "name": "orders_customer_id_not_null", "type": "n"})
    )

    outcome = _check("DB-PG-003", source)

    assert "not-null constraint" in outcome[0][1]


def test_pg_004_published_table_without_usable_replica_identity() -> None:
    rows = (
        {"tbl": "a", "identity": "d", "has_pk": False, "has_index": False},
        {"tbl": "b", "identity": "d", "has_pk": True, "has_index": False},
        {"tbl": "c", "identity": "n", "has_pk": True, "has_index": False},
        {"tbl": "d", "identity": "i", "has_pk": True, "has_index": False},
        {"tbl": "e", "identity": "f", "has_pk": False, "has_index": False},
    )
    source = _source("postgresql", replicaIdentity=_fact(*rows))

    assert _targets(_check("DB-PG-004", source)) == ["db/a", "db/c", "db/d"]


def test_pg_005_unlogged_table() -> None:
    source = _source("postgresql", unlogged=_fact({"tbl": "cache"}))

    assert _targets(_check("DB-PG-005", source)) == ["db/cache"]


def test_mysql_001_non_transactional_engine() -> None:
    source = _source("mysql", engines=_fact({"tbl": "logs", "engine": "MyISAM"}, {"tbl": "orders", "engine": "InnoDB"}))

    assert _targets(_check("DB-MYSQL-001", source)) == ["db/logs"]


def test_mysql_002_utf8mb3_table_and_column() -> None:
    source = _source("mariadb", utf8mb3=_fact({"tbl": "orders", "col": None}, {"tbl": "users", "col": "name"}))

    assert _targets(_check("DB-MYSQL-002", source)) == ["db/orders", "db/users.name"]


def test_mysql_003_auto_increment_nearing_exhaustion() -> None:
    rows = (
        {"tbl": "a", "col": "id", "column_type": "tinyint", "next_value": 120},
        {"tbl": "b", "col": "id", "column_type": "tinyint unsigned", "next_value": 120},
        {"tbl": "c", "col": "id", "column_type": "bigint unsigned", "next_value": 18000000000000000000},
    )
    source = _source("mysql", autoIncrement=_fact(*rows))

    assert _targets(_check("DB-MYSQL-003", source)) == ["db/a.id", "db/c.id"]


def test_server_001_idle_in_transaction_without_limit() -> None:
    source = _source("postgresql", settings=_fact({"name": "idle_in_transaction_session_timeout", "setting": "0"}))

    assert _targets(_check("DB-SERVER-001", source)) == ["db/idle_in_transaction_session_timeout"]


def test_server_001_unreported_setting_skips() -> None:
    source = _source("postgresql", settings=_fact({"name": "statement_timeout", "setting": "0"}))

    assert isinstance(_check("DB-SERVER-001", source), str)


# --- leased servers (coordinator) -----------------------------------------------------------------------------------


def _read(url: str) -> dict[str, Any]:
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine(url, pool_size=1, max_overflow=0)
    try:
        return asyncio.run(
            sqla.run_db_read(
                engine,
                lambda c: rules_vendor.read_vendor(c, CatalogBounds(), Masker("MASKED", True, None)),
                5.0,
                read_only=True,
            )
        )
    finally:
        engine.dispose()


def _ddl(url: str, *statements: str) -> None:
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            for statement in statements:
                conn.exec_driver_sql(statement)
    finally:
        engine.dispose()


@pytest.mark.needs_sqlalchemy
@pytest.mark.skipif(not PG_URL, reason="requires a leased PostgreSQL via SHARPIT_TEST_POSTGRES_URL")
def test_pg_vendor_rules_on_a_leased_server() -> None:
    _ddl(PG_URL, "DROP TABLE IF EXISTS sharpit_dbadv2_cache", "DROP TABLE IF EXISTS sharpit_dbadv2_orders",
         "DROP SEQUENCE IF EXISTS sharpit_dbadv2_seq",
         "CREATE UNLOGGED TABLE sharpit_dbadv2_cache (id INTEGER PRIMARY KEY)",
         "CREATE TABLE sharpit_dbadv2_orders (id INTEGER PRIMARY KEY, total INTEGER)",
         "INSERT INTO sharpit_dbadv2_orders VALUES (1, -1)",
         "ALTER TABLE sharpit_dbadv2_orders ADD CONSTRAINT sharpit_dbadv2_total CHECK (total >= 0) NOT VALID",
         "CREATE SEQUENCE sharpit_dbadv2_seq MAXVALUE 100", "SELECT setval('sharpit_dbadv2_seq', 95)")  # fmt: skip
    try:
        found = _read(PG_URL)
        source = _source("postgresql", **found)

        assert [name for name, fact in found.items() if "error" in fact] == []
        assert "db/sharpit_dbadv2_cache" in _targets(_check("DB-PG-005", source))
        assert "db/sharpit_dbadv2_orders.sharpit_dbadv2_total" in _targets(_check("DB-PG-003", source))
        assert "db/sharpit_dbadv2_seq" in _targets(_check("DB-PG-002", source))
        assert isinstance(_check("DB-SERVER-002", source), list)
    finally:
        _ddl(PG_URL, "DROP TABLE IF EXISTS sharpit_dbadv2_cache", "DROP TABLE IF EXISTS sharpit_dbadv2_orders",
             "DROP SEQUENCE IF EXISTS sharpit_dbadv2_seq")  # fmt: skip


@pytest.mark.needs_sqlalchemy
@pytest.mark.skipif(not MYSQL_URL, reason="requires a leased MySQL via SHARPIT_TEST_MYSQL_URL")
def test_mysql_vendor_rules_on_a_leased_server() -> None:
    url = MYSQL_URL.replace("mysql://", "mysql+pymysql://", 1)
    _ddl(url, "DROP TABLE IF EXISTS sharpit_dbadv2_logs",
         "CREATE TABLE sharpit_dbadv2_logs (id INTEGER PRIMARY KEY) ENGINE=MyISAM CHARACTER SET utf8mb3")  # fmt: skip
    try:
        found = _read(url)
        source = _source("mysql", **found)

        assert [name for name, fact in found.items() if "error" in fact] == []
        assert "db/sharpit_dbadv2_logs" in _targets(_check("DB-MYSQL-001", source))
        assert "db/sharpit_dbadv2_logs" in _targets(_check("DB-MYSQL-002", source))
    finally:
        _ddl(url, "DROP TABLE IF EXISTS sharpit_dbadv2_logs")


def test_postgres_empty_partitioned_table_is_reported() -> None:
    # ported: DatabaseAdvisorVendorRulesTests.postgresEmptyPartitionedTableRuleReportsEmptyPartitionedParent
    source = _source("postgresql", emptyPartitioned=_fact({"tbl": "empty_metrics"}))

    outcome = _check("DB-PG-006", source)
    assert _targets(outcome) == ["db/empty_metrics"]
    assert "empty_metrics" in outcome[0][1]
    assert "no attached partitions in pg_inherits" in outcome[0][1]
    assert "every INSERT into it will fail" in outcome[0][1]

    healthy = _source("postgresql", emptyPartitioned=_fact())
    assert _targets(_check("DB-PG-006", healthy)) == []


def test_postgres_empty_partitioned_table_skips_before_postgres_10() -> None:
    # ported: DatabaseAdvisorVendorRulesTests
    #   .postgresEmptyPartitionedTableRuleSkipsBeforePostgres10WithoutCoverageWarning
    pg96 = Source(
        "pg",
        "postgresql",
        "driver",
        "AVAILABLE",
        None,
        {"vendor": {"emptyPartitioned": _fact({"tbl": "empty_metrics"})}, "server": {"server_version": "9.6"}},
    )
    outcome = _check("DB-PG-006", pg96)
    assert isinstance(outcome, str)
    assert "PostgreSQL 10 or later" in outcome


def test_mysql_strict_sql_mode_fires_when_not_strict() -> None:
    # ported: DatabaseAdvisorServerRulesTests.strictSqlModeFiresWhenNeitherStrictTransTablesNorStrictAllTablesIsPresent
    for dialect in ("mysql", "mariadb"):
        empty = Source("ordersDb", dialect, "driver", "AVAILABLE", None, {"server": {"sql_mode": ""}})
        empty_outcome = _check("DB-SERVER-008", empty)
        assert _targets(empty_outcome) == ["ordersDb/sql_mode"]
        assert "ordersDb" in empty_outcome[0][1]
        assert "`sql_mode` is empty" in empty_outcome[0][1]
        assert "STRICT_TRANS_TABLES" in empty_outcome[0][1]

        non_strict = Source(
            "ordersDb",
            dialect,
            "driver",
            "AVAILABLE",
            None,
            {"server": {"sql_mode": "ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION"}},
        )
        non_strict_outcome = _check("DB-SERVER-008", non_strict)
        assert _targets(non_strict_outcome) == ["ordersDb/sql_mode"]
        assert "`ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION`" in non_strict_outcome[0][1]

        strict_trans = Source(
            "ordersDb",
            dialect,
            "driver",
            "AVAILABLE",
            None,
            {"server": {"sql_mode": "ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES"}},
        )
        assert _targets(_check("DB-SERVER-008", strict_trans)) == []

        strict_all = Source(
            "ordersDb",
            dialect,
            "driver",
            "AVAILABLE",
            None,
            {"server": {"sql_mode": "STRICT_ALL_TABLES"}},
        )
        assert _targets(_check("DB-SERVER-008", strict_all)) == []

    bad_token = Source(
        "ordersDb",
        "mysql",
        "driver",
        "AVAILABLE",
        None,
        {"server": {"sql_mode": "bad token"}},
    )
    outcome_bad = _check("DB-SERVER-008", bad_token)
    assert isinstance(outcome_bad, str)


def test_mysql_unenforced_check_constraints_is_reported() -> None:
    # ported: DatabaseAdvisorVendorRulesTests
    #   .mysqlUnenforcedCheckConstraintRuleReportsNotEnforcedBaseTableChecksAndSkipsMariaDbAndOldMySql
    source = Source(
        "ds",
        "mysql",
        "driver",
        "AVAILABLE",
        None,
        {
            "server": {"server_version": "8.4.0"},
            "vendor": {
                "unenforcedChecks": _fact({"tbl": "orders", "name": "chk_orders_total"}),
            },
        },
    )
    violation = _check("DB-MYSQL-004", source)
    assert _targets(violation) == ["ds/orders.chk_orders_total"]
    assert "chk_orders_total" in violation[0][1]
    assert "orders" in violation[0][1]
    assert "NOT ENFORCED" in violation[0][1]

    clean = Source(
        "ds",
        "mysql",
        "driver",
        "AVAILABLE",
        None,
        {
            "server": {"server_version": "8.4.0"},
            "vendor": {"unenforcedChecks": _fact()},
        },
    )
    assert _targets(_check("DB-MYSQL-004", clean)) == []

    mariadb = Source("maria", "mariadb", "driver", "AVAILABLE", None, {})
    maria_outcome = _check("DB-MYSQL-004", mariadb)
    assert isinstance(maria_outcome, str)
    assert "MariaDB does not support NOT ENFORCED" in maria_outcome

    old_mysql = Source(
        "old",
        "mysql",
        "driver",
        "AVAILABLE",
        None,
        {"server": {"server_version": "5.7.44"}, "vendor": {}},
    )
    old_outcome = _check("DB-MYSQL-004", old_mysql)
    assert isinstance(old_outcome, str)
    assert "MySQL 8.0.16 or later" in old_outcome


def test_vendor_version_gates_read_dialect_server_version_info_from_inspect_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeInspector:
        @staticmethod
        def get_table_names() -> list[str]:
            return []

    monkeypatch.setattr(
        sqla,
        "sqlalchemy_module",
        lambda: type("SA", (), {"inspect": staticmethod(lambda _c: FakeInspector())})(),
    )

    def inspected_source(dialect_name: str, version: tuple[int, ...], **vendor: dict[str, Any]) -> Source:
        dialect = type("FakeDialect", (), {"name": dialect_name, "driver": "drv", "server_version_info": version})()
        engine = type("FakeEngine", (), {"url": "db://localhost/app"})()
        conn = type(
            "FakeConn",
            (),
            {
                "dialect": dialect,
                "engine": engine,
                "begin_nested": lambda self: contextlib.nullcontext(),
                "exec_driver_sql": lambda self, _sql: type("Res", (), {"fetchmany": lambda self, _n: []})(),
            },
        )()
        found = {**sqla_inspect.catalog(conn, CatalogBounds(), Masker("MASKED", True, None)), "vendor": vendor}
        return Source("db", dialect_name, "drv", "AVAILABLE", None, found)

    pg96 = inspected_source("postgresql", (9, 6), emptyPartitioned=_fact({"tbl": "empty_metrics"}))
    old_server = inspected_source("mysql", (8, 0, 15), unenforcedChecks=_fact({"tbl": "orders", "name": "chk"}))

    assert _check("DB-PG-006", pg96) == "Not applicable: declarative partitioning requires PostgreSQL 10 or later."
    assert _check("DB-MYSQL-004", old_server) == "Not applicable: check constraints require MySQL 8.0.16 or later."
