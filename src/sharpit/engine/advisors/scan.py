"""The advisor scan core (0.5.0 spec §4.3): skeleton."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.retention import MAX_PAGE_LIMIT
from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight


@dataclass(frozen=True)
class ScanSpec:
    id: str
    analyzer: str
    disclaimer: str
    not_scanned_message: str

    @property
    def operation(self) -> str:
        return f"{self.id}-scan"


@dataclass(frozen=True)
class Evaluation:
    status: str
    message: str
    evaluated: tuple[str, ...]
    findings: tuple[Finding, ...]
    evidence: dict[str, Any]
    detail: Any = None


@dataclass(frozen=True)
class Scope:
    lists: Mapping[str, Any] = field(default_factory=dict[str, Any])
    counts: Mapping[str, int] = field(default_factory=dict[str, int])


def no_extra_sections(_done: Evaluation | None) -> Mapping[str, Any]:
    return {}


class AdvisorScan:
    def __init__(
        self,
        spec: ScanSpec,
        rules: Sequence[RuleDefinition],
        run: Callable[[Any], Evaluation],
        *,
        scope: Callable[[Evaluation | None], Scope],
        extra_sections: Callable[[Evaluation | None], Mapping[str, Any]] = no_extra_sections,
        dismissals: DismissalStore,
        masker: Masker,
        single_flight: SingleFlight,
        max_retained: int,
    ) -> None:
        self.spec = spec
        self.dismissals = dismissals
        self.single_flight = single_flight

    def report(self) -> dict[str, Any]:
        return {"scan": {"status": "NOT_SCANNED"}, "results": [], "violationDetails": {"scanId": None}}

    def scan(self, request: Any = None) -> dict[str, Any]:
        return self.report()

    def violations(
        self,
        rule_id: str | None,
        scan_id: str | None,
        offset: int | None,
        limit: int | None,
        max_results: int = MAX_PAGE_LIMIT,
    ) -> dict[str, Any]:
        return {"violations": []}
