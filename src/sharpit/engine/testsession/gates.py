"""The count gates (0.3.0 spec §6.4): queries, N+1 and swallowed exceptions in the call phase. Counts, never time."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from sharpit.engine.advisors.findings import Finding

if TYPE_CHECKING:
    from sharpit.engine.testsession.facts import TestFacts

ADVISOR = "test-runtime"
MAX_QUERIES = "sharpit.max-queries"
N_PLUS_ONE = "sharpit.n-plus-one"
EXCEPTION = "sharpit.exception"


@dataclass(frozen=True)
class Budget:
    max_queries: int | None
    allow_n_plus_one: bool
    max_exceptions: int


def _finding(
    rule_id: str, target: str, message: str, node_id: str, dismissed: Collection[str], identity: str | None = None
) -> Finding:
    finding = Finding(rule_id, ADVISOR, "HIGH", target, message, node_id, identity=identity)
    return replace(finding, dismissed=finding.fingerprint in dismissed)


def evaluate_test(
    facts: TestFacts, budget: Budget, n_plus_one_threshold: int, dismissed: Collection[str]
) -> list[Finding]:
    """The gate findings of one test attempt (call phase only); a dismissed fingerprint stays listed, not failing."""
    call = facts.phases.get("call")
    if call is None:
        return []
    node = facts.key.node_id
    found: list[Finding] = []
    if budget.max_queries is not None and call.queries > budget.max_queries:
        message = f"{call.queries} queries in the call phase (budget {budget.max_queries})"
        found.append(_finding(MAX_QUERIES, node, message, node, dismissed))
    if not budget.allow_n_plus_one:
        threshold = max(2, n_plus_one_threshold)
        for group, count in call.selects.items():
            if count >= threshold:
                message = f"{count} executions of one SELECT in the call phase"
                found.append(_finding(N_PLUS_ONE, call.sql_of.get(group, group), message, node, dismissed, group))
    if call.exceptions > budget.max_exceptions:
        for group, (type_name, text) in call.exception_groups.items():
            target = f"{node}#{group}"
            found.append(_finding(EXCEPTION, target, f"{type_name}: {text} (swallowed)", node, dismissed))
    return found
