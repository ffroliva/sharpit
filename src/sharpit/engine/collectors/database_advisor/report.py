"""The database advisor's report (port of BootUI ``DatabaseAdvisorScanner``, 2.2.0) on F5a's advisor scan core."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope
from sharpit.engine.collectors.database_advisor import RULES
from sharpit.engine.singleflight import SingleFlight

if TYPE_CHECKING:
    from sharpit.engine.advisors.dismissals import DismissalStore
    from sharpit.engine.context import SharpitContext
    from sharpit.engine.masking import Masker

ADVISOR = "database-advisor"
OPERATION = f"{ADVISOR}-scan"
SPEC = ScanSpec(ADVISOR, "", "", "")


class DatabaseAdvisorService(AdvisorScan):
    def __init__(self, dismissals: DismissalStore, masker: Masker, *, max_retained: int) -> None:
        super().__init__(
            SPEC,
            [r.definition for r in RULES],
            lambda _request: Evaluation("ERROR", "", (), (), evidence()),
            scope=lambda _done: Scope(),
            dismissals=dismissals,
            masker=masker,
            single_flight=SingleFlight(),
            max_retained=max_retained,
        )


async def run_scan(ctx: SharpitContext, service: DatabaseAdvisorService) -> dict[str, Any]:
    return {}
