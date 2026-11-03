"""REST API advisor service (port of BootUI ``RestApiScanner.scan``/``lastReport`` and ``RestApiController``).

``RestApiService`` is the shared advisor scan core (``engine/advisors/scan.py``) over the REST API rules: single-flight
scans, the cached report, paging and dismissals live there. ``assess()`` is the same evaluation as an ``AdvisorRun``
(0.3.0 spec §5.5), pure, for callers with no console (the pytest plugin). Violation strings, targets and limitations
are masked before they are kept.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, replace
from typing import Any

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.findings import AdvisorRun, Finding
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.rules import Severity
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope, mask
from sharpit.engine.collectors.restapi import report
from sharpit.engine.collectors.restapi.rules import RULES, application_routes, evaluate
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.spi import ApiModel

ADVISOR = "rest-api"
OPERATION = f"{ADVISOR}-scan"
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


def _evaluate(model: ApiModel, masker: Masker) -> _Evaluation:
    routes = application_routes(model.routes)
    limitations = [mask(masker, item) for item in model.limitations]
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
                Finding(rule.id, ADVISOR, rule.severity, mask(masker, v.target), mask(masker, v.message))
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


def _run(
    done: _Evaluation,
    dismissed: Collection[str],
    fail_on: Severity,
    app: str | None,
    dismissed_pairs: Collection[tuple[str, str]] = (),
    baseline: Mapping[str, int | None] | None = None,
) -> AdvisorRun:
    findings = tuple(
        replace(f, dismissed=True)
        if f.rule_id in dismissed
        or f.fingerprint in dismissed
        or (f.rule_id, f.identity or f.target) in dismissed_pairs
        else f
        for f in done.findings
    )
    if baseline is not None:
        findings = tuple(
            replace(
                finding,
                baseline_state=(
                    "existing"
                    if finding.fingerprint in baseline
                    and (baseline[finding.fingerprint] is None or finding.observed is None)
                    else "existing"
                    if finding.fingerprint in baseline
                    else "new"
                ),
            )
            for finding in findings
        )
    return AdvisorRun.of(ADVISOR, findings, done.evidence, scan_status=done.status, fail_on=fail_on, app=app)


def assess(
    model: ApiModel,
    masker: Masker,
    *,
    fail_on: Severity = DEFAULT_FAIL_ON,
    app: str | None = None,
    dismissed: Collection[str] = (),
    dismissed_pairs: Collection[tuple[str, str]] = (),
    baseline: Mapping[str, int | None] | None = None,
) -> AdvisorRun:
    """Pure: the REST API rules over ``model`` as an ``AdvisorRun`` (no lock, no cache; used by the pytest plugin)."""
    return _run(_evaluate(model, masker), dismissed, fail_on, app, dismissed_pairs, baseline)


def _scope(done: Evaluation | None) -> Scope:
    rest: _Evaluation | None = done.detail if done else None
    modules = rest.modules if rest else []
    return Scope(
        {"basePackages": sorted({m.partition(".")[0] for m in modules})},
        {"controllersAnalyzed": len(modules), "handlersAnalyzed": rest.routes if rest else 0},
    )


def _scan_evaluation(model: ApiModel, masker: Masker) -> Evaluation:
    done = _evaluate(model, masker)
    if done.limitations:
        message = report.incomplete_message(done.limitations)
    elif done.routes:
        message = report.scanned_message(len(done.modules), done.routes)
    else:
        message = report.NO_ROUTES_MESSAGE
    return Evaluation(done.status, message, done.evaluated, done.findings, done.evidence, done)


SPEC = ScanSpec(ADVISOR, report.ANALYZER, report.DISCLAIMER, report.NOT_SCANNED_MESSAGE)


class RestApiService(AdvisorScan):
    """The REST API advisor on the shared scan core."""

    def __init__(
        self,
        model: Callable[[], ApiModel],
        dismissals: DismissalStore,
        masker: Masker,
        single_flight: SingleFlight,
        *,
        max_retained: int,
    ) -> None:
        super().__init__(
            SPEC,
            RULES,
            lambda _request: _scan_evaluation(model(), masker),
            scope=_scope,
            dismissals=dismissals,
            masker=masker,
            single_flight=single_flight,
            max_retained=max_retained,
        )
