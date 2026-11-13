"""Runtime Insights (W5c): I2 adds the report, one observation and the resource-profile floor.

Every GET runs under ``no_side_effects`` in the shared sweeps; the two POSTs are the panel's only actions and the
matrix proves the read-only refusal for both. The floor starts nothing (``test_insights_profile.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.service import InsightsService

PANEL = "runtime-insights"
GET_ROWS = [
    "/sharpit/api/runtime-insights",
    "/sharpit/api/runtime-insights/insights/{observation_id}",
    "/sharpit/api/runtime-insights/resource-profile",
]
WRITE_ROWS = [
    ("POST", "/sharpit/api/runtime-insights/resource-profile"),
    ("POST", "/sharpit/api/runtime-insights/resource-profile/stop"),
]
PATH_PARAMS = {"observation_id": "uncounted-work:0000000000"}


@dataclass(frozen=True)
class _Kind:
    kind: str = "uncounted-work"
    title: str = "Uncounted work"
    minimum_tier: str = "REQUEST_ID"
    reads: frozenset[str] = frozenset({"ai"})
    optional_reads: frozenset[str] = frozenset()
    evaluate: object = field(
        default=lambda _snapshot: Evaluation(
            1, [Finding("GET /x", "GET /x", True, "ran", 1, 1, ["Check."], ["r-1"], ["site"], [["a.py:1"]], [])]
        )
    )


def _seed_args(ctx: Any) -> dict[str, Any]:
    """A bare sweep app has no kind that finds anything: seed one so the tool is given a real observation id."""
    ctx.capture.journal = ctx.capture.journal or RuntimeJournal(sources=("ai",))
    ctx.capture.journal.offer({"source": "ai", "operation": "chat", "inputTokens": 1, "outputTokens": 1})
    service = ctx.lazy("runtime-insights", lambda: InsightsService(ctx.capture.journal, [_Kind()]))
    return {"id": service.report()["observations"][0]["id"]}


def _observation_args(handle: Any) -> dict[str, Any]:
    return _seed_args(handle.context)


TOOL_ARGS = {"get_runtime_insight": _observation_args}
TOOL_SEEDS = {"get_runtime_insight": _seed_args}
