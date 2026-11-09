"""ORM mapping rules DB-HIB-* over ``install(models=...)`` and the catalog dicts (plan A-dbadv-2 Task 1).

The declared side is real SQLAlchemy models read through ``rules_orm.facts``; the observed side is hand-made catalog
dicts in ``sqla.inspect.catalog``'s shape.
"""

from __future__ import annotations

import gc
from collections.abc import Iterator
from typing import Any

import pytest

from sharpit.engine.collectors.database_advisor import report, rules_orm
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Source

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")
orm = pytest.importorskip("sqlalchemy.orm")


@pytest.fixture(autouse=True)
def _keep_mapped_classes() -> Iterator[None]:
    """A registry holds its mapped classes weakly: the tests' throwaway classes must outlive a cyclic collection."""
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()


def _column(name: str, type_: str = "INTEGER", *, nullable: bool = True, autoincrement: bool = False) -> dict[str, Any]:
    return {"name": name, "type": type_, "nullable": nullable, "autoincrement": autoincrement}


def _table(name: str, *columns: dict[str, Any], pk: tuple[str, ...] = ("id",), fks: tuple[dict[str, Any], ...] = (),
           indexes: tuple[dict[str, Any], ...] = ()) -> dict[str, Any]:  # fmt: skip
    return {"schema": None, "name": name, "truncated": False, "columns": list(columns), "primaryKey": list(pk),
            "foreignKeys": list(fks), "indexes": list(indexes)}  # fmt: skip


def _source(models: tuple[object, ...], *tables: dict[str, Any], dialect: str = "postgresql") -> Source:
    catalog = {"dialect": dialect, "tables": list(tables), "tableCount": len(tables), "truncated": False,
               "complete": True, "diagnostics": [], "server": {}, "orm": rules_orm.facts(models)}  # fmt: skip
    return Source("db", dialect, "driver", "AVAILABLE", None, catalog)


def _check(rule_id: str, source: Source) -> Outcome:
    return next(r for r in rules_orm.RULES if r.definition.id == rule_id).check(source)


def _targets(outcome: Outcome) -> list[str] | str:
    return [target for target, _message, _identity in outcome] if isinstance(outcome, list) else outcome


def _users(**columns: Any) -> Any:
    """A configured registry mapping ``users`` with an integer ``id`` key and the given extra columns."""
    reg = orm.registry()
    table = sa.Table("users", reg.metadata, sa.Column("id", sa.Integer, primary_key=True), *columns.values())
    reg.map_imperatively(type("User", (), {}), table)
    reg.configure()
    return reg


ID = _column("id", nullable=False, autoincrement=True)


def test_scan_never_configures_mappers() -> None:
    # spec §5.8: the ORM rules read mappers only through the configured-gate, never configure_mappers()
    reg = orm.registry()
    parent = sa.Table("parent", reg.metadata, sa.Column("id", sa.Integer, primary_key=True))
    parent_class = type("Parent", (), {})
    mapper = reg.map_imperatively(parent_class, parent, properties={"children": orm.relationship("NotYetDeclared")})
    source = _source((reg,), _table("parent", ID))

    outcomes = [rule.check(source) for rule in rules_orm.RULES]
    report.evaluate([source])

    assert mapper.configured is False
    assert all(isinstance(outcome, str) for outcome in outcomes)


def test_unconfigured_registry_skips_orm_rules() -> None:
    reg = orm.registry()
    thing = sa.Table("thing", reg.metadata, sa.Column("id", sa.Integer, primary_key=True))
    reg.map_imperatively(type("Thing", (), {}), thing)
    source = _source((reg,), _table("thing", ID))

    outcomes = {rule.definition.id: rule.check(source) for rule in rules_orm.RULES}

    assert set(outcomes) == {"DB-HIB-002", "DB-HIB-003", "DB-HIB-004", "DB-HIB-005", "DB-HIB-006", "DB-HIB-007",
                             "DB-HIB-009", "DB-HIB-010"}  # fmt: skip
    assert all(isinstance(o, str) and "not configured" in o for o in outcomes.values())


def test_orm_rules_skip_without_orm_facts() -> None:
    source = Source("db", "postgresql", "driver", "AVAILABLE", None, {"tables": [_table("users", ID)]})

    assert isinstance(_check("DB-HIB-002", source), str)


def test_hib_002_declared_table_missing() -> None:
    # ported: DatabaseAdvisorHibernateRulesTests (an explicit table name absent from complete relation metadata)
    source = _source((_users(),), _table("accounts", ID))

    assert _targets(_check("DB-HIB-002", source)) == ["db/users"]


def test_hib_002_no_claim_from_a_cut_table_inventory() -> None:
    source = _source((_users(),), _table("accounts", ID))
    source.catalog["truncated"] = True

    assert isinstance(_check("DB-HIB-002", source), str)


def test_hib_003_declared_not_null_but_column_nullable() -> None:
    reg = _users(email=sa.Column("email", sa.String(50), nullable=False))
    source = _source((reg,), _table("users", ID, _column("email", "VARCHAR(50)", nullable=True)))

    assert _targets(_check("DB-HIB-003", source)) == ["db/users.email"]


def test_hib_003_matching_nullability_passes() -> None:
    reg = _users(email=sa.Column("email", sa.String(50), nullable=False))
    source = _source((reg,), _table("users", ID, _column("email", "VARCHAR(50)", nullable=False)))

    assert _check("DB-HIB-003", source) == []


def test_hib_004_declared_length_exceeds_column() -> None:
    reg = _users(name=sa.Column("name", sa.String(100)))
    source = _source((reg,), _table("users", ID, _column("name", "VARCHAR(40)")))

    assert _targets(_check("DB-HIB-004", source)) == ["db/users.name"]


def test_hib_004_unbounded_physical_text_is_not_compared() -> None:
    reg = _users(name=sa.Column("name", sa.String(100)))
    source = _source((reg,), _table("users", ID, _column("name", "TEXT")))

    assert _check("DB-HIB-004", source) == []


def test_hib_005_declared_unique_without_enforcing_key() -> None:
    reg = _users(email=sa.Column("email", sa.String(50), unique=True))
    source = _source((reg,), _table("users", ID, _column("email", "VARCHAR(50)")))

    assert _targets(_check("DB-HIB-005", source)) == ["db/users(email)"]


def test_hib_005_unique_index_on_a_subset_enforces() -> None:
    reg = orm.registry()
    table = sa.Table("users", reg.metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("a", sa.Integer),
                     sa.Column("b", sa.Integer), sa.UniqueConstraint("a", "b"))  # fmt: skip
    reg.map_imperatively(type("User", (), {}), table)
    reg.configure()
    index = {"name": "ux_a", "columns": ["a"], "unique": True, "options": {}}
    source = _source((reg,), _table("users", ID, _column("a"), _column("b"), indexes=(index,)))

    assert _check("DB-HIB-005", source) == []


def test_hib_005_skips_on_sqlite() -> None:
    # the SQLite inspector hides the indexes behind UNIQUE constraints, so absence cannot be claimed there
    reg = _users(email=sa.Column("email", sa.String(50), unique=True))
    source = _source((reg,), _table("users", ID, _column("email", "VARCHAR(50)")), dialect="sqlite")

    assert isinstance(_check("DB-HIB-005", source), str)


def test_hib_006_declared_column_missing() -> None:
    reg = _users(email=sa.Column("email", sa.String(50)))
    source = _source((reg,), _table("users", ID))

    assert _targets(_check("DB-HIB-006", source)) == ["db/users.email"]


def test_hib_007_declared_foreign_key_missing() -> None:
    reg = orm.registry()
    sa.Table("orgs", reg.metadata, sa.Column("id", sa.Integer, primary_key=True))
    users = sa.Table("users", reg.metadata, sa.Column("id", sa.Integer, primary_key=True),
                     sa.Column("org_id", sa.ForeignKey("orgs.id")))  # fmt: skip
    reg.map_imperatively(type("User", (), {}), users)
    reg.configure()
    source = _source((reg,), _table("users", ID, _column("org_id")), _table("orgs", ID))

    assert _targets(_check("DB-HIB-007", source)) == ["db/users(org_id)"]


def test_hib_007_matching_foreign_key_passes() -> None:
    reg = orm.registry()
    sa.Table("orgs", reg.metadata, sa.Column("id", sa.Integer, primary_key=True))
    users = sa.Table("users", reg.metadata, sa.Column("id", sa.Integer, primary_key=True),
                     sa.Column("org_id", sa.ForeignKey("orgs.id")))  # fmt: skip
    reg.map_imperatively(type("User", (), {}), users)
    reg.configure()
    fk = {"name": "fk", "columns": ["org_id"], "referredSchema": None, "referredTable": "orgs",
          "referredColumns": ["id"], "options": {}}  # fmt: skip
    source = _source((reg,), _table("users", ID, _column("org_id"), fks=(fk,)), _table("orgs", ID))

    assert _check("DB-HIB-007", source) == []


def test_hib_009_identity_key_without_database_generation() -> None:
    reg = orm.registry()
    table = sa.Table("users", reg.metadata, sa.Column("id", sa.Integer, sa.Identity(), primary_key=True))
    reg.map_imperatively(type("User", (), {}), table)
    reg.configure()
    source = _source((reg,), _table("users", _column("id", nullable=False, autoincrement=False)))

    assert _targets(_check("DB-HIB-009", source)) == ["db/users.id"]


def test_hib_009_skips_on_sqlite() -> None:
    reg = orm.registry()
    table = sa.Table("users", reg.metadata, sa.Column("id", sa.Integer, sa.Identity(), primary_key=True))
    reg.map_imperatively(type("User", (), {}), table)
    reg.configure()
    source = _source((reg,), _table("users", _column("id", autoincrement=False)), dialect="sqlite")

    assert isinstance(_check("DB-HIB-009", source), str)


def test_hib_010_declared_scale_exceeds_column() -> None:
    reg = _users(price=sa.Column("price", sa.Numeric(10, 4)))
    source = _source((reg,), _table("users", ID, _column("price", "NUMERIC(10, 2)")))

    assert _targets(_check("DB-HIB-010", source)) == ["db/users.price"]


def test_hib_010_declared_integer_digits_exceed_column() -> None:
    reg = _users(price=sa.Column("price", sa.Numeric(12, 2)))
    source = _source((reg,), _table("users", ID, _column("price", "DECIMAL(8,2)")))

    assert _targets(_check("DB-HIB-010", source)) == ["db/users.price"]


def test_hib_010_unconstrained_numeric_is_not_compared() -> None:
    reg = _users(price=sa.Column("price", sa.Numeric(12, 2)))
    source = _source((reg,), _table("users", ID, _column("price", "NUMERIC")))

    assert _check("DB-HIB-010", source) == []


def test_scan_leaves_a_configurable_registry_unconfigured() -> None:
    # a registry that configure_mappers() *could* configure: a scan that configured it would flip mapper.configured
    reg = orm.registry()
    sa.Table("child", reg.metadata, sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("parent_id", sa.ForeignKey("parent.id")))  # fmt: skip
    parent = sa.Table("parent", reg.metadata, sa.Column("id", sa.Integer, primary_key=True))
    child_class, parent_class = type("Child", (), {}), type("Parent", (), {})
    reg.map_imperatively(child_class, reg.metadata.tables["child"])
    mapper = reg.map_imperatively(parent_class, parent, properties={"children": orm.relationship(child_class)})
    source = _source((reg,), _table("parent", ID), _table("child", ID, _column("parent_id")))

    report.evaluate([source])
    outcomes = [rule.check(source) for rule in rules_orm.RULES]

    assert mapper.configured is False
    assert all(isinstance(outcome, str) for outcome in outcomes)
