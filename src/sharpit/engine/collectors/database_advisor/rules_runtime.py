"""Runtime SQL rule DB-RUNTIME-001 over the SQL Trace ring (skeleton)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Rule, Source


def facts(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    del rows
    return {"statements": 0, "shapes": []}


def _never(source: Source) -> Outcome:
    del source
    return [("?", "?", "?"), ("?", "?", "?")]


RULES = (
    Rule(
        RuleDefinition(
            "DB-RUNTIME-001", "SQL text variations with predicate literals", "Runtime SQL", "LOW", "", "", ""
        ),
        _never,
    ),
)
