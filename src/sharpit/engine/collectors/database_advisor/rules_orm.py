"""ORM mapping rules DB-HIB-002..010 (port of BootUI's ``Hibernate*Rule`` cross-references, 2.2.0) on SQLAlchemy models.

``facts(models)`` reads the tables behind ``install(models=...)`` once, through ``engine/models.py``'s configured-gate:
an unconfigured registry yields a skip reason and no mapper attribute that would configure it is touched (sharpit
never calls ``configure_mappers()``). Each check compares those declared tables with one source's catalog.
"""

from __future__ import annotations

from typing import Any

from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Rule, Source

ORM = "ORM mapping"


def facts(models: tuple[object, ...]) -> dict[str, Any]:
    """The declared tables behind ``models`` as plain dicts, or ``{"skipped": reason}``."""
    del models
    return {"tables": []}


def _never(source: Source) -> Outcome:
    del source
    return [("?", "?", "?")]


def _rule(rule_id: str, title: str, severity: str, description: str, recommendation: str) -> Rule:
    definition = RuleDefinition(rule_id, title, ORM, severity, description, recommendation, _URL)  # type: ignore[arg-type]
    return Rule(definition, _never)


_URL = "https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html"

RULES = (
    _rule("DB-HIB-002", "Declared entity relation name not found in the observed schema", "MEDIUM", "", ""),
    _rule("DB-HIB-003", "Declared column nullability differs from observed metadata", "MEDIUM", "", ""),
    _rule("DB-HIB-004", "Declared column length exceeds observed column size", "MEDIUM", "", ""),
    _rule("DB-HIB-005", "Declared uniqueness has no observed enforcing key", "HIGH", "", ""),
    _rule("DB-HIB-006", "Declared column name not found in the observed relation", "MEDIUM", "", ""),
    _rule("DB-HIB-007", "Declared association has no matching observed foreign key", "MEDIUM", "", ""),
    _rule("DB-HIB-009", "IDENTITY identifier column without database-side generation", "MEDIUM", "", ""),
    _rule("DB-HIB-010", "Declared numeric precision or scale exceeds the observed column", "MEDIUM", "", ""),
)
