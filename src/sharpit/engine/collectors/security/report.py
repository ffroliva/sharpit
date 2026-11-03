"""``SecurityReport`` (port of BootUI ``SecurityScanner``): the rule registry, one scan's evaluation and the service.

The service is the shared advisor scan core (``engine/advisors/scan.py``): single-flight scans, the cached report,
paging and dismissals live there. Nothing is read before the first explicit scan; a GET renders the cached dict.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope
from sharpit.engine.collectors.security import Inputs, SecurityRule, Violation
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight

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

RULES: tuple[SecurityRule, ...] = ()


def check(rule_id: str, inputs: Inputs) -> list[Violation]:
    """One rule over ``inputs`` (tests and callers that need a single rule); an unknown id finds nothing."""
    found = next((r for r in RULES if r.definition.id == rule_id), None)
    return found.check(inputs) if found is not None else []


def _scope(_done: Evaluation | None) -> Scope:
    return Scope()


def _extra(_done: Evaluation | None) -> Mapping[str, Any]:
    return {}


def scan_evaluation(inputs: Inputs) -> Evaluation:
    return Evaluation("SCANNED", "", (), (), evidence(), inputs)


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
