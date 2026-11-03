"""Vendor rules DB-PG-*, DB-MYSQL-*, DB-SCHEMA-010 and DB-SERVER-001/002 (skeleton)."""

from __future__ import annotations

from typing import Any

from sharpit.engine.advisors.rules import RuleDefinition, Severity
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Rule, Source
from sharpit.engine.sqla.inspect import CatalogBounds


def read_vendor(conn: Any, bounds: CatalogBounds) -> dict[str, Any]:
    del conn, bounds
    return {}


def _never(source: Source) -> Outcome:
    del source
    return [("?", "?", "?")]


def _rule(rule_id: str, title: str, category: str, severity: Severity) -> Rule:
    return Rule(RuleDefinition(rule_id, title, category, severity, "", "", ""), _never)


RULES = (
    _rule("DB-SCHEMA-010", "Invisible or ignored indexes", "Schema", "LOW"),
    _rule("DB-PG-001", "Invalid PostgreSQL indexes", "PostgreSQL", "HIGH"),
    _rule("DB-PG-002", "PostgreSQL sequence nearing exhaustion", "PostgreSQL", "HIGH"),
    _rule("DB-PG-003", "PostgreSQL NOT VALID constraint never validated", "PostgreSQL", "MEDIUM"),
    _rule("DB-PG-004", "PostgreSQL table lacking usable replica identity", "PostgreSQL", "MEDIUM"),
    _rule("DB-PG-005", "PostgreSQL unlogged tables", "PostgreSQL", "LOW"),
    _rule("DB-MYSQL-001", "Tables on a non-transactional storage engine", "MySQL", "MEDIUM"),
    _rule("DB-MYSQL-002", "Tables/columns using the legacy utf8mb3 character set", "MySQL", "MEDIUM"),
    _rule("DB-MYSQL-003", "MySQL/MariaDB AUTO_INCREMENT nearing exhaustion", "MySQL", "HIGH"),
    _rule("DB-SERVER-001", "PostgreSQL does not end sessions that are idle in a transaction", "Server", "LOW"),
    _rule("DB-SERVER-002", "PostgreSQL has no statement timeout", "Server", "LOW"),
)
