"""The count gates (0.3.0 spec §6.4): queries, N+1 and swallowed exceptions in the call phase. Counts, never time."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.findings import fails as fails  # the one predicate, re-exported
from sharpit.engine.advisors.rules import Severity

if TYPE_CHECKING:
    from sharpit.engine.testsession.facts import PhaseFacts, TestFacts

ADVISOR = "test-runtime"
MAX_QUERIES = "sharpit.max-queries"
N_PLUS_ONE = "sharpit.n-plus-one"
EXCEPTION = "sharpit.exception"
SWALLOWED = "sharpit.swallowed-exception"
UNBOUNDED_READ = "sharpit.unbounded-read"
# PEP 249 error classes (sqlite3, the DB-API drivers and SQLAlchemy keep these names): a failed query swallowed into a
# default value hides a broken schema or statement (bench D13). shortcut: matched by class name only, so a driver
# subclass with its own name (psycopg's UndefinedTable, unwrapped) stays a note; upgrade: record the MRO in the fact.
DATABASE_ERRORS = frozenset(
    {
        "DatabaseError",
        "DBAPIError",
        "OperationalError",
        "ProgrammingError",
        "IntegrityError",
        "DataError",
        "InternalError",
        "InterfaceError",
        "NotSupportedError",
    }
)


@dataclass(frozen=True)
class Budget:
    max_queries: int | None
    allow_n_plus_one: bool
    max_exceptions: int
    allow_swallowed: bool = False
    allow_unbounded_read: bool = False
    unbounded_read_factor: int = 2


def _finding(
    rule_id: str,
    target: str,
    message: str,
    node_id: str,
    dismissed: Collection[str],
    identity: str | None = None,
    dismissed_pairs: Collection[tuple[str, str]] = (),
    observed: int | None = None,
    *,
    severity: Severity = "HIGH",
) -> Finding:
    fingerprint = Finding(rule_id, ADVISOR, severity, target, message, node_id, identity=identity).fingerprint
    is_dismissed = fingerprint in dismissed or (rule_id, identity or target) in dismissed_pairs
    return Finding(rule_id, ADVISOR, severity, target, message, node_id, is_dismissed, identity, observed)


def _swallowed_findings(
    call: PhaseFacts,
    budget: Budget,
    node: str,
    dismissed: Collection[str],
    dismissed_pairs: Collection[tuple[str, str]],
) -> list[Finding]:
    """A programming or database error swallowed by a broad handler fails the test unless relaxed; any other swallow is
    a note."""
    found: list[Finding] = []
    for fact in call.swallowed:
        gating = fact.programming_error or fact.type_name in DATABASE_ERRORS
        severity: Severity = "HIGH" if gating and not budget.allow_swallowed else "INFO"
        message = (
            f"{fact.type_name} swallowed by a broad except clause at {fact.location} (neither re-raised nor logged)"
        )
        identity = f"{fact.location}:{fact.type_name}"
        found.append(
            _finding(
                SWALLOWED, fact.location, message, node, dismissed, identity, dismissed_pairs, 1, severity=severity
            )
        )
    return found


def _unbounded_read_findings(
    call: PhaseFacts,
    budget: Budget,
    node: str,
    dismissed: Collection[str],
    dismissed_pairs: Collection[tuple[str, str]],
) -> list[Finding]:
    if budget.allow_unbounded_read:
        return []
    found: list[Finding] = []
    for fact in call.unbounded_reads:
        if fact.has_limit or fact.loaded < fact.page_size * budget.unbounded_read_factor:
            continue
        location = f" at {fact.location}" if fact.location else ""
        message = (
            f"{fact.route} materialized {fact.loaded} {fact.entity} rows for page size {fact.page_size}{location}; "
            f"masked statement: {fact.statement}"
        )
        found.append(
            _finding(
                UNBOUNDED_READ,
                fact.statement,
                message,
                node,
                dismissed,
                identity=f"{fact.route}:{fact.statement}",
                dismissed_pairs=dismissed_pairs,
                observed=fact.loaded,
            )
        )
    return found


def _n_plus_one_message(call: PhaseFacts, group: str, count: int) -> str:
    message = f"{count} executions of one SELECT in the call phase"
    relation = call.relationship_of.get(group)
    if relation is None:
        site = call.statement_sites.get(group)
        if site is None:
            return message
        location, batched = site
        statement = call.sql_of.get(group, "the masked SELECT")
        return (
            f"{message}; first at {location or 'unknown'}; batch into one query: {batched}; "
            f"masked statement: {statement}"
        )
    identity, collection = relation
    relation_count = call.relationship_loads.get(identity, count)
    loader = "selectinload" if collection else "joinedload"
    statement = call.sql_of.get(group, call.sql_of.get(identity, "the masked SELECT"))
    return (
        f"{identity} lazy-loaded {relation_count} times; {loader}({identity}); "
        f"first lazy load at {call.relationship_sites.get(identity) or 'unknown'}; "
        f"masked statement: {statement}; {message}"
    )


def _query_findings(
    call: PhaseFacts,
    node: str,
    budget: Budget,
    dismissed: Collection[str],
    dismissed_pairs: Collection[tuple[str, str]],
) -> list[Finding]:
    if budget.max_queries is None or call.queries <= budget.max_queries:
        return []
    message = f"{call.queries} queries in the call phase (budget {budget.max_queries})"
    return [
        _finding(
            MAX_QUERIES,
            node,
            message,
            node,
            dismissed,
            dismissed_pairs=dismissed_pairs,
            observed=call.queries,
        )
    ]


def _n_plus_one_findings(
    call: PhaseFacts,
    node: str,
    budget: Budget,
    threshold: int,
    dismissed: Collection[str],
    dismissed_pairs: Collection[tuple[str, str]],
) -> list[Finding]:
    if budget.allow_n_plus_one:
        return []
    found: list[Finding] = []
    for group, count in call.selects.items():
        if count >= max(2, threshold):
            found.append(
                _finding(
                    N_PLUS_ONE,
                    call.sql_of.get(group, group),
                    _n_plus_one_message(call, group, count),
                    node,
                    dismissed,
                    group,
                    dismissed_pairs,
                    count,
                )
            )
    return found


def _exception_findings(
    call: PhaseFacts,
    node: str,
    budget: Budget,
    dismissed: Collection[str],
    dismissed_pairs: Collection[tuple[str, str]],
) -> list[Finding]:
    if call.exceptions <= budget.max_exceptions:
        return []
    return [
        _finding(
            EXCEPTION,
            f"{node}#{group}",
            f"{type_name}: {text} (swallowed)",
            node,
            dismissed,
            dismissed_pairs=dismissed_pairs,
            observed=1,
        )
        for group, (type_name, text) in call.exception_groups.items()
    ]


def _annotate_baseline(found: list[Finding], baseline: Mapping[str, int | None]) -> list[Finding]:
    annotated: list[Finding] = []
    for finding in found:
        old_count = baseline.get(finding.fingerprint)
        existing = finding.fingerprint in baseline and (
            old_count is None or finding.observed is None or finding.observed <= old_count
        )
        annotated.append(replace(finding, baseline_state="existing" if existing else "new"))
    return annotated


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
    found = _query_findings(call, node, budget, dismissed, dismissed_pairs)
    found.extend(_n_plus_one_findings(call, node, budget, n_plus_one_threshold, dismissed, dismissed_pairs))
    found.extend(_exception_findings(call, node, budget, dismissed, dismissed_pairs))
    found.extend(_swallowed_findings(call, budget, node, dismissed, dismissed_pairs))
    found.extend(_unbounded_read_findings(call, budget, node, dismissed, dismissed_pairs))
    return found if baseline is None else _annotate_baseline(found, baseline)
