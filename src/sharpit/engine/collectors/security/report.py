"""``SecurityReport`` (port of BootUI ``SecurityScanner``): the rule registry, one scan's evaluation and the service.

The service is the shared advisor scan core (``engine/advisors/scan.py``): single-flight scans, the cached report,
paging and dismissals live there. Nothing is read before the first explicit scan; a GET renders the cached dict.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from typing import Any

from sharpit.engine import appsource
from sharpit.engine.activation import active_profiles
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.rules import RuleDefinition, RuleResult
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope
from sharpit.engine.collectors.security import (
    ADVISOR,
    Inputs,
    SecurityRule,
    View,
    Violation,
    rules_auth,
    rules_config,
    rules_source,
    rules_transport,
)
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.spi import SecurityChain, SecurityFacts, SecurityModel
from sharpit.settings import SharpitSettings

ANALYZER = "sharpit FastAPI Security Advisor"
DISCLAIMER = (
    "Heuristic FastAPI security rules run against the host application's middleware stacks, security dependencies"
    " and source only. These checks are review prompts, not verdicts, and should be validated against the"
    " application's threat model."
)
NOT_SCANNED_MESSAGE = (
    "Security Advisor has not run yet. Run security checks in the panel, or call security_scan (sharpit security"
    " scan), to inspect the middleware stacks."
)

DISABLED_MESSAGE = "No FastAPI application was found to inspect."
PARTIAL_TAIL = " Unsupported or incomplete evidence remains unknown; skipped checks are not security passes."
FRAMEWORK_LOGGERS = ("fastapi", "starlette", "uvicorn", "sqlalchemy.engine")

RULES: tuple[SecurityRule, ...] = (*rules_source.RULES, *rules_auth.RULES, *rules_transport.RULES, *rules_config.RULES)


def check(rule_id: str, inputs: Inputs) -> list[Violation]:
    """One rule over ``inputs`` (tests and callers that need a single rule); an unknown id finds nothing."""
    found = next((r for r in RULES if r.definition.id == rule_id), None)
    return found.check(inputs) if found is not None else []


@dataclass(frozen=True)
class _Done:
    """What the scope and extra-section hooks read from one scan."""

    chains: tuple[str, ...]  # each middleware stack's matcher description
    errors: tuple[RuleDefinition, ...] = ()  # rules whose evaluation raised


def _matcher(chain: SecurityChain) -> str:
    return "any request" if chain.prefix is None else f"{chain.prefix}/**"


def _scope(done: Evaluation | None) -> Scope:
    chains: tuple[str, ...] = done.detail.chains if done is not None and isinstance(done.detail, _Done) else ()
    return Scope({"filterChains": list(chains)}, {"filterChainsAnalyzed": len(chains)})


def _error_result(definition: RuleDefinition) -> dict[str, Any]:
    values = {f.name: getattr(definition, f.name) for f in fields(RuleDefinition)}
    return RuleResult(**values, status="ERROR").to_dto()


def _extra(done: Evaluation | None) -> Mapping[str, Any]:
    errors = done.detail.errors if done is not None and isinstance(done.detail, _Done) else ()
    return {"analysisErrors": [_error_result(d) for d in sorted(errors, key=lambda d: d.id)]}


def _limitations(inputs: Inputs) -> list[str]:
    found = [*inputs.model.limitations, *inputs.facts.limitations]
    source = [*inputs.limitations, *(inputs.source.limitations if inputs.source is not None else ())]
    if inputs.source is None and not source:
        source = ["not read"]
    return found + [f"application source: {item}" for item in source]


def _message(chains: int, limitations: list[str]) -> str:
    message = f"Security Advisor completed against {chains} middleware stack" + ("." if chains == 1 else "s.")
    if limitations:
        message += " Some configuration remains unobserved: " + "; ".join(limitations) + "." + PARTIAL_TAIL
    return message


def scan_evaluation(inputs: Inputs) -> Evaluation:
    """Every rule over one scan's inputs (BootUI ``SecurityScanner.scan``): a rule that raises is an analysis error."""
    model = inputs.model
    if not model.present:
        limitations = list(model.limitations) or None
        return Evaluation("DISABLED", DISABLED_MESSAGE, (), (), evidence(limitations=limitations), _Done(()))
    limitations = _limitations(inputs)
    evaluated: list[str] = []
    findings: list[Finding] = []
    errors: list[RuleDefinition] = []
    for rule in RULES:
        definition = rule.definition
        if rule.needs_source and inputs.source is None:
            continue  # unknown, never a pass: the limitation says why
        try:
            found = rule.check(inputs)
        except Exception:  # noqa: BLE001 - one rule's failure is an analysis error; never a failed scan
            errors.append(definition)
            continue
        evaluated.append(definition.id)
        findings.extend(
            Finding(definition.id, ADVISOR, definition.severity, v.target, v.message, identity=v.identity)
            for v in found
        )
    if errors:
        limitations.append(f"{len(errors)} rule(s) could not be evaluated.")
    status = "PARTIAL" if limitations else "SCANNED"
    chains = tuple(_matcher(c) for c in model.chains)
    report_evidence = evidence(True, not limitations, limitations)
    message = _message(len(chains), limitations)
    return Evaluation(status, message, tuple(evaluated), tuple(findings), report_evidence, _Done(chains, tuple(errors)))


def view_of(settings: SharpitSettings, environ: Mapping[str, str]) -> View:
    """The settings and process state the rules read (active profiles, framework logger levels); nothing is set."""
    production = any(p in settings.disabled_profiles for p in active_profiles(settings, environ))
    loggers = logging.Logger.manager.loggerDict  # read: getLogger() would create a missing logger
    debug = tuple(
        name
        for name in FRAMEWORK_LOGGERS
        if isinstance(logger := loggers.get(name), logging.Logger) and logging.NOTSET < logger.level <= logging.DEBUG
    )
    return View(production, debug)


def build_inputs(
    model: SecurityModel,
    facts: SecurityFacts,
    app: object,
    settings: SharpitSettings,
    environ: Mapping[str, str] = os.environ,
) -> Inputs:
    """One scan's inputs: the app source through the one package-root resolver (``engine/appsource.py``)."""
    reasons: list[str] = []
    root = appsource.resolve_package_root(app, sys.modules, app_package=settings.app_package, reasons=reasons)
    if root is not None and root.name == "__init__.py":  # a package module seen without ``__path__``: its directory
        root = root.parent
    index = appsource.build_index(root) if root is not None else None  # dropped with the inputs after the scan
    return Inputs(model, facts, index, view_of(settings, environ), tuple(reasons))


SPEC = ScanSpec("security", ANALYZER, DISCLAIMER, NOT_SCANNED_MESSAGE)


class SecurityService(AdvisorScan):
    """The security advisor on the shared scan core; ``inputs`` is read on each explicit scan only."""

    def __init__(
        self,
        inputs: Callable[[], Inputs],
        dismissals: DismissalStore,
        masker: Masker,
        single_flight: SingleFlight,
        *,
        max_retained: int,
    ) -> None:
        super().__init__(
            SPEC,
            [r.definition for r in RULES],
            lambda _request: scan_evaluation(inputs()),
            scope=_scope,
            extra_sections=_extra,
            dismissals=dismissals,
            masker=masker,
            single_flight=single_flight,
            max_retained=max_retained,
        )
