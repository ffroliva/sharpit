"""``FastapiReport`` texts, the rule catalogue and the advisor on the shared scan core (BootUI ``SpringScanner``).

The shape (``inspected``/``componentsAnalyzed`` scope keys, ``analysisErrors``) is built by ``engine/advisors/scan.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope
from sharpit.engine.appsource import SourceIndex
from sharpit.engine.collectors.fastapi_advisor import rules_app, rules_async, rules_models
from sharpit.engine.collectors.fastapi_advisor.handlers import Endpoint, Handler, Hit, index_handlers
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

RULES: tuple[RuleDefinition, ...] = (*rules_async.RULES, *rules_models.RULES, *rules_app.RULES)

SPEC = ScanSpec(ADVISOR, ANALYZER, DISCLAIMER, NOT_SCANNED_MESSAGE)
_BY_ID = {rule.id: rule for rule in RULES}


def _source_checks(handlers: Sequence[Handler], index: SourceIndex) -> dict[str, list[Hit]]:
    return {
        rules_async.SYNC_IO.id: rules_async.sync_io(handlers),
        rules_async.ASYNC_BLOCKING.id: rules_async.async_blocking(handlers),
        rules_async.HTTP_TIMEOUT.id: rules_async.http_timeout(index),
        rules_async.HEAVY_BACKGROUND.id: rules_async.heavy_background(handlers),
        rules_models.PYDANTIC_V1.id: rules_models.pydantic_v1(index),
        rules_models.DICT_RESPONSE.id: rules_models.dict_response(handlers),
        rules_app.ON_EVENT.id: rules_app.on_event(index),
        rules_app.BROAD_EXCEPT.id: rules_app.broad_except(handlers),
    }


def evaluate(
    app: object, endpoints: Sequence[Endpoint], index: SourceIndex | None, limitations: Sequence[str] = ()
) -> Evaluation:
    """One pass of the rules: the app object's own attributes always, source rules when the app's source is indexed."""
    notes = list(limitations)
    hits: dict[str, list[Hit]] = {
        rules_app.DEBUG.id: rules_app.debug(app),
        rules_app.DEFAULT_TITLE.id: rules_app.default_title(app),
    }
    handlers: list[Handler] = []
    if index is not None:
        handlers, skipped = index_handlers(endpoints, index)
        notes += [*index.limitations, *skipped]
        hits.update(_source_checks(handlers, index))
    findings = tuple(
        Finding(rule_id, ADVISOR, _BY_ID[rule_id].severity, target, message)
        for rule_id, found in hits.items()
        for target, message in found
    )
    unevaluated = len(RULES) - len(hits)
    inspected = [
        f"Routes: {len(endpoints)}; handlers analysed: {len(handlers)}; source parsed, never executed.",
        "Configuration is not proof of execution, authorization, or network reachability.",
        f"Unevaluated rules (inapplicable or required evidence unavailable): {unevaluated}.",
        *notes,
    ]
    message = (
        f"FastAPI Advisor completed against {len(handlers)} route handler(s); see unevaluated observations and "
        "analysis errors."
    )
    detail = {"inspected": inspected, "components": len(handlers)}
    return Evaluation("SCANNED", message, tuple(hits), findings, evidence(True, not notes, notes), detail)


def _scope(done: Evaluation | None) -> Scope:
    raw: object = done.detail if done is not None else None
    detail: Mapping[str, Any] = cast("Mapping[str, Any]", raw) if isinstance(raw, Mapping) else {}
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
