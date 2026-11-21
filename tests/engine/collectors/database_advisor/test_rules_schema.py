"""Schema rules DB-SCHEMA-001..007 over the catalog dicts ``sqla.inspect.catalog`` returns (plan A-dbadv-1 Task 3)."""

from __future__ import annotations

from typing import Any

from sharpit.engine.collectors.database_advisor import rules_schema
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Source


def _column(name: str, type_: str = "INTEGER", *, autoincrement: bool = False) -> dict[str, Any]:
    return {"name": name, "type": type_, "nullable": True, "autoincrement": autoincrement}


def _index(name: str, *columns: str | None, unique: bool = False, **options: str) -> dict[str, Any]:
    return {"name": name, "columns": list(columns), "unique": unique, "options": options}


def _fk(name: str | None, columns: list[str], table: str, referred: list[str], **options: str) -> dict[str, Any]:
    return {"name": name, "columns": columns, "referredSchema": None, "referredTable": table,
            "referredColumns": referred, "options": options}  # fmt: skip


def _table(name: str, *columns: dict[str, Any], pk: tuple[str, ...] = ("id",), fks: tuple[dict[str, Any], ...] = (),
           indexes: tuple[dict[str, Any], ...] = (), truncated: bool = False,
           pk_name: str | None = None) -> dict[str, Any]:  # fmt: skip
    return {"schema": None, "name": name, "truncated": truncated, "primaryKeyName": pk_name,
            "columns": list(columns) or [_column("id")],
            "primaryKey": list(pk), "foreignKeys": list(fks), "indexes": list(indexes)}  # fmt: skip


def _source(*tables: dict[str, Any], status: str = "AVAILABLE", dialect: str = "sqlite") -> Source:
    catalog = {"dialect": dialect, "tables": list(tables), "tableCount": len(tables), "truncated": False,
               "complete": True, "diagnostics": [], "server": {}}  # fmt: skip
    return Source("db", dialect, "driver", status, None, catalog if status != "FAILED" else {})


def _check(rule_id: str, source: Source) -> Outcome:
    rule = next(r for r in rules_schema.RULES if r.definition.id == rule_id)
    return rule.check(source)


def _targets(outcome: Outcome) -> list[str] | str:
    return [target for target, _message, _identity in outcome] if isinstance(outcome, list) else outcome


PARENT = _table("orders", _column("id"), _column("code", "VARCHAR(20)"))


def test_missing_primary_key_is_reported() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.missingPrimaryKeyIsAnObservedStructuralReview
    source = _source(PARENT, _table("audit_log", _column("at"), pk=()))

    assert _targets(_check("DB-SCHEMA-001", source)) == ["db/audit_log"]


def test_migration_bookkeeping_table_is_not_a_missing_primary_key() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.exclusionsAndUnreadKeysAreSkippedRatherThanPassed
    source = _source(_table("flyway_schema_history", _column("version"), pk=()))

    assert _targets(_check("DB-SCHEMA-001", source)) == []


def test_unread_datasource_is_skipped_rather_than_passed() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.noEligibleTargetsNeverPassesAnyGenericRule
    outcomes = [rule.check(_source(status="FAILED")) for rule in rules_schema.RULES]

    assert [isinstance(o, str) for o in outcomes] == [True] * len(rules_schema.RULES)


def test_foreign_key_without_leading_index_is_reported() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.incompleteLeadingSetPromptsReviewWithoutPredictingScans
    child = _table("lines", _column("id"), _column("order_id"), fks=(_fk("fk_order", ["order_id"], "orders", ["id"]),))

    assert _targets(_check("DB-SCHEMA-002", _source(PARENT, child))) == ["db/lines(order_id)"]


def test_foreign_key_access_path_accepts_leading_columns_in_either_order() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.foreignKeyAccessPathAcceptsAllLeadingColumnsInEitherOrderAndTrailingExpression  # noqa: E501
    fk = _fk("fk_pair", ["a", "b"], "orders", ["id", "code"])
    child = _table(
        "lines", _column("id"), _column("a"), _column("b"), fks=(fk,), indexes=(_index("ix", "b", "a", None),)
    )

    assert _targets(_check("DB-SCHEMA-002", _source(PARENT, child))) == []


def test_truncated_index_inventory_cannot_prove_an_absent_access_path() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.prefixPartialUnknownAndTruncatedIndexesCannotProveAnAbsentAccessPath
    fk = _fk("fk_order", ["order_id"], "orders", ["id"])
    child = _table("lines", _column("id"), _column("order_id"), fks=(fk,), truncated=True)

    assert _targets(_check("DB-SCHEMA-002", _source(PARENT, child))) == []


def test_exact_duplicate_indexes_are_one_pair() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.onlyExactKnownIndexDefinitionsAreDuplicateCandidates
    table = _table("orders", _column("id"), _column("code"), indexes=(
        _index("ix_b", "code"), _index("ix_a", "code"), _index("ix_prefix", "code", "id")))  # fmt: skip

    assert _targets(_check("DB-SCHEMA-003", _source(table))) == ["db/orders: ix_a, ix_b"]


def test_expression_or_differently_configured_indexes_are_not_duplicates() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.orderingCollationAndUnknownExpressionsDoNotProveEquivalence
    table = _table("orders", _column("id"), _column("code"), indexes=(
        _index("ix_expr_1", None), _index("ix_expr_2", None),
        _index("ix_hash", "code", postgresql_using="hash"), _index("ix_btree", "code")))  # fmt: skip

    assert _targets(_check("DB-SCHEMA-003", _source(table))) == []


def test_foreign_key_type_mismatch_uses_the_referenced_column() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.domainNarrowingUsesTheActualAlternateReferencedColumn
    fk = _fk("fk_code", ["order_code"], "orders", ["code"])
    child = _table("lines", _column("id"), _column("order_code", "VARCHAR(10)"), fks=(fk,))

    assert _targets(_check("DB-SCHEMA-004", _source(PARENT, child))) == ["db/lines.order_code"]


def test_postgresql_serial_aliases_match_their_integer_types():
    # ported: DatabaseAdvisorSchemaRulesTests.postgresSerialTypesAndUnboundedSentinelsAreComparedAccurately
    parent = _table("orders", _column("id", "INTEGER"))
    child = _table(
        "lines",
        _column("order_id", "SERIAL"),
        pk=(),
        fks=(_fk("fk_order", ["order_id"], "orders", ["id"]),),
    )

    assert _targets(_check("DB-SCHEMA-004", _source(parent, child, dialect="postgresql"))) == []


def test_identical_declarations_are_not_a_type_mismatch() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.onlyIdenticalFullyReportedDeclarationsMakeUnmodeledFamiliesComparable
    fk = _fk("fk_code", ["order_code"], "orders", ["code"])
    child = _table("lines", _column("id"), _column("order_code", "varchar(20)"), fks=(fk,))

    assert _targets(_check("DB-SCHEMA-004", _source(PARENT, child))) == []


def test_unique_index_on_the_primary_key_columns_is_reported() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.primaryKeyBackingIndexIsNeverGuessedFromItsNameOrColumns
    table = _table("orders", _column("id"), _column("code"), pk_name="pk_orders", indexes=(
        _index("pk_orders", "id", unique=True), _index("uq_id", "id", unique=True),
        _index("uq_code", "code", unique=True), _index("ix_id", "id")))  # fmt: skip

    assert _targets(_check("DB-SCHEMA-005", _source(table))) == ["db/orders.uq_id"]


def test_unique_index_without_observed_primary_key_backing_is_not_called_redundant() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.tablesWithOnlyNonUniqueSecondaryIndexesOrUnrelatedUniqueIndexesDoNotTriggerUnknownBackingDiagnostics  # noqa: E501
    table = _table("orders", _column("id"), _column("customer_id"), indexes=(
        _index("uq_id", "id", unique=True), _index("ix_customer", "customer_id"),
        _index("uq_customer", "customer_id", unique=True)))  # fmt: skip

    assert _targets(_check("DB-SCHEMA-005", _source(table))) == []


def test_duplicate_foreign_keys_need_identical_pairs_and_actions() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.foreignKeyDuplicateRequiresKnownMatchingActionsAndExactPairedIdentity
    fks = (
        _fk("fk_b", ["order_id"], "orders", ["id"]),
        _fk("fk_a", ["order_id"], "orders", ["id"]),
        _fk("fk_cascade", ["order_id"], "orders", ["id"], ondelete="CASCADE"),
    )
    child = _table("lines", _column("id"), _column("order_id"), fks=fks)

    assert _targets(_check("DB-SCHEMA-006", _source(PARENT, child))) == ["db/lines: fk_a, fk_b"]


def test_generated_small_key_is_reported() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.generatedSmallKeyReportsBoundsNotLifetimeRows
    tiny = _table("tiny", _column("id", "SMALLINT", autoincrement=True))
    plain = _table("plain", _column("id", "SMALLINT"))
    wide = _table("wide", _column("id", "BIGINT", autoincrement=True))

    assert _targets(_check("DB-SCHEMA-007", _source(tiny, plain, wide))) == ["db/tiny.id"]


def test_generated_postgresql_serial_aliases_use_their_integer_width() -> None:
    # ported: DatabaseAdvisorSchemaRulesTests.generatedSmallKeyReportsBoundsNotLifetimeRows
    small = _table("small", _column("id", "serial2", autoincrement=True))
    regular = _table("regular", _column("id", "serial4", autoincrement=True))
    large = _table("large", _column("id", "serial8", autoincrement=True))

    assert _targets(_check("DB-SCHEMA-007", _source(small, regular, large))) == ["db/small.id"]


def test_finding_identity_never_holds_a_value() -> None:
    # ported: DatabaseFindingIdentityTests (identities name the physical object, never a message or value)
    outcome = _check("DB-SCHEMA-001", _source(_table("audit_log", _column("at"), pk=())))

    assert [identity for _target, _message, identity in outcome] == ["ds=db|table=audit_log"]
