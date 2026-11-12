"""The advisor scan core (0.5.0 spec §4.3; port of BootUI's shared ``*Scanner.scan``/``lastReport`` flow), extracted
from the REST API advisor so every advisor reports, scans, pages and dismisses the same way.

An advisor supplies a ``ScanSpec`` (its texts), its rule definitions, a ``run`` callable that evaluates the rules and
returns an ``Evaluation``, a ``scope`` hook (its scope list and count keys, e.g. ``basePackages``/``classesAnalyzed``)
and optional ``extra_sections`` (e.g. ``analysisErrors``, ``diagnostics``). Both hooks get ``None`` before the first
scan. ``report()`` never scans: it renders the last completed scan, or ``NOT_SCANNED``. ``scan()`` runs on its own
single-flight (``ActionBusy`` -> 409). Every string an advisor hands the core (finding targets and messages, the scan
message, limitations, scope lists, extra sections) is masked before it is kept or rendered. The report and the
retained details are replaced together, so a report's ``scanId`` always pages its own details. Dismissals are re-read
and applied on every render; the cache is never changed by them.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, cast

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.report import apply_dismissals, evidence, severity_counts
from sharpit.engine.advisors.retention import MAX_PAGE_LIMIT, ViolationRetention
from sharpit.engine.advisors.rules import SEVERITIES, RuleDefinition, RuleResult, severity_rank
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
    """One pass of an advisor's rules: what ran, what it found; nothing dismissed."""

    status: str  # SCANNED | PARTIAL | ERROR | DISABLED
    message: str
    evaluated: tuple[str, ...]  # ids of the rules that ran to completion
    findings: tuple[Finding, ...]
    evidence: dict[str, Any]
    detail: Any = None  # the advisor's own facts, for its scope and extra-section hooks
    skipped: tuple[str, ...] = ()  # ids reported SKIPPED: counted in rulesEvaluated, never evaluated (BootUI skipped())


@dataclass(frozen=True)
class Scope:
    """An advisor's scope keys: ``lists`` at the top level only, ``counts`` at the top level and in ``scan``."""

    lists: Mapping[str, Any] = field(default_factory=dict[str, Any])
    counts: Mapping[str, int] = field(default_factory=dict[str, int])


def no_extra_sections(_done: Evaluation | None) -> Mapping[str, Any]:
    return {}


def mask(masker: Masker, text: str) -> str:
    masked = masker.mask_text(text)
    return masked if masked is not None else masker.mask_path(text)  # METADATA_ONLY: paths stay visible


def _mask_tree(masker: Masker, value: Any) -> Any:
    if isinstance(value, str):
        return mask(masker, value)
    if isinstance(value, Mapping):
        return {k: _mask_tree(masker, v) for k, v in cast("Mapping[str, Any]", value).items()}
    if isinstance(value, list | tuple):
        return [_mask_tree(masker, v) for v in cast("Iterable[Any]", value)]
    return value


def violating(results: Iterable[RuleResult]) -> list[RuleResult]:
    """Only the violating rules, most severe first, then the most violations, then by id (``violationResults``)."""
    found = [r for r in results if r.status == "VIOLATION"]
    return sorted(found, key=lambda r: (severity_rank(r.severity), -r.violation_count, r.id))


def build_report(
    spec: ScanSpec,
    status: str,
    message: str,
    scanned_at: int | None,
    scope: Scope,
    results: Sequence[RuleResult],
    rules_evaluated: int,
    report_evidence: dict[str, Any],
    extra: Mapping[str, Any],
) -> dict[str, Any]:
    """The shared report shape (WAVE-B contract): scope keys, counts, ``scan``, ``results``, evidence, extras."""
    violations = violating(results)
    return {
        "localOnly": True,
        "disclaimer": spec.disclaimer,
        **scope.lists,
        **scope.counts,
        "rulesEvaluated": rules_evaluated,
        "violationsFound": len(violations),
        "severityCounts": severity_counts(((r.severity, r.violation_count) for r in violations), SEVERITIES),
        "scan": {
            "analyzer": spec.analyzer,
            "status": status,
            "message": message,
            "scannedAt": scanned_at,
            "rulesEvaluated": rules_evaluated,
            **scope.counts,
            "violationsFound": len(violations),
        },
        "results": [r.to_dto() for r in violations],
        "evidence": report_evidence,
        "violationDetails": {},
        **extra,
    }


@dataclass(frozen=True)
class _Scan:
    report: dict[str, Any]  # as built, before dismissals
    occurrences: dict[str, list[tuple[str, str, str]]]  # (fingerprint, text, identity or target)


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
        self.rules = tuple(rules)
        self._run = run
        self._scope = scope
        self._extra = extra_sections
        self.dismissals = dismissals
        self._masker = masker
        self.single_flight = single_flight
        self._retention = ViolationRetention(max_retained)
        self._cached: _Scan | None = None
        self._swap = threading.Lock()  # retention and cache are replaced (and read) together

    def report(self) -> dict[str, Any]:
        """The last completed scan, else ``NOT_SCANNED``; dismissals applied. Never scans."""
        with self._swap:
            cached = self._cached
            details = self._details()
        if cached is not None:
            return self._dismiss(cached.report, cached.occurrences)
        base = self._build("NOT_SCANNED", self.spec.not_scanned_message, None, None, [], evidence())
        return self._dismiss({**base, "violationDetails": details}, None)

    def scan(self, request: Any = None) -> dict[str, Any]:
        """Run the rules (single-flight ``ActionBusy``) and cache the result."""
        scanned = self.single_flight.run(self.spec.operation, lambda: self._scan_once(request))
        return self._dismiss(scanned.report, scanned.occurrences)

    def violations(
        self,
        rule_id: str | None,
        scan_id: str | None,
        offset: int | None,
        limit: int | None,
        max_results: int = MAX_PAGE_LIMIT,
    ) -> dict[str, Any]:
        """One page of the cached scan's retained violations for ``rule_id``. Never scans."""
        return self._retention.page(scan_id, rule_id, offset, limit, max_results)

    def _dismiss(
        self, report: dict[str, Any], occurrences: dict[str, list[tuple[str, str, str]]] | None
    ) -> dict[str, Any]:
        return apply_dismissals(report, set(self.dismissals.list()), occurrences, self.dismissals.dismissed_pairs())

    def _details(self) -> dict[str, Any]:
        return {**self._retention.details(), "locationNotes": [], "changes": None}  # AdvisorViolationDetailsDto

    def _build(
        self,
        status: str,
        message: str,
        scanned_at: int | None,
        done: Evaluation | None,
        results: Sequence[RuleResult],
        report_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        scope = self._scope(done)
        return build_report(
            self.spec,
            status,
            mask(self._masker, message),
            scanned_at,
            Scope(_mask_tree(self._masker, scope.lists), scope.counts),
            results,
            len(results),
            {**report_evidence, "limitations": _mask_tree(self._masker, report_evidence["limitations"])},
            _mask_tree(self._masker, self._extra(done)),
        )

    def _scan_once(self, request: Any) -> _Scan:
        scanned_at = int(time.time() * 1000)
        done = self._run(request)
        findings = [
            replace(f, target=mask(self._masker, f.target), message=mask(self._masker, f.message))
            for f in done.findings
        ]
        found: dict[str, list[str]] = {rule_id: [] for rule_id in done.evaluated}
        occurrences: dict[str, list[tuple[str, str, str]]] = {}
        for finding in findings:
            found.setdefault(finding.rule_id, []).append(finding.message)
            occurrences.setdefault(finding.rule_id, []).append(
                (finding.fingerprint, finding.message, finding.identity or finding.target)
            )
        results = [
            RuleResult.skipped(rule) if rule.id in done.skipped else RuleResult.evaluate(rule, found[rule.id])
            for rule in self.rules
            if rule.id in found or rule.id in done.skipped
        ]
        result = self._build(done.status, done.message, scanned_at, done, results, done.evidence)
        scan = _Scan(result, occurrences)
        with self._swap:  # build first: a failed build must leave retention and cache as they were
            self._retention.store(found, {rule: [fp for fp, _, _ in pairs] for rule, pairs in occurrences.items()})
            result["violationDetails"] = self._details()
            self._cached = scan
        return scan
