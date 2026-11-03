"""``FastapiReport`` texts, the rule catalogue and the advisor on the shared scan core (BootUI ``SpringScanner``).

The shape (``inspected``/``componentsAnalyzed`` scope keys, ``analysisErrors``) is built by ``engine/advisors/scan.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight

ADVISOR = "fastapi"
ANALYZER = "sharpit FastAPI Advisor"
DISCLAIMER = (
    "Bounded FastAPI route and source checks are review prompts, not runtime or deployment verdicts. Unknown "
    "observations are unevaluated; validate advice against the application's requirements."
)
NOT_SCANNED_MESSAGE = (
    "FastAPI Advisor has not run yet. Run FastAPI checks in the panel, or call fastapi_scan (sharpit fastapi scan), "
    "to inspect the application."
)

RULES: tuple[RuleDefinition, ...] = ()

SPEC = ScanSpec(ADVISOR, ANALYZER, DISCLAIMER, NOT_SCANNED_MESSAGE)


def _scope(done: Evaluation | None) -> Scope:
    detail: Mapping[str, Any] = done.detail if done is not None and isinstance(done.detail, Mapping) else {}
    return Scope({"inspected": list(detail.get("inspected", []))}, {"componentsAnalyzed": detail.get("components", 0)})


def _extra(_done: Evaluation | None) -> Mapping[str, Any]:
    return {"analysisErrors": []}  # no rule reports ERROR: a rule that cannot see its evidence is skipped


class FastapiAdvisor(AdvisorScan):
    """The FastAPI advisor on the shared scan core; ``run`` evaluates the rules for one scan."""

    def __init__(
        self,
        run: Callable[[Any], Evaluation],
        dismissals: DismissalStore,
        masker: Masker,
        single_flight: SingleFlight,
        *,
        max_retained: int,
    ) -> None:
        super().__init__(
            SPEC,
            RULES,
            run,
            scope=_scope,
            extra_sections=_extra,
            dismissals=dismissals,
            masker=masker,
            single_flight=single_flight,
            max_retained=max_retained,
        )
