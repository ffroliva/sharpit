"""REST API advisor service (port of BootUI ``RestApiScanner.scan``/``lastReport`` and ``RestApiController``).

``report()`` never scans: it renders the last completed scan, or ``NOT_SCANNED``. ``scan()`` is the only way to run the
rules; it runs on its own single-flight lock. Violation strings and limitations are masked before they are kept. The
report and the retained details are replaced together, so a report's ``scanId`` always pages its own details.
Dismissals are re-read and applied on every render; the cache is never changed by them.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.report import apply_dismissals, evidence
from sharpit.engine.advisors.retention import AdvisorViolationError, ViolationRetention
from sharpit.engine.advisors.rules import RuleResult
from sharpit.engine.collectors.restapi import report
from sharpit.engine.collectors.restapi.rules import RULE_IDS, RULES, application_routes, violations
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.spi import ApiModel

OPERATION = "rest-api-scan"


class RestApiService:
    def __init__(
        self,
        model: Callable[[], ApiModel],
        dismissals: DismissalStore,
        masker: Masker,
        single_flight: SingleFlight,
        *,
        max_retained: int,
    ) -> None:
        self._model = model
        self.dismissals = dismissals
        self._masker = masker
        self.single_flight = single_flight
        self._retention = ViolationRetention(max_retained)
        self._cached: dict[str, Any] | None = None

    def report(self) -> dict[str, Any]:
        """The last completed scan, else ``NOT_SCANNED``; dismissals applied. Never scans."""
        cached = self._cached
        if cached is None:
            cached = report.not_scanned(self._retention.details())
        return apply_dismissals(cached, set(self.dismissals.list()))

    def scan(self) -> dict[str, Any]:
        """Run the rules (single-flight ``ActionBusy``) and cache the result."""
        result = self.single_flight.run(OPERATION, self._scan)
        return apply_dismissals(result, set(self.dismissals.list()))

    def violations(
        self, rule_id: str | None, scan_id: str | None, offset: int | None, limit: int | None, max_results: int
    ) -> dict[str, Any]:
        """One page of the cached scan's retained violations for ``rule_id``. Never scans."""
        if rule_id and rule_id.strip() and rule_id not in RULE_IDS:
            raise AdvisorViolationError(400, f"Unknown REST API rule id: {rule_id}")
        return self._retention.page(scan_id, rule_id, offset, limit, max_results)

    def _mask(self, text: str) -> str:
        masked = self._masker.mask_text(text)
        return masked if masked is not None else self._masker.mask_path(text)  # METADATA_ONLY: paths stay visible

    def _scan(self) -> dict[str, Any]:
        model = self._model()
        scanned_at = int(time.time() * 1000)
        routes = application_routes(model.routes)
        limitations = [self._mask(item) for item in model.limitations]
        modules = sorted({r.handler.partition(":")[0] for r in routes})
        found: dict[str, list[str]] = {}
        if routes:  # BootUI: no controllers -> no rule is evaluated
            raw = violations(routes, model.exception_handlers)
            found = {rule_id: [self._mask(v) for v in items] for rule_id, items in raw.items()}
        results = [RuleResult.evaluate(rule, found[rule.id]) for rule in RULES] if routes else []
        self._retention.store(found)
        if limitations:
            status, message = "PARTIAL", report.incomplete_message(limitations)
        elif routes:
            status, message = "SCANNED", report.scanned_message(len(modules), len(routes))
        else:
            status, message = "SCANNED", report.NO_ROUTES_MESSAGE
        result = report.build(
            status,
            message,
            scanned_at,
            sorted({m.partition(".")[0] for m in modules}),
            len(modules),
            len(routes),
            len(results),
            results,
            evidence(bool(routes), bool(routes) and not limitations, limitations),
            self._retention.details(),
        )
        self._cached = result
        return result
