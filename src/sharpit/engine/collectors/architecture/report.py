"""Architecture advisor report texts and service on the shared scan core."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.rules import RuleResult
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope
from sharpit.engine.collectors.architecture.rules import RULES
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight

ADVISOR = "architecture"
ANALYZER = "BootUI ArchUnit hygiene"
DISCLAIMER = (
    "Heuristic, project-agnostic architecture rules run against the host application's own classes only. These checks "
    "complement, but do not replace, a project-specific ArchUnit test suite or an architecture review."
)
NOT_SCANNED_MESSAGE = (
    "Architecture rules have not run yet. Run architecture checks in the panel, or call architecture_scan (bootui "
    "architecture scan), to analyse the application classes."
)
NO_BASE_PACKAGES_MESSAGE = "No application base package was detected, so there were no classes to analyse."
NO_CLASSES_MESSAGE = "No application classes were found under the detected base package(s) to analyse."

SPEC = ScanSpec(ADVISOR, ANALYZER, DISCLAIMER, NOT_SCANNED_MESSAGE)


def scanned_message(classes: int) -> str:
    return f"Architecture rules completed against {classes} application class(es) under the detected base package(s)."


def incomplete_message(rules: int, classes: int) -> str:
    return (
        f"Architecture analysis is incomplete: {rules} rule(s) could not be evaluated against {classes} application "
        "class(es)."
    )


@dataclass(frozen=True)
class ArchitectureScanDetail:
    classes_analyzed: int = 0
    base_packages: tuple[str, ...] = ()
    analysis_errors: tuple[RuleResult, ...] = ()


def _scope(done: Evaluation | None, base_packages_fn: Callable[[], Sequence[str]]) -> Scope:
    detail: ArchitectureScanDetail | None = done.detail if done else None
    packages = list(detail.base_packages) if detail is not None and detail.base_packages else list(base_packages_fn())
    classes = detail.classes_analyzed if detail is not None else 0
    return Scope({"basePackages": packages}, {"classesAnalyzed": classes})


def _extra(done: Evaluation | None) -> Mapping[str, Any]:
    detail: ArchitectureScanDetail | None = done.detail if done else None
    errors = [r.to_dto() for r in detail.analysis_errors] if detail is not None else []
    return {"analysisErrors": errors}


def _dummy_run(_request: Any) -> Evaluation:
    # Skeleton: returns empty scanned evaluation
    detail = ArchitectureScanDetail(0, (), ())
    return Evaluation(
        status="SCANNED",
        message=NO_CLASSES_MESSAGE,
        evaluated=tuple(r.id for r in RULES),
        findings=(),
        evidence=evidence(usable=False, coverage_complete=True, limitations=[]),
        detail=detail,
    )


class ArchitectureService(AdvisorScan):
    """The Architecture advisor on the shared scan core."""

    def __init__(
        self,
        base_packages: Callable[[], Sequence[str]],
        dismissals: DismissalStore,
        masker: Masker,
        single_flight: SingleFlight,
        *,
        max_retained: int,
        run_scan: Callable[[Any], Evaluation] | None = None,
    ) -> None:
        self.base_packages = base_packages
        runner = run_scan if run_scan is not None else _dummy_run
        super().__init__(
            SPEC,
            RULES,
            runner,
            scope=lambda done: _scope(done, self.base_packages),
            extra_sections=_extra,
            dismissals=dismissals,
            masker=masker,
            single_flight=single_flight,
            max_retained=max_retained,
        )
