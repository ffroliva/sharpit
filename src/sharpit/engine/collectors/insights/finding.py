"""Runtime Insights contract: what one kind's evaluation found (BootUI ``Finding`` and ``Observation.Evaluation``)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Finding:
    key: str
    subject: str
    sufficient: bool
    sentence: str
    eligible: int
    affected: int
    what_to_check: list[str]
    exemplar_request_ids: list[str]
    columns: list[str]
    rows: list[list[str]]
    limitations: list[str]
    tier: str | None = None
    unlisted: str | None = None

    @property
    def listed(self) -> bool:
        return self.unlisted is None

    def unlisted_whole(self, reason: str | None) -> Finding:
        """``Finding.unlistedWhole``: the kind's reason replaces the row's own."""
        return replace(self, unlisted=reason)


@dataclass(frozen=True)
class Evaluation:
    """What one evaluation examined: ``eligible`` requests, its findings, what it left out, and whether it had work."""

    eligible: int
    findings: list[Finding] = field(default_factory=list[Finding])
    uncounted: str | None = None
    has_eligible_work: bool = False

    @property
    def worked(self) -> bool:
        return self.has_eligible_work or self.eligible > 0 or any(f.sufficient for f in self.findings)
