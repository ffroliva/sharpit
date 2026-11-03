"""Schema rules DB-SCHEMA-001..007 (port of BootUI's ``*Rule`` schema checks, 2.2.0) over the bounded catalog.

Each check reads one source's catalog (``sqla.inspect.catalog``: the connection's default schema) and returns its
findings, or why it could not look. A table whose index or column inventory was cut by a bound never yields a claim of
absence from that inventory.
"""

from __future__ import annotations

import itertools
from typing import Any

from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.collectors.database_advisor.catalog import Hit, Outcome, Rule, Source, unreadable

SCHEMA = "Schema"


MIGRATION_TABLES = frozenset(
    {
        "alembic_version",
        "flyway_schema_history",
        "schema_version",
        "databasechangelog",
        "databasechangeloglock",
        "changelog",
        "changeloglock",
    }
)
_NARROW = frozenset({"TINYINT", "SMALLINT", "INT2", "SMALLSERIAL"})

Table = dict[str, Any]


def _where(source: Source, table: Table, suffix: str = "") -> str:
    return f"{source.name}/{table['name']}{suffix}"


def _identity(source: Source, table: Table, *parts: str) -> str:
    return "|".join((f"ds={source.name}", f"table={table['name']}", *parts))


def _plain(index: dict[str, Any]) -> bool:
    """An ordinary B-tree index: no partial predicate, no other access method."""
    options = index["options"]
    return options.get("postgresql_where", "None") == "None" and options.get("postgresql_using", "btree") == "btree"


def _fk_label(fk: dict[str, Any], position: int) -> str:
    return fk["name"] or f"fk#{position + 1}"


def _pairs(source: Source, table: Table, groups: dict[Any, list[str]], noun: str, part: str) -> list[Hit]:
    hits: list[Hit] = []
    for names in groups.values():
        for a, b in itertools.combinations(sorted(names), 2):
            hits.append(
                (
                    _where(source, table, f": {a}, {b}"),
                    f"Datasource `{source.name}`: table `{table['name']}` has {noun} `{a}` and `{b}` with the same "
                    "definition.",
                    _identity(source, table, f"{part}={a}", f"{part}={b}"),
                )
            )
    return hits


def _missing_primary_key(source: Source) -> Outcome:
    if (reason := unreadable(source)) is not None:
        return reason
    return [
        (
            _where(source, t),
            f"Datasource `{source.name}`: table `{t['name']}` has no primary key.",
            _identity(source, t),
        )
        for t in source.tables
        if not t["primaryKey"] and t["name"].lower() not in MIGRATION_TABLES
    ]


def _foreign_key_access_path(source: Source) -> Outcome:
    if (reason := unreadable(source)) is not None:
        return reason
    hits: list[Hit] = []
    for t in source.tables:
        if t["truncated"]:  # an index past the bound could be the access path
            continue
        keys = [ix["columns"] for ix in t["indexes"] if _plain(ix)] + [t["primaryKey"]]
        for position, fk in enumerate(t["foreignKeys"]):
            columns = fk["columns"]
            if any(set(key[: len(columns)]) == set(columns) for key in keys):
                continue
            listed = ", ".join(columns)
            hits.append(
                (
                    _where(source, t, f"({listed})"),
                    f"Datasource `{source.name}`: foreign key `{_fk_label(fk, position)}` on `{t['name']}"
                    f"({listed})` has no index leading on its columns.",
                    _identity(source, t, f"fk={_fk_label(fk, position)}"),
                )
            )
    return hits


def _duplicate_index(source: Source) -> Outcome:
    if (reason := unreadable(source)) is not None:
        return reason
    hits: list[Hit] = []
    for t in source.tables:
        groups: dict[Any, list[str]] = {}
        for ix in t["indexes"]:
            if None not in ix["columns"]:  # an expression's definition is unknown, so it proves no equality
                key = (tuple(ix["columns"]), ix["unique"], tuple(sorted(ix["options"].items())))
                groups.setdefault(key, []).append(ix["name"])
        hits += _pairs(source, t, groups, "indexes", "index")
    return hits


def _foreign_key_type_mismatch(source: Source) -> Outcome:
    if (reason := unreadable(source)) is not None:
        return reason
    by_name = {t["name"]: t for t in source.tables}
    hits: list[Hit] = []
    for t in source.tables:
        own = {c["name"]: c for c in t["columns"]}
        for position, fk in enumerate(t["foreignKeys"]):
            parent = by_name.get(fk["referredTable"]) if fk["referredSchema"] is None else None
            referred = {c["name"]: c for c in parent["columns"]} if parent else {}
            for child, target in zip(fk["columns"], fk["referredColumns"], strict=False):
                if child not in own or target not in referred:  # an unread side is unknown, never a mismatch
                    continue
                child_type, target_type = own[child]["type"].upper(), referred[target]["type"].upper()
                if child_type != target_type:
                    hits.append(
                        (
                            _where(source, t, f".{child}"),
                            f"Datasource `{source.name}`: `{t['name']}.{child}` is {child_type} but references "
                            f"`{fk['referredTable']}.{target}`, which is {target_type}.",
                            _identity(source, t, f"fk={_fk_label(fk, position)}", f"column={child}"),
                        )
                    )
    return hits


def _unique_index_duplicating_primary_key(source: Source) -> Outcome:
    if (reason := unreadable(source)) is not None:
        return reason
    return [
        (
            _where(source, t, f".{ix['name']}"),
            f"Datasource `{source.name}`: unique index `{ix['name']}` on `{t['name']}` repeats the primary key's "
            "columns.",
            _identity(source, t, f"index={ix['name']}"),
        )
        for t in source.tables
        for ix in t["indexes"]
        if t["primaryKey"] and ix["unique"] and _plain(ix) and ix["columns"] == t["primaryKey"]
    ]


def _duplicate_foreign_key(source: Source) -> Outcome:
    if (reason := unreadable(source)) is not None:
        return reason
    hits: list[Hit] = []
    for t in source.tables:
        groups: dict[Any, list[str]] = {}
        for position, fk in enumerate(t["foreignKeys"]):
            pairs = frozenset(zip(fk["columns"], fk["referredColumns"], strict=False))
            key = (fk["referredSchema"], fk["referredTable"], pairs, tuple(sorted(fk["options"].items())))
            groups.setdefault(key, []).append(_fk_label(fk, position))
        hits += _pairs(source, t, groups, "foreign keys", "fk")
    return hits


def _narrow_generated_primary_key(source: Source) -> Outcome:
    if (reason := unreadable(source)) is not None:
        return reason
    hits: list[Hit] = []
    for t in source.tables:
        columns = {c["name"]: c for c in t["columns"]}
        key = columns.get(t["primaryKey"][0]) if len(t["primaryKey"]) == 1 else None
        if key and key["autoincrement"] and key["type"].split("(")[0].upper() in _NARROW:
            hits.append(
                (
                    _where(source, t, f".{key['name']}"),
                    f"Datasource `{source.name}`: generated primary key `{t['name']}.{key['name']}` is "
                    f"{key['type']}, a narrow domain.",
                    _identity(source, t, f"column={key['name']}"),
                )
            )
    return hits


RULES = (
    Rule(
        RuleDefinition(
            "DB-SCHEMA-001",
            "Tables without a primary key",
            SCHEMA,
            "MEDIUM",
            "Detects application tables reported by the SQLAlchemy inspector with no primary key columns, excluding "
            "migration bookkeeping tables.",
            "Review whether a declared primary key fits this table's identity and consumers. No observed primary key "
            "does not prove unsafe data or a broken ORM/replication setup; empty catalog metadata can also reflect "
            "driver or privilege limitations.",
            "https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-PRIMARY-KEYS",
        ),
        _missing_primary_key,
    ),
    Rule(
        RuleDefinition(
            "DB-SCHEMA-002",
            "Foreign-key access-path review",
            SCHEMA,
            "MEDIUM",
            "Identifies foreign keys with no observed ordinary index leading on the full child column set. Equality "
            "lookups permit any leading order when the access method supports it.",
            "Review parent-key updates/deletes and representative query plans before adding an index. Partial, prefix "
            "and special indexes need individual assessment; no table scan is proven.",
            "https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-FK",
        ),
        _foreign_key_access_path,
    ),
    Rule(
        RuleDefinition(
            "DB-SCHEMA-003",
            "Exact duplicate index candidates",
            SCHEMA,
            "LOW",
            "Compares fully known ordinary index keys, uniqueness and reported dialect options. Prefixes, expressions, "
            "predicates and unknown definitions are not compared.",
            "Review both definitions, constraint dependencies, index hints and workload before considering removal. "
            "Even an exact structural duplicate does not prove workload-neutral removal.",
            "https://use-the-index-luke.com/sql/dml",
        ),
        _duplicate_index,
    ),
    Rule(
        RuleDefinition(
            "DB-SCHEMA-004",
            "Foreign key column type mismatch with the referenced column",
            SCHEMA,
            "MEDIUM",
            "Compares each foreign key column against the column it actually references, by the declared type the "
            "dialect renders (type family, width, precision/scale and length).",
            "Review whether the narrower child domain is intentional. It cannot represent every value the referenced "
            "declaration permits, but this does not prove invalid existing rows, a broken foreign key, or "
            "incompatible vendor coercions.",
            "https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html",
        ),
        _foreign_key_type_mismatch,
    ),
    Rule(
        RuleDefinition(
            "DB-SCHEMA-005",
            "Unique index duplicating a proven primary-key backing index",
            SCHEMA,
            "LOW",
            "Detects an ordinary unique index whose key columns are exactly the primary key's, in order; the "
            "inspector reports the primary key's own backing index separately.",
            "Review definitions, payload, constraint ownership and dependencies before considering removal. Matching "
            "primary-key columns alone is not evidence that an index is redundant.",
            "https://use-the-index-luke.com/sql/dml",
        ),
        _unique_index_duplicating_primary_key,
    ),
    Rule(
        RuleDefinition(
            "DB-SCHEMA-006",
            "Potential duplicate foreign-key definitions",
            SCHEMA,
            "LOW",
            "Compares exact qualified child-parent pairs plus the reported update/delete actions and deferrability.",
            "Review constraint definitions, match mode, enforcement, validation and dependencies. The inspector does "
            "not establish all these semantics; do not drop a constraint based only on structural overlap.",
            "https://www.postgresql.org/docs/current/ddl-constraints.html",
        ),
        _duplicate_foreign_key,
    ),
    Rule(
        RuleDefinition(
            "DB-SCHEMA-007",
            "Narrow auto-generated primary key",
            SCHEMA,
            "LOW",
            "Detects a single-column, auto-generated (autoincrement/identity/serial) primary key typed TINYINT or "
            "SMALLINT/INT2, regardless of how many rows the table currently has.",
            "Review whether the representable domain fits the intended bounded population. A deliberately small "
            "generated domain is valid. These type bounds do not predict generator headroom, time to exhaustion, or "
            "the number of rows ever inserted.",
            "https://www.postgresql.org/docs/current/datatype-numeric.html",
        ),
        _narrow_generated_primary_key,
    ),
)
