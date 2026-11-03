"""``SecurityReport`` (port of BootUI ``SecurityScanner``): the rule registry, one scan's evaluation and the service.

The service is the shared advisor scan core (``engine/advisors/scan.py``): single-flight scans, the cached report,
paging and dismissals live there. Nothing is read before the first explicit scan; a GET renders the cached dict.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from typing import Any

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.rules import RuleDefinition, RuleResult
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope
from sharpit.engine.collectors.security import (
    Inputs,
    SecurityRule,
    Violation,
    rules_auth,
    rules_config,
    rules_source,
    rules_transport,
)
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.spi import SecurityChain

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


def scan_evaluation(inputs: Inputs) -> Evaluation:
    chains = tuple(_matcher(c) for c in inputs.model.chains)
    return Evaluation("SCANNED", "", (), (), evidence(), _Done(chains))


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
