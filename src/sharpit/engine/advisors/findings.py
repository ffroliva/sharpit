"""The finding contract (0.3.0 spec §5.2-5.3): ``Finding``, ``AdvisorRun`` and ``severity_counts_of``."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from sharpit.engine.advisors.report import severity_counts
from sharpit.engine.advisors.rules import SEVERITIES, Severity, severity_rank

_FALLBACK_REASON = "assessment evidence is incomplete"


@dataclass(frozen=True)
class Finding:
    rule_id: str
    advisor: str
    severity: Severity
    target: str
    message: str
    test_node_id: str | None = None
    dismissed: bool = False
    identity: str | None = None

    @property
    def fingerprint(self) -> str:
        """``<advisor>:<rule>:<16 hex>``; the hash input holds no path or timestamp, so it survives reformatting."""
        material = "\x1f".join((self.rule_id, self.identity or self.target, self.test_node_id or ""))
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        return f"{self.advisor}:{self.rule_id}:{digest}"

    def to_dto(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "advisor": self.advisor,
            "severity": self.severity,
            "target": self.target,
            "message": self.message,
            "fingerprint": self.fingerprint,
            "testNodeId": self.test_node_id,
            "dismissed": self.dismissed,
        }


@dataclass(frozen=True)
class AdvisorRun:
    advisor: str
    status: Literal["PASSED", "FAILED", "UNKNOWN"]
    findings: tuple[Finding, ...]
    evidence: dict[str, Any]
    reason: str | None
    app: str | None = None

    @classmethod
    def of(
        cls,
        advisor: str,
        findings: Iterable[Finding],
        evidence: dict[str, Any],
        *,
        scan_status: str | None = None,
        fail_on: Severity = "HIGH",
        app: str | None = None,
    ) -> AdvisorRun:
        """Derive the status (spec §5.3); it is never set by hand."""
        found = tuple(findings)
        gate = severity_rank(fail_on)
        if any(not f.dismissed and severity_rank(f.severity) <= gate for f in found):
            return cls(advisor, "FAILED", found, evidence, None, app)
        limitations: list[str] = evidence.get("limitations") or []
        incomplete = (
            not evidence.get("coverageComplete")
            or (not evidence.get("usable") and bool(limitations))
            or scan_status in ("PARTIAL", "ERROR")
        )
        if incomplete:
            return cls(advisor, "UNKNOWN", found, evidence, limitations[0] if limitations else _FALLBACK_REASON, app)
        return cls(advisor, "PASSED", found, evidence, None, app)

    def to_dto(self) -> dict[str, Any]:
        return {
            "advisor": self.advisor,
            "status": self.status,
            "reason": self.reason,
            "app": self.app,
            "evidence": self.evidence,
            "findings": [f.to_dto() for f in self.findings],
        }


def severity_counts_of(findings: Iterable[Finding]) -> list[dict[str, Any]]:
    """BootUI's ``severityCounts`` form over the non-dismissed findings, one occurrence each."""
    return severity_counts(((f.severity, 1) for f in findings if not f.dismissed), SEVERITIES)
