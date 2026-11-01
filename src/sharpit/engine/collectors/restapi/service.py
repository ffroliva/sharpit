"""REST API advisor service (port of BootUI ``RestApiScanner.scan``/``lastReport`` and ``RestApiController``).

``report()`` never scans: it renders the last completed scan, or ``NOT_SCANNED``. ``scan()`` is the only way to run the
rules; it runs on its own single-flight lock. ``run()`` is the same scan as an ``AdvisorRun`` (0.3.0 spec §5.5), and
``assess()`` is the pure form of it for callers with no console (the pytest plugin). Violation strings, targets and
limitations are masked before they are kept. The report and the retained details are replaced together, so a report's
``scanId`` always pages its own details. Dismissals (rule ids and finding fingerprints) are re-read and applied on every
render; the cache is never changed by them.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass, replace
from typing import Any

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.findings import AdvisorRun, Finding
from sharpit.engine.advisors.report import apply_dismissals, evidence
from sharpit.engine.advisors.retention import ViolationRetention
from sharpit.engine.advisors.rules import RuleResult, Severity
from sharpit.engine.collectors.restapi import report
from sharpit.engine.collectors.restapi.rules import RULES, application_routes, evaluate
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.spi import ApiModel

OPERATION = "rest-api-scan"
ADVISOR = "rest-api"
DEFAULT_FAIL_ON: Severity = "HIGH"


@dataclass(frozen=True)
class _Evaluation:
    """One pass of the rules over a model: everything masked, nothing dismissed."""

    status: str  # SCANNED | PARTIAL
    routes: int
    modules: list[str]
    limitations: list[str]
    evaluated: tuple[str, ...]  # ids of the rules that ran to completion
    findings: tuple[Finding, ...]
    evidence: dict[str, Any]


def _mask(masker: Masker, text: str) -> str:
    masked = masker.mask_text(text)
    return masked if masked is not None else masker.mask_path(text)  # METADATA_ONLY: paths stay visible


def _evaluate(model: ApiModel, masker: Masker) -> _Evaluation:
    routes = application_routes(model.routes)
    limitations = [_mask(masker, item) for item in model.limitations]
    modules = sorted({r.handler.partition(":")[0] for r in routes})
    findings: list[Finding] = []
    evaluated: list[str] = []
    errored: set[str] = set()
    if routes:  # BootUI: no controllers -> no rule is evaluated
        raw, errored = evaluate(routes, model.exception_handlers)
        for rule in RULES:
            if rule.id in errored:
                continue
            evaluated.append(rule.id)
            findings.extend(
                Finding(rule.id, ADVISOR, rule.severity, _mask(masker, v.target), _mask(masker, v.message))
                for v in raw.get(rule.id, ())
            )
    if errored:  # BootUI: a rule that throws is skipped and the report is PARTIAL
        limitations.append("rule evaluation: required REST API evidence was unavailable.")
    return _Evaluation(
        "PARTIAL" if limitations else "SCANNED",
        len(routes),
        modules,
        limitations,
        tuple(evaluated),
        tuple(findings),
        evidence(bool(routes), not limitations, limitations),  # no routes and no limitation: confirmed empty
    )


def _run(done: _Evaluation, dismissed: Collection[str], fail_on: Severity, app: str | None) -> AdvisorRun:
    findings = tuple(
        replace(f, dismissed=True) if f.rule_id in dismissed or f.fingerprint in dismissed else f for f in done.findings
    )
    return AdvisorRun.of(ADVISOR, findings, done.evidence, scan_status=done.status, fail_on=fail_on, app=app)


def assess(
    model: ApiModel,
    masker: Masker,
    *,
    fail_on: Severity = DEFAULT_FAIL_ON,
    app: str | None = None,
    dismissed: Collection[str] = (),
) -> AdvisorRun:
    """Pure: the REST API rules over ``model`` as an ``AdvisorRun`` (no lock, no cache; used by the pytest plugin)."""
    return _run(_evaluate(model, masker), dismissed, fail_on, app)


@dataclass(frozen=True)
class _Scan:
    report: dict[str, Any]  # as built, before dismissals
    done: _Evaluation
    occurrences: dict[str, list[tuple[str, str]]]  # rule id -> its occurrences' (fingerprint, text), in violation order


class RestApiService:
    def __init__(
        self,
        model: Callable[[], ApiModel],
        dismissals: DismissalStore,
        masker: Masker,
        single_flight: SingleFlight,
        *,
        max_retained: int,
    ) -> None:
        self._model = model
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
            base = cached.report if cached else report.not_scanned(self._retention.details())
        return apply_dismissals(base, set(self.dismissals.list()), cached.occurrences if cached else None)

    def scan(self) -> dict[str, Any]:
        """Run the rules (single-flight ``ActionBusy``) and cache the result."""
        scanned = self.single_flight.run(OPERATION, self._scan)
        return apply_dismissals(scanned.report, set(self.dismissals.list()), scanned.occurrences)

    def run(self) -> AdvisorRun:
        """The cached scan as an ``AdvisorRun`` with the current dismissals applied; scans when there is none."""
        with self._swap:
            cached = self._cached
        if cached is None:
            cached = self.single_flight.run(OPERATION, self._scan)
        return _run(cached.done, set(self.dismissals.list()), DEFAULT_FAIL_ON, None)

    def violations(
        self, rule_id: str | None, scan_id: str | None, offset: int | None, limit: int | None, max_results: int
    ) -> dict[str, Any]:
        """One page of the cached scan's retained violations for ``rule_id``. Never scans."""
        return self._retention.page(scan_id, rule_id, offset, limit, max_results)

    def _scan(self) -> _Scan:
        scanned_at = int(time.time() * 1000)
        done = _evaluate(self._model(), self._masker)
        found: dict[str, list[str]] = {rule_id: [] for rule_id in done.evaluated}
        occurrences: dict[str, list[tuple[str, str]]] = {}
        for finding in done.findings:
            found[finding.rule_id].append(finding.message)
            occurrences.setdefault(finding.rule_id, []).append((finding.fingerprint, finding.message))
        results = [RuleResult.evaluate(rule, found[rule.id]) for rule in RULES if rule.id in found]
        if done.limitations:
            status, message = "PARTIAL", report.incomplete_message(done.limitations)
        elif done.routes:
            status, message = "SCANNED", report.scanned_message(len(done.modules), done.routes)
        else:
            status, message = "SCANNED", report.NO_ROUTES_MESSAGE
        result = report.build(
            status,
            message,
            scanned_at,
            sorted({m.partition(".")[0] for m in done.modules}),
            len(done.modules),
            done.routes,
            len(results),
            results,
            done.evidence,
            {},
        )
        scan = _Scan(result, done, occurrences)
        with self._swap:  # build first: a failed build must leave retention and cache as they were
            self._retention.store(found, {rule: [fp for fp, _ in pairs] for rule, pairs in occurrences.items()})
            result["violationDetails"] = self._retention.details()
            self._cached = scan
        return scan
