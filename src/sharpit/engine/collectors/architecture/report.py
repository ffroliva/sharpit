"""Architecture advisor report texts and service on the shared scan core."""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sharpit.engine import appsource
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.rules import RuleResult
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope
from sharpit.engine.collectors.architecture.contracts import find_pyproject_path, read_contracts
from sharpit.engine.collectors.architecture.graph import build_graph
from sharpit.engine.collectors.architecture.rules import RULES, evaluate_rules
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

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


def scan_application(app: Any, app_package: str | None = None) -> Evaluation:
    """Run architecture checks against the application package resolved through appsource."""
    reasons: list[str] = []
    search_path = list(sys.path)
    pkg_name = app_package
    if app_package:
        p = Path(app_package)
        if p.exists():
            search_path.insert(0, str(p.parent))
            pkg_name = p.stem if p.is_file() else p.name

    root = appsource.resolve_package_root(
        app,
        sys.modules,
        app_package=pkg_name,
        search_path=tuple(search_path),
        reasons=reasons,
    )
    if root is None:
        return Evaluation(
            status="NOT_SCANNED",
            message=reasons[0] if reasons else NO_BASE_PACKAGES_MESSAGE,
            evaluated=(),
            findings=(),
            evidence=evidence(usable=False, coverage_complete=False, limitations=reasons),
            detail=ArchitectureScanDetail(0, (), ()),
        )

    index = appsource.build_index(root)
    if not index.modules:
        base_name = root.stem if root.is_file() else root.name
        return Evaluation(
            status="SCANNED",
            message=NO_CLASSES_MESSAGE,
            evaluated=tuple(r.id for r in RULES),
            findings=(),
            evidence=evidence(usable=True, coverage_complete=not index.truncated, limitations=index.limitations),
            detail=ArchitectureScanDetail(0, (base_name,), ()),
        )

    base_pkg = root.stem if root.is_file() else root.name
    graph = build_graph(index, base_pkg)
    pyproject = find_pyproject_path(root, sys.path)
    contracts, c_limitations = read_contracts(pyproject) if pyproject is not None else ((), ())
    findings_by_rule = evaluate_rules(index, graph, contracts)

    findings: list[Finding] = [f for flist in findings_by_rule.values() for f in flist]

    limitations = [*index.limitations, *c_limitations]
    classes = len(graph.nodes)
    status = "PARTIAL" if index.truncated else "SCANNED"
    message = scanned_message(classes)
    ev = evidence(usable=True, coverage_complete=not index.truncated, limitations=limitations)
    detail = ArchitectureScanDetail(classes_analyzed=classes, base_packages=(base_pkg,), analysis_errors=())

    return Evaluation(
        status=status,
        message=message,
        evaluated=tuple(r.id for r in RULES),
        findings=tuple(findings),
        evidence=ev,
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
        runner: Callable[[Any], Evaluation] = run_scan if run_scan is not None else (lambda req: scan_application(req))
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


def architecture_service(ctx: SharpitContext, host_app: Any = None) -> ArchitectureService:
    """The per-install Architecture advisor service, memoised on the context."""
    app = host_app if host_app is not None else getattr(ctx.introspector, "app", None)

    def default_base_packages() -> Sequence[str]:
        if ctx.settings.app_package:
            p = Path(ctx.settings.app_package)
            return (p.stem if p.exists() and p.is_file() else (p.name if p.exists() else ctx.settings.app_package),)
        reasons: list[str] = []
        root = appsource.resolve_package_root(app, sys.modules, reasons=reasons)
        if root is not None:
            return (root.stem if root.is_file() else root.name,)
        return ()

    return ctx.lazy(
        "architecture",
        lambda: ArchitectureService(
            default_base_packages,
            ctx.lazy("dismissals", lambda: DismissalStore(Path(ctx.settings.state_dir))),
            ctx.masker,
            ctx.lazy("singleflight:architecture-scan", SingleFlight),
            max_retained=ctx.settings.advisors_max_retained_violations,
            run_scan=lambda req: scan_application(req if req is not None else app, ctx.settings.app_package),
        ),
    )
