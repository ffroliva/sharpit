"""Advisor rule model (port of BootUI ``SeverityOrder.DEFAULT`` and the ``*RuleResultDto`` shape)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import Any, Literal

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
SAMPLE_LIMIT = 10

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
# BootUI 2.2.0 ``*RuleSupport`` vocabulary (WAVE-B contract; spec §4.3); ERROR is an ``analysisErrors`` row
Status = Literal["VIOLATION", "PASS", "SKIPPED", "ERROR"]


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
    status: Status = "PASS"
    violation_count: int = 0
    sample_violations: tuple[str, ...] = ()
    dismissed: bool = False
    sample_locations: tuple[dict[str, Any], ...] = ()  # BootUI ``sampleLocations``; an advisor fills it

    @classmethod
    def evaluate(cls, rule: RuleDefinition, violations: Sequence[str]) -> RuleResult:
        status: Status = "VIOLATION" if violations else "PASS"
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
            "sampleLocations": list(self.sample_locations),
        }


def _definition(rule: RuleDefinition) -> dict[str, Any]:
    return {f.name: getattr(rule, f.name) for f in fields(RuleDefinition)}
