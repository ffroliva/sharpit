from __future__ import annotations

from typing import TYPE_CHECKING

from sharpit.engine.collectors.database_advisor.report import DatabaseAdvisorService
from sharpit.engine.tools import dismissal_store

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext


def database_advisor_service(ctx: SharpitContext) -> DatabaseAdvisorService:
    return ctx.lazy(
        "database-advisor",
        lambda: DatabaseAdvisorService(
            dismissal_store(ctx), ctx.masker, max_retained=ctx.settings.advisors_max_retained_violations
        ),
    )


TOOLS = ()
COMMANDS = {}
