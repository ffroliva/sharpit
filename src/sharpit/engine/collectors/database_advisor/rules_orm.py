"""ORM mapping rules DB-HIB-002..010 (port of BootUI's ``Hibernate*Rule`` cross-references, 2.2.0) on SQLAlchemy models.

``facts(models)`` reads the tables behind ``install(models=...)`` once, through ``engine/models.py``'s configured-gate:
an unconfigured registry yields a skip reason and no mapper attribute that would configure it is touched (sharpit
never calls ``configure_mappers()``). Only ``mapper.local_table`` and its ``Table`` are read: a declared foreign key is
the column's ``ForeignKey`` target string, never ``mapper.relationships``. Each check compares those declared tables
with one source's catalog (the connection's default schema); a table declared in another schema is not compared.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any, cast

from sharpit.engine.advisors.rules import RuleDefinition, Severity
from sharpit.engine.collectors.database_advisor.catalog import Hit, Outcome, Rule, Source, unreadable
from sharpit.engine.models import mappers_configured, registries

ORM = "ORM mapping"
NO_MODELS = "No models were passed to sharpit.install(models=...), so the ORM rules have nothing to compare."
NO_REGISTRY = "models= holds no declarative base or registry, so the ORM rules have nothing to compare."
UNCONFIGURED = (
    "The SQLAlchemy mappers are not configured yet, so the ORM rules did not read them (sharpit never calls "
    "configure_mappers()). Run the checks again once the application has used its models."
)
NOT_READ = "The ORM declarations were not read for this scan."
CUT = "The table inventory was cut by a scan bound, so a declared table cannot be called missing."
NOTHING_MATCHED = "No declared table was found in the observed schema, so no column could be compared."
_CHAR_SIZE = re.compile(r"CHAR[A-Z ]*\((\d+)\)")
_DECIMAL = re.compile(r"^(?:NUMERIC|DECIMAL)\((\d+)(?:,\s*(\d+))?\)")

Table = dict[str, Any]


# --- the declared side -------------------------------------------------------------------------------------------


def facts(models: tuple[object, ...]) -> dict[str, Any]:
    """The declared tables behind ``models`` as plain dicts, or ``{"skipped": reason}``."""
    if not models:
        return {"skipped": NO_MODELS}
    found, _warnings = registries(models)
    if not found:
        return {"skipped": NO_REGISTRY}
    tables: dict[int, Table] = {}
    try:
        for registry in found:
            mappers = list(cast("Any", registry).mappers)
            if not mappers_configured(registry, mappers):
                return {"skipped": UNCONFIGURED}
            for mapper in mappers:
                table = mapper.local_table  # a configured mapper: reading it configures nothing
                if type(table).__name__ == "Table" and id(table) not in tables:
                    tables[id(table)] = _declared(table)
    except Exception as exc:  # noqa: BLE001 - unreadable models skip the ORM rules, never fail the scan
        return {"skipped": f"The models could not be read ({type(exc).__name__})."}
    return {"tables": list(tables.values())}


def _is_numeric(column_type: Any) -> bool:
    names = {c.__name__ for c in type(column_type).__mro__}
    return "Numeric" in names and "Float" not in names


def _declared_column(column: Any) -> dict[str, Any]:
    kind = column.type
    numeric = _is_numeric(kind)
    length = getattr(kind, "length", None)
    return {
        "name": column.name,
        "nullable": bool(column.nullable),
        "primaryKey": bool(column.primary_key),
        "length": length if isinstance(length, int) and length > 0 else None,
        "precision": kind.precision if numeric and isinstance(kind.precision, int) else None,
        "scale": (kind.scale or 0) if numeric else None,
        "identity": column.identity is not None or column.autoincrement is True,
    }


def _declared(table: Any) -> Table:
    # Column(unique=True) is a UniqueConstraint on the table, so constraints and unique indexes cover every form
    uniques = {
        tuple(column.name for column in item.columns): None
        for item in (*table.constraints, *table.indexes)
        if type(item).__name__ == "UniqueConstraint" or (type(item).__name__ == "Index" and item.unique)
    }
    foreign_keys: list[dict[str, Any]] = []
    for constraint in table.foreign_key_constraints:
        targets = [str(element.target_fullname).rsplit(".", 2) for element in constraint.elements]
        foreign_keys.append(
            {
                "columns": [element.parent.name for element in constraint.elements],
                "referredTable": targets[0][-2] if len(targets[0]) > 1 else "",
                "referredColumns": [target[-1] for target in targets],
            }
        )
    return {
        "name": table.name,
        "schema": table.schema,
        "columns": [_declared_column(column) for column in table.columns],
        "uniques": [list(columns) for columns in uniques],
        "foreignKeys": foreign_keys,
    }


# --- comparison helpers ------------------------------------------------------------------------------------------


def _declared_tables(source: Source) -> list[Table] | str:
    if (reason := unreadable(source)) is not None:
        return reason
    declared = source.catalog.get("orm")
    if declared is None:
        return NOT_READ
    if "skipped" in declared:
        return declared["skipped"]
    return [t for t in declared["tables"] if t["schema"] is None]


def _pairs(source: Source) -> list[tuple[Table, Table]] | str:
    """(declared, observed) per declared table found in the catalog."""
    declared = _declared_tables(source)
    if isinstance(declared, str):
        return declared
    observed = {t["name"].lower(): t for t in source.tables}
    pairs = [(d, observed[d["name"].lower()]) for d in declared if d["name"].lower() in observed]
    return pairs or NOTHING_MATCHED


def _columns(declared: Table, observed: Table) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    by_name = {c["name"].lower(): c for c in observed["columns"]}
    for column in declared["columns"]:
        if (found := by_name.get(column["name"].lower())) is not None:
            yield column, found


def _column_hit(source: Source, table: Table, column: dict[str, Any], text: str) -> Hit:
    where = f"{table['name']}.{column['name']}"
    return (
        f"{source.name}/{where}",
        f"Datasource `{source.name}`: column `{where}` {text}",
        f"ds={source.name}|table={table['name']}|column={column['name']}",
    )


def _per_column(source: Source, judge: Callable[[dict[str, Any], dict[str, Any]], str | None]) -> Outcome:
    pairs = _pairs(source)
    if isinstance(pairs, str):
        return pairs
    return [
        _column_hit(source, declared, column, text)
        for declared, observed in pairs
        for column, physical in _columns(declared, observed)
        if (text := judge(column, physical)) is not None
    ]


# --- the checks --------------------------------------------------------------------------------------------------


def _missing_table(source: Source) -> Outcome:
    declared = _declared_tables(source)
    if isinstance(declared, str):
        return declared
    if source.catalog.get("truncated") or not source.catalog.get("complete"):
        return CUT
    observed = {t["name"].lower() for t in source.tables}
    return [
        (
            f"{source.name}/{t['name']}",
            f"Datasource `{source.name}`: declared table `{t['name']}` was not found in the observed schema.",
            f"ds={source.name}|table={t['name']}",
        )
        for t in declared
        if t["name"].lower() not in observed
    ]


def _nullability(column: dict[str, Any], physical: dict[str, Any]) -> str | None:
    if column["primaryKey"] or column["nullable"] or not physical["nullable"]:
        return None
    return "is declared NOT NULL but the database allows NULL."


def _length(column: dict[str, Any], physical: dict[str, Any]) -> str | None:
    size = _CHAR_SIZE.search(physical["type"])
    if column["length"] is None or size is None or column["length"] <= int(size.group(1)):
        return None
    return f"is declared with length {column['length']} but the database column holds {size.group(1)}."


def _precision(column: dict[str, Any], physical: dict[str, Any]) -> str | None:
    bounded = _DECIMAL.match(physical["type"])
    if not column["precision"] or bounded is None:
        return None
    precision, scale = int(bounded.group(1)), int(bounded.group(2) or 0)
    wider_scale = column["scale"] > scale
    wider_digits = column["precision"] - column["scale"] > precision - scale
    if not (wider_scale or wider_digits):
        return None
    return (
        f"is declared NUMERIC({column['precision']}, {column['scale']}) but the database column is "
        f"NUMERIC({precision}, {scale})."
    )


def _identity(column: dict[str, Any], physical: dict[str, Any]) -> str | None:
    if not column["identity"] or physical["autoincrement"]:
        return None
    return "is declared database-generated (Identity or autoincrement=True) but the database does not generate it."


def _missing_column(source: Source) -> Outcome:
    pairs = _pairs(source)
    if isinstance(pairs, str):
        return pairs
    hits: list[Hit] = []
    for declared, observed in pairs:
        if observed["truncated"]:
            continue  # a cut column inventory proves no absence
        names = {c["name"].lower() for c in observed["columns"]}
        hits += [
            _column_hit(source, declared, c, "is declared but was not found in the observed table.")
            for c in declared["columns"]
            if c["name"].lower() not in names
        ]
    return hits


def _key_hit(source: Source, table: Table, columns: list[str], text: str, kind: str) -> Hit:
    where = f"{table['name']}({', '.join(columns)})"
    return (
        f"{source.name}/{where}",
        f"Datasource `{source.name}`: `{where}` {text}",
        f"ds={source.name}|table={table['name']}|{kind}={','.join(columns)}",
    )


def _enforced(observed: Table, columns: list[str]) -> bool:
    wanted = {c.lower() for c in columns}
    keys = [observed["primaryKey"]] + [i["columns"] for i in observed["indexes"] if i["unique"]]
    return any(key and None not in key and {c.lower() for c in key} <= wanted for key in keys)


def _missing_unique(source: Source) -> Outcome:
    if source.dialect == "sqlite":
        return "The SQLite inspector does not list the indexes behind UNIQUE constraints."
    pairs = _pairs(source)
    if isinstance(pairs, str):
        return pairs
    return [
        _key_hit(source, declared, columns, "is declared unique but no observed key enforces it.", "unique")
        for declared, observed in pairs
        if not observed["truncated"]
        for columns in declared["uniques"]
        if not _enforced(observed, columns)
    ]


def _has_fk(observed: Table, fk: dict[str, Any]) -> bool:
    return any(
        [c.lower() for c in found["columns"]] == [c.lower() for c in fk["columns"]]
        and found["referredTable"].lower() == fk["referredTable"].lower()
        and [c.lower() for c in found["referredColumns"]] == [c.lower() for c in fk["referredColumns"]]
        for found in observed["foreignKeys"]
    )


def _missing_foreign_key(source: Source) -> Outcome:
    pairs = _pairs(source)
    if isinstance(pairs, str):
        return pairs
    return [
        _key_hit(
            source,
            declared,
            fk["columns"],
            f"declares a foreign key to `{fk['referredTable']}` that the database does not have.",
            "fk",
        )  # fmt: skip
        for declared, observed in pairs
        for fk in declared["foreignKeys"]
        if not _has_fk(observed, fk)
    ]


def _generated_identity(source: Source) -> Outcome:
    if source.dialect not in ("postgresql", "mysql", "mariadb"):
        return f"Database-side generation is only read on PostgreSQL, MySQL and MariaDB, not {source.dialect}."
    return _per_column(source, _identity)


def _rule(rule_id: str, title: str, severity: Severity, description: str, check: Callable[[Source], Outcome]) -> Rule:
    recommendation = (
        "Review the model declaration and the live table together before changing either: a migration, a naming "
        "convention or another datasource can explain the difference."
    )
    return Rule(RuleDefinition(rule_id, title, ORM, severity, description, recommendation, _URL), check)


_URL = "https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html"

RULES = (
    _rule("DB-HIB-002", "Declared entity relation name not found in the observed schema", "MEDIUM",
          "Reviews a mapped table name not observed in a complete table inventory of the default schema. Not proof "
          "the table is missing: a view, another schema or another datasource can hold it.", _missing_table),
    _rule("DB-HIB-003", "Declared column nullability differs from observed metadata", "MEDIUM",
          "Compares a column declared nullable=False with a database column that allows NULL. Primary-key columns "
          "are not compared.", lambda s: _per_column(s, _nullability)),
    _rule("DB-HIB-004", "Declared column length exceeds observed column size", "MEDIUM",
          "Compares a declared positive String length with a bounded CHAR/VARCHAR column. Unbounded text types are "
          "not compared.", lambda s: _per_column(s, _length)),
    _rule("DB-HIB-005", "Declared uniqueness has no observed enforcing key", "HIGH",
          "Reviews a declared unique column, UniqueConstraint or unique Index against the observed primary key and "
          "unique indexes; a unique key on a subset of the declared columns enforces it.", _missing_unique),
    _rule("DB-HIB-006", "Declared column name not found in the observed relation", "MEDIUM",
          "Reviews a declared column not observed in a found table whose column inventory is complete.",
          _missing_column),
    _rule("DB-HIB-007", "Declared association has no matching observed foreign key", "MEDIUM",
          "Reviews a declared ForeignKey/ForeignKeyConstraint against the observed child-to-parent column pairs. "
          "A relationship() without a ForeignKey is not compared.", _missing_foreign_key),
    _rule("DB-HIB-009", "IDENTITY identifier column without database-side generation", "MEDIUM",
          "Reviews a column declared with Identity() or autoincrement=True that the PostgreSQL, MySQL or MariaDB "
          "inspector reports as not database-generated.", _generated_identity),
    _rule("DB-HIB-010", "Declared numeric precision or scale exceeds the observed column", "MEDIUM",
          "Compares a declared Numeric(precision, scale) with a bounded NUMERIC/DECIMAL column: a narrower scale "
          "rounds, fewer integer digits reject. Unconstrained columns are not compared.",
          lambda s: _per_column(s, _precision)),
)  # fmt: skip
