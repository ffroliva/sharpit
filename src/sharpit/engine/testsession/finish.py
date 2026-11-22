"""Framework-free assembly of the final pytest session report."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from sharpit.engine.advisors import http_security
from sharpit.engine.advisors.http_security import HeaderExpectation, StatusExpectation
from sharpit.engine.testsession import outcome, report
from sharpit.engine.testsession.facts import SessionFacts
from sharpit.engine.testsession.sink import report_masker


@dataclass(frozen=True)
class GateOptions:
    max_queries: int | None
    activity_n_plus_one_threshold: int
    fail_on: str
    allow_unknown: bool
    max_unattributed: float
    advisors_enabled: bool
    report_only: bool = False
    http_headers: tuple[HeaderExpectation, ...] = ()
    http_statuses: tuple[StatusExpectation, ...] = ()
    partial_run: bool = False
    baseline: frozenset[str] | None = None  # fingerprints of the baseline in use; None: no baseline


def _add_http_security(
    merged: outcome.MergedFacts, parts: Sequence[SessionFacts], missing: Sequence[str], options: GateOptions
) -> None:
    """Evaluate the configured HTTP expectations once, over every worker's merged facts (never per worker)."""
    if not options.advisors_enabled:
        return
    run = http_security.evaluate(
        options.http_headers,
        options.http_statuses,
        merged.tests,
        unassociated=[part.http_unassociated for part in parts],
        partial_run=options.partial_run,
        missing_workers=missing,
        fail_on=options.fail_on,
        baseline=options.baseline,
    )
    if run is None:
        return
    masker = report_masker()  # a configured route is text the host wrote: it is masked like any report string
    run = replace(
        run,
        findings=tuple(
            replace(f, target=masker.mask_text(f.target) or "", message=masker.mask_text(f.message) or "")
            for f in run.findings
        ),
    )
    merged.advisor_runs.append(run)
    known = {finding["fingerprint"] for finding in merged.findings}
    merged.findings.extend(f.to_dto() for f in run.findings if f.fingerprint not in known)


def finish(
    parts: Sequence[SessionFacts],
    missing: Sequence[str],
    *,
    options: GateOptions,
    version: str,
    now_ms: int,
    warnings: Sequence[str],
) -> tuple[dict[str, Any], str, list[str]]:
    """Merge run facts and render the report without depending on pytest or adapter state."""
    merged = outcome.merge(parts, missing, fail_on=options.fail_on)
    _add_http_security(merged, parts, missing, options)
    for warning in warnings:
        if warning not in merged.warnings:
            merged.warnings.append(warning)
    if any(warning.startswith("a sharpit session hook failed (") for warning in warnings) and not any(
        source["name"] == "pytest-plugin" for source in merged.sources
    ):
        warning = next(w for w in warnings if w.startswith("a sharpit session hook failed ("))
        merged.sources.append({"name": "pytest-plugin", "attached": False, "reason": warning, "limitations": []})
    session = outcome.session_status(
        merged,
        allow_unknown=options.allow_unknown,
        max_unattributed=options.max_unattributed,
        advisors_enabled=options.advisors_enabled,
        fail_on=options.fail_on,
    )
    status = session.status
    reasons = session.fail_reasons or session.unknown_reasons
    data = report.render(
        merged,
        status,
        reasons,
        gates={
            "maxQueriesPerTest": options.max_queries,
            "nPlusOneThreshold": options.activity_n_plus_one_threshold,
            "failOnSeverity": options.fail_on,
            "allowUnknown": options.allow_unknown,
            "maxUnattributedPercent": options.max_unattributed,
        },
        version=version,
        now_ms=now_ms,
        advisors_enabled=options.advisors_enabled,
        mode="report-only" if options.report_only else "gate",
        unknown_reasons=session.unknown_reasons,
    )
    return data, status, reasons
