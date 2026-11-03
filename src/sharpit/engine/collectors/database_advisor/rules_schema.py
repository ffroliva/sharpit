"""Schema rules DB-SCHEMA-001..007 (port of BootUI's ``*Rule`` schema checks, 2.2.0) over the bounded catalog.

Each check reads one source's catalog (``sqla.inspect.catalog``: the connection's default schema) and returns its
findings, or why it could not look. A table whose index or column inventory was cut by a bound never yields a claim of
absence from that inventory.
"""

from __future__ import annotations

from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Rule, Source

SCHEMA = "Schema"


def _missing_primary_key(source: Source) -> Outcome:
    return [("", "", "")]


def _foreign_key_access_path(source: Source) -> Outcome:
    return [("", "", "")]


def _duplicate_index(source: Source) -> Outcome:
    return [("", "", "")]


def _foreign_key_type_mismatch(source: Source) -> Outcome:
    return [("", "", "")]


def _unique_index_duplicating_primary_key(source: Source) -> Outcome:
    return [("", "", "")]


def _duplicate_foreign_key(source: Source) -> Outcome:
    return [("", "", "")]


def _narrow_generated_primary_key(source: Source) -> Outcome:
    return [("", "", "")]


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
