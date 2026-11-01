"""The raw facts of a test session (0.3.0 spec §6.4, §6.8): per test and phase, plus the session-wide evidence."""

from __future__ import annotations

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


def _finding_from(dto: dict[str, Any]) -> Finding:
    return RestoredFinding(
        dto["ruleId"],
        dto["advisor"],
        cast("Severity", dto["severity"]),
        dto["target"],
        dto["message"],
        dto["testNodeId"],
        dto["dismissed"],
        None,
        dto["fingerprint"],
    )


def _run_from(dto: dict[str, Any]) -> AdvisorRun:
    findings = tuple(_finding_from(f) for f in dto["findings"])
    return AdvisorRun(dto["advisor"], dto["status"], findings, dto["evidence"], dto["reason"], dto["app"])


@dataclass(frozen=True)
class TestKey:
    __test__: ClassVar[bool] = False  # not a pytest test class

    node_id: str
    worker: str
    attempt: int


@dataclass
class PhaseFacts:
    queries: int = 0
    filtered: int = 0
    exceptions: int = 0
    selects: Counter[str] = field(default_factory=Counter[str])
    sql_of: dict[str, str] = field(default_factory=dict[str, str])
    exception_groups: dict[str, tuple[str, str]] = field(default_factory=dict[str, tuple[str, str]])

    def to_json(self) -> dict[str, Any]:
        return {
            "queries": self.queries,
            "filtered": self.filtered,
            "exceptions": self.exceptions,
            "selects": dict(self.selects),
            "sqlOf": self.sql_of,
            "exceptionGroups": {k: list(v) for k, v in self.exception_groups.items()},
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
        )


@dataclass
class TestFacts:
    __test__: ClassVar[bool] = False  # not a pytest test class

    key: TestKey
    phases: dict[str, PhaseFacts] = field(default_factory=dict[str, PhaseFacts])
    outcome: str | None = None
    budget: Budget | None = None
    findings: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])

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
            },
            "phases": {name: phase.to_json() for name, phase in self.phases.items()},
            "findings": self.findings,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        budget = data["budget"]
        return cls(
            TestKey(data["nodeId"], data["worker"], data["attempt"]),
            {name: PhaseFacts.from_json(phase) for name, phase in data["phases"].items()},
            data["outcome"],
            None if budget is None else Budget(budget["maxQueries"], budget["allowNPlusOne"], budget["maxExceptions"]),
            list(data["findings"]),
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
        )
