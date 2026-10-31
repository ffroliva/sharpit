"""Advisor rule model (port of BootUI ``SeverityOrder.DEFAULT`` and the ``*RuleResultDto`` shape)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import Any, Literal

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
SAMPLE_LIMIT = 10

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
Status = Literal["PASSED", "FAILED", "SKIPPED"]


def severity_rank(severity: str) -> int:
    """Lower is more severe; an unknown severity sorts after every known one (``SeverityOrder.rank``)."""
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    name: str
    category: str
    severity: Severity
    description: str
    recommendation: str
    learn_more_url: str


@dataclass(frozen=True)
class RuleResult(RuleDefinition):
    status: Status = "PASSED"
    violation_count: int = 0
    sample_violations: tuple[str, ...] = ()
    dismissed: bool = False

    @classmethod
    def evaluate(cls, rule: RuleDefinition, violations: Sequence[str]) -> RuleResult:
        status: Status = "FAILED" if violations else "PASSED"
        return cls(
            **_definition(rule),
            status=status,
            violation_count=len(violations),
            sample_violations=tuple(violations[:SAMPLE_LIMIT]),
        )

    @classmethod
    def skipped(cls, rule: RuleDefinition) -> RuleResult:
        return cls(**_definition(rule), status="SKIPPED")

    def to_dto(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "status": self.status,
            "violationCount": self.violation_count,
            "sampleViolations": list(self.sample_violations),
            "recommendation": self.recommendation,
            "learnMoreUrl": self.learn_more_url,
            "dismissed": self.dismissed,
        }


def _definition(rule: RuleDefinition) -> dict[str, Any]:
    return {f.name: getattr(rule, f.name) for f in fields(RuleDefinition)}
