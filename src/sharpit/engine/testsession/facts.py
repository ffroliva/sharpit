"""The raw facts of a test session (0.3.0 spec §6.4, §6.8): per test and phase, plus the session-wide evidence."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, ClassVar, Self, cast

from sharpit.engine.advisors.findings import AdvisorRun, Finding
from sharpit.engine.advisors.rules import Severity
from sharpit.engine.testsession.gates import Budget

PHASES = ("setup", "call", "teardown")


@dataclass(frozen=True)
class RestoredFinding(Finding):
    """A finding read back from JSON: its identity is gone, so it keeps the fingerprint it was shipped with."""

    shipped_fingerprint: str = ""

    @property
    def fingerprint(self) -> str:
        return self.shipped_fingerprint


def finding_from(dto: dict[str, Any]) -> Finding:
    return RestoredFinding(
        rule_id=dto["ruleId"],
        advisor=dto["advisor"],
        severity=cast("Severity", dto["severity"]),
        target=dto["target"],
        message=dto["message"],
        test_node_id=dto["testNodeId"],
        dismissed=dto["dismissed"],
        identity=None,
        observed=dto.get("observed"),
        baseline_state=dto.get("baselineState"),
        shipped_fingerprint=dto["fingerprint"],
    )


def _run_from(dto: dict[str, Any]) -> AdvisorRun:
    findings = tuple(finding_from(f) for f in dto["findings"])
    return AdvisorRun(dto["advisor"], dto["status"], findings, dto["evidence"], dto["reason"], dto["app"])


@dataclass(frozen=True)
class TestKey:
    __test__: ClassVar[bool] = False  # not a pytest test class

    node_id: str
    worker: str
    attempt: int


@dataclass(frozen=True)
class SwallowedFact:
    """A broad handler in application code that swallowed an exception: never the message or a local value.

    ``test_double`` only says that a test double (a ``unittest.mock`` object) raised it; the message that decided it
    is read once and never kept.
    """

    location: str  # ``path:line`` of the except clause, relative to the pytest rootdir when under it
    type_name: str
    programming_error: bool
    # ``path:scope:Type#<8 hex>[.n/m]``, built by the worker from the parsed source; None from an earlier worker
    identity: str | None = None
    # ``path:line`` relative to the working directory, as 0.4.0 to 0.6.0 wrote it: only to name a stale legacy entry
    legacy_location: str | None = None
    # not part of the identity: one clause hit by a double and by real code is one fact, which the real raise clears
    test_double: bool = field(default=False, compare=False)

    def to_json(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "type": self.type_name,
            "programmingError": self.programming_error,
            "identity": self.identity,
            "legacyLocation": self.legacy_location,
            "testDouble": self.test_double,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(
            data["location"],
            data["type"],
            data["programmingError"],
            data.get("identity"),
            data.get("legacyLocation"),
            data.get("testDouble", False),
        )


@dataclass
class UnboundedReadFact:
    route: str
    statement: str
    entity: str
    loaded: int
    page_size: int
    has_limit: bool
    location: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "statement": self.statement,
            "entity": self.entity,
            "loaded": self.loaded,
            "pageSize": self.page_size,
            "hasLimit": self.has_limit,
            "location": self.location,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(
            data["route"],
            data["statement"],
            data["entity"],
            data["loaded"],
            data["pageSize"],
            data["hasLimit"],
            data.get("location"),
        )


MAX_HTTP_VARIANTS_PER_ROUTE = 64  # distinct (status, header presence) pairs kept per configured route
MAX_HTTP_METHODS = 16  # distinct methods counted in the route-state tallies
_HTTP_METHOD = re.compile(r"[A-Z]{1,16}")


@dataclass
class HttpFacts:
    """The HTTP exchanges one test attempt made, reduced to what a configured expectation reads (T1).

    Only configured ``(method, route)`` keys are kept, each as ``(status, configured headers present)`` plus a count,
    so the size follows the configuration and the status range, never the request count. A route that is not
    matched (``not_found``) or whose metadata is missing (``unobservable``) is a per-method tally: it matches no
    expectation, but an unobservable one may have hidden an exchange of any route. No value, body, path or node id.
    """

    exchanges: dict[tuple[str, str, int, tuple[str, ...]], int] = field(
        default_factory=dict[tuple[str, str, int, tuple[str, ...]], int]
    )
    incomplete: set[tuple[str, str]] = field(default_factory=set[tuple[str, str]])  # routes that overflowed
    unobservable: dict[str, int] = field(default_factory=dict[str, int])
    not_found: dict[str, int] = field(default_factory=dict[str, int])
    overflow: bool = False  # more methods than the tallies hold

    def record(self, method: str, state: str, route: str, status: int, present: tuple[str, ...]) -> None:
        method = method if _HTTP_METHOD.fullmatch(method) else "OTHER"  # the client picks the method: bound its text
        if state == "matched":
            self._matched(method, route, status, tuple(sorted(present)))
            return
        tally = self.unobservable if state == "unobservable" else self.not_found
        if method not in tally and len(tally) >= MAX_HTTP_METHODS:
            self.overflow = True
            return
        tally[method] = tally.get(method, 0) + 1

    def _matched(self, method: str, route: str, status: int, present: tuple[str, ...]) -> None:
        key = (method, route, status, present)
        if key in self.exchanges:
            self.exchanges[key] += 1
        elif sum(1 for k in self.exchanges if k[:2] == (method, route)) >= MAX_HTTP_VARIANTS_PER_ROUTE:
            self.incomplete.add((method, route))
        else:
            self.exchanges[key] = 1

    def to_json(self) -> dict[str, Any]:
        return {
            "exchanges": [[m, r, s, list(p), c] for (m, r, s, p), c in sorted(self.exchanges.items())],
            "incomplete": sorted([m, r] for m, r in self.incomplete),
            "unobservable": dict(sorted(self.unobservable.items())),
            "notFound": dict(sorted(self.not_found.items())),
            "overflow": self.overflow,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(
            {(m, r, s, tuple(p)): c for m, r, s, p, c in data["exchanges"]},
            {(m, r) for m, r in data["incomplete"]},
            dict(data["unobservable"]),
            dict(data["notFound"]),
            data["overflow"],
        )


@dataclass
class PhaseFacts:
    queries: int = 0
    filtered: int = 0
    exceptions: int = 0
    selects: Counter[str] = field(default_factory=Counter[str])
    sql_of: dict[str, str] = field(default_factory=dict[str, str])
    exception_groups: dict[str, tuple[str, str]] = field(default_factory=dict[str, tuple[str, str]])
    relationship_loads: Counter[str] = field(default_factory=Counter[str])
    relationship_of: dict[str, tuple[str, bool]] = field(default_factory=dict[str, tuple[str, bool]])
    relationship_sites: dict[str, str | None] = field(default_factory=dict[str, str | None])
    swallowed: list[SwallowedFact] = field(default_factory=list[SwallowedFact])
    unbounded_reads: list[UnboundedReadFact] = field(default_factory=list[UnboundedReadFact])
    # repeated-SELECT group -> (first application site, batched-query suggestion), for groups with no relationship
    statement_sites: dict[str, tuple[str | None, str]] = field(default_factory=dict[str, tuple[str | None, str]])

    def to_json(self) -> dict[str, Any]:
        return {
            "queries": self.queries,
            "filtered": self.filtered,
            "exceptions": self.exceptions,
            "selects": dict(self.selects),
            "sqlOf": self.sql_of,
            "exceptionGroups": {k: list(v) for k, v in self.exception_groups.items()},
            "relationshipLoads": dict(self.relationship_loads),
            "relationshipOf": {k: list(v) for k, v in self.relationship_of.items()},
            "relationshipSites": self.relationship_sites,
            "swallowed": [fact.to_json() for fact in self.swallowed],
            "unboundedReads": [fact.to_json() for fact in self.unbounded_reads],
            "statementSites": {k: list(v) for k, v in self.statement_sites.items()},
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(
            data["queries"],
            data["filtered"],
            data["exceptions"],
            Counter(data["selects"]),
            dict(data["sqlOf"]),
            {k: (v[0], v[1]) for k, v in data["exceptionGroups"].items()},
            Counter(data.get("relationshipLoads", {})),
            {k: (v[0], v[1]) for k, v in data.get("relationshipOf", {}).items()},
            dict(data.get("relationshipSites", {})),
            [SwallowedFact.from_json(fact) for fact in data.get("swallowed", [])],
            [UnboundedReadFact.from_json(fact) for fact in data.get("unboundedReads", [])],
            {k: (v[0], v[1]) for k, v in data.get("statementSites", {}).items()},
        )


@dataclass
class TestFacts:
    __test__: ClassVar[bool] = False  # not a pytest test class

    key: TestKey
    phases: dict[str, PhaseFacts] = field(default_factory=dict[str, PhaseFacts])
    outcome: str | None = None
    budget: Budget | None = None
    findings: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    http: HttpFacts = field(default_factory=HttpFacts)

    def to_json(self) -> dict[str, Any]:
        budget = self.budget
        return {
            "nodeId": self.key.node_id,
            "worker": self.key.worker,
            "attempt": self.key.attempt,
            "outcome": self.outcome,
            "budget": None
            if budget is None
            else {
                "maxQueries": budget.max_queries,
                "allowNPlusOne": budget.allow_n_plus_one,
                "maxExceptions": budget.max_exceptions,
                "allowSwallowed": budget.allow_swallowed,
                "allowUnboundedRead": budget.allow_unbounded_read,
                "unboundedReadFactor": budget.unbounded_read_factor,
                "reason": budget.reason,
            },
            "phases": {name: phase.to_json() for name, phase in self.phases.items()},
            "findings": self.findings,
            "http": self.http.to_json(),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        budget = data["budget"]
        return cls(
            TestKey(data["nodeId"], data["worker"], data["attempt"]),
            {name: PhaseFacts.from_json(phase) for name, phase in data["phases"].items()},
            data["outcome"],
            None
            if budget is None
            else Budget(
                budget["maxQueries"],
                budget["allowNPlusOne"],
                budget["maxExceptions"],
                budget.get("allowSwallowed", False),
                budget.get("allowUnboundedRead", False),
                budget.get("unboundedReadFactor", 2),
                budget.get("reason"),
            ),
            list(data["findings"]),
            HttpFacts.from_json(data["http"]) if "http" in data else HttpFacts(),
        )


@dataclass
class SessionFacts:
    worker: str
    tests: list[TestFacts] = field(default_factory=list[TestFacts])
    unattributed: int = 0
    top_unattributed: dict[str, int] = field(default_factory=dict[str, int])
    unattributed_exceptions: int = 0
    filtered: int = 0
    sources: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    untraced_drivers: set[str] = field(default_factory=set[str])
    engine_drivers: set[str] = field(default_factory=set[str])
    preexisting: int = 0
    aliases: list[str] = field(default_factory=list[str])
    advisor_runs: list[AdvisorRun] = field(default_factory=list[AdvisorRun])
    warnings: list[str] = field(default_factory=list[str])
    exceptions_source_ok: bool = True
    sqlite_seen: bool = False
    http_unassociated: HttpFacts = field(default_factory=HttpFacts)

    def to_json(self) -> dict[str, Any]:
        return {
            "worker": self.worker,
            "tests": [t.to_json() for t in self.tests],
            "unattributed": self.unattributed,
            "topUnattributed": self.top_unattributed,
            "unattributedExceptions": self.unattributed_exceptions,
            "filtered": self.filtered,
            "sources": self.sources,
            "untracedDrivers": sorted(self.untraced_drivers),
            "engineDrivers": sorted(self.engine_drivers),
            "preexisting": self.preexisting,
            "aliases": self.aliases,
            "advisorRuns": [r.to_dto() for r in self.advisor_runs],
            "warnings": self.warnings,
            "exceptionsSourceOk": self.exceptions_source_ok,
            "sqliteSeen": self.sqlite_seen,
            "httpUnassociated": self.http_unassociated.to_json(),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(
            data["worker"],
            [TestFacts.from_json(t) for t in data["tests"]],
            data["unattributed"],
            dict(data["topUnattributed"]),
            data["unattributedExceptions"],
            data["filtered"],
            list(data["sources"]),
            set(data["untracedDrivers"]),
            set(data["engineDrivers"]),
            data["preexisting"],
            list(data["aliases"]),
            [_run_from(r) for r in data["advisorRuns"]],
            list(data["warnings"]),
            data["exceptionsSourceOk"],
            data.get("sqliteSeen", False),
            HttpFacts.from_json(data["httpUnassociated"]) if "httpUnassociated" in data else HttpFacts(),
        )
