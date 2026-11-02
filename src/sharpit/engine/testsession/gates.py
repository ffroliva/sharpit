"""The count gates (0.3.0 spec §6.4): queries, N+1 and swallowed exceptions in the call phase. Counts, never time."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sharpit.engine.advisors.findings import Finding

if TYPE_CHECKING:
    from sharpit.engine.testsession.facts import TestFacts

ADVISOR = "test-runtime"
MAX_QUERIES = "sharpit.max-queries"
N_PLUS_ONE = "sharpit.n-plus-one"
EXCEPTION = "sharpit.exception"


def fails(dto: Mapping[str, object]) -> bool:
    """Whether a finding is active and eligible to fail a gate."""
    return not dto["dismissed"] and dto.get("baselineState") != "existing" and dto["severity"] != "INFO"


@dataclass(frozen=True)
class Budget:
    max_queries: int | None
    allow_n_plus_one: bool
    max_exceptions: int


def _finding(
    rule_id: str,
    target: str,
    message: str,
    node_id: str,
    dismissed: Collection[str],
    identity: str | None = None,
    dismissed_pairs: Collection[tuple[str, str]] = (),
    observed: int | None = None,
) -> Finding:
    fingerprint = Finding(rule_id, ADVISOR, "HIGH", target, message, node_id, identity=identity).fingerprint
    is_dismissed = fingerprint in dismissed or (rule_id, identity or target) in dismissed_pairs
    return Finding(rule_id, ADVISOR, "HIGH", target, message, node_id, is_dismissed, identity, observed)


def evaluate_test(
    facts: TestFacts,
    budget: Budget,
    n_plus_one_threshold: int,
    dismissed: Collection[str],
    dismissed_pairs: Collection[tuple[str, str]] = (),
    baseline: Mapping[str, int | None] | None = None,
) -> list[Finding]:
    """The gate findings of one test attempt (call phase only); a dismissed fingerprint stays listed, not failing."""
    call = facts.phases.get("call")
    if call is None:
        return []
    node = facts.key.node_id
    found: list[Finding] = []
    if budget.max_queries is not None and call.queries > budget.max_queries:
        message = f"{call.queries} queries in the call phase (budget {budget.max_queries})"
        found.append(
            _finding(
                MAX_QUERIES,
                node,
                message,
                node,
                dismissed,
                dismissed_pairs=dismissed_pairs,
                observed=call.queries,
            )
        )
    if not budget.allow_n_plus_one:
        threshold = max(2, n_plus_one_threshold)
        for group, count in call.selects.items():
            if count >= threshold:
                message = f"{count} executions of one SELECT in the call phase"
                found.append(
                    _finding(
                        N_PLUS_ONE,
                        call.sql_of.get(group, group),
                        message,
                        node,
                        dismissed,
                        group,
                        dismissed_pairs,
                        count,
                    )
                )
    if call.exceptions > budget.max_exceptions:
        for group, (type_name, text) in call.exception_groups.items():
            target = f"{node}#{group}"
            found.append(
                _finding(
                    EXCEPTION,
                    target,
                    f"{type_name}: {text} (swallowed)",
                    node,
                    dismissed,
                    dismissed_pairs=dismissed_pairs,
                    observed=1,
                )
            )
    if baseline is None:
        return found
    from dataclasses import replace

    return [
        replace(
            finding,
            baseline_state="existing",
        )
        for finding in found
    ]
