"""Framework-free assembly of the final pytest session report."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sharpit.engine.testsession import outcome, report
from sharpit.engine.testsession.facts import SessionFacts


@dataclass(frozen=True)
class GateOptions:
    max_queries: int | None
    activity_n_plus_one_threshold: int
    fail_on: str
    allow_unknown: bool
    max_unattributed: float
    advisors_enabled: bool


def finish(
    parts: Sequence[SessionFacts],
    missing: Sequence[str],
    *,
    options: GateOptions,
    version: str,
    now_ms: int,
    warnings: Sequence[str],
) -> tuple[dict[str, Any], str, list[str]]:
    """Merge run facts and render the report without depending on pytest or adapter state."""
    merged = outcome.merge(parts, missing)
    for warning in warnings:
        if warning not in merged.warnings:
            merged.warnings.append(warning)
    if any(warning.startswith("a sharpit session hook failed (") for warning in warnings) and not any(
        source["name"] == "pytest-plugin" for source in merged.sources
    ):
        warning = next(w for w in warnings if w.startswith("a sharpit session hook failed ("))
        merged.sources.append({"name": "pytest-plugin", "attached": False, "reason": warning, "limitations": []})
    status, reasons = outcome.session_status(
        merged,
        allow_unknown=options.allow_unknown,
        max_unattributed=options.max_unattributed,
        advisors_enabled=options.advisors_enabled,
        fail_on=options.fail_on,
    )
    data = report.render(
        merged,
        status,
        reasons,
        gates={
            "maxQueriesPerTest": options.max_queries,
            "nPlusOneThreshold": options.activity_n_plus_one_threshold,
            "failOnSeverity": options.fail_on,
            "allowUnknown": options.allow_unknown,
            "maxUnattributedPercent": options.max_unattributed,
        },
        version=version,
        now_ms=now_ms,
        advisors_enabled=options.advisors_enabled,
    )
    return data, status, reasons
