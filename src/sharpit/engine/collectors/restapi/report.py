"""``RestApiReport`` (port of BootUI ``RestApiScanner.report``, ``violationResults`` and its messages)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sharpit.engine.advisors.report import evidence, severity_counts
from sharpit.engine.advisors.rules import SEVERITIES, RuleResult, severity_rank

ANALYZER = "sharpit rest-api"
DISCLAIMER = (
    "Heuristic, project-agnostic REST API design rules run against the host application's own route handlers only."
    " These checks complement, but do not replace, an API design review or contract testing. Security concerns"
    " (CORS, authentication, authorization) are out of scope."
)
NOT_SCANNED_MESSAGE = (
    "REST API rules have not run yet. Click Run REST API checks to analyse the application's route handlers."
)
NO_ROUTES_MESSAGE = "No route handlers were found in the host application."


def scanned_message(modules: int, handlers: int) -> str:
    return (
        f"REST API rules completed against {modules} module(s) and {handlers} route handler(s) in the host application."
    )


def incomplete_message(limitations: Sequence[str]) -> str:
    return (
        f"REST API analysis is incomplete: {len(limitations)} part(s) of the application could not be inspected."
        " Reliable findings are retained; missing findings do not establish a clean API."
    )


def failing(results: Iterable[RuleResult]) -> list[RuleResult]:
    """Only the FAILED rules, most severe first, then the most violations, then by id (``violationResults``)."""
    found = [r for r in results if r.status == "FAILED"]
    return sorted(found, key=lambda r: (severity_rank(r.severity), -r.violation_count, r.id))


def build(
    status: str,
    message: str,
    scanned_at: int | None,
    base_packages: Sequence[str],
    modules: int,
    handlers: int,
    rules_evaluated: int,
    results: Sequence[RuleResult],
    report_evidence: dict[str, Any],
    violation_details: dict[str, Any],
) -> dict[str, Any]:
    violations = failing(results)
    return {
        "localOnly": True,
        "disclaimer": DISCLAIMER,
        "basePackages": list(base_packages),
        "controllersAnalyzed": modules,
        "handlersAnalyzed": handlers,
        "rulesEvaluated": rules_evaluated,
        "violationsFound": len(violations),
        "severityCounts": severity_counts(((r.severity, r.violation_count) for r in violations), SEVERITIES),
        "scan": {
            "analyzer": ANALYZER,
            "status": status,
            "message": message,
            "scannedAt": scanned_at,
            "rulesEvaluated": rules_evaluated,
            "controllersAnalyzed": modules,
            "handlersAnalyzed": handlers,
            "violationsFound": len(violations),
        },
        "results": [r.to_dto() for r in violations],
        "evidence": report_evidence,
        "violationDetails": violation_details,
    }


def not_scanned(violation_details: dict[str, Any]) -> dict[str, Any]:
    return build("NOT_SCANNED", NOT_SCANNED_MESSAGE, None, [], 0, 0, 0, [], evidence(), violation_details)
