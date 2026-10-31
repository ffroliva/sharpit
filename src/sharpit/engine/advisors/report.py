"""Advisor report helpers (port of BootUI ``SeverityOrder.occurrenceCounts``, ``RestApiScanner.applyDismissals`` and
the ``AdvisorEvidenceDto`` constructor)."""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Any

from sharpit.engine.advisors.rules import SEVERITIES

UNKNOWN_EVIDENCE = "Assessment evidence is unavailable."
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")  # Java \p{Cntrl}
_MAX_LIMITATION = 240
_MAX_LIMITATIONS = 20


def severity_counts(results: Iterable[tuple[str, int]], severities: Sequence[str]) -> list[dict[str, Any]]:
    """One ``{severity, count}`` per given severity, zeros included; ``results`` are ``(severity, occurrences)`` pairs
    and a severity outside ``severities`` is skipped."""
    counts = dict.fromkeys(severities, 0)
    for severity, occurrences in results:
        if severity in counts:
            counts[severity] += occurrences
    return [{"severity": s, "count": c} for s, c in counts.items()]


def apply_dismissals(report: Mapping[str, Any], dismissed: Collection[str]) -> dict[str, Any]:
    """A copy of ``report`` with each result's ``dismissed`` set and ``violationsFound``, ``severityCounts`` and
    ``scan.violationsFound`` recomputed from the active failing rules. The input is never mutated."""
    marked: list[dict[str, Any]] = [{**r, "dismissed": r["id"] in dismissed} for r in report["results"]]
    active = [r for r in marked if not r["dismissed"] and r["status"] == "FAILED"]
    return {
        **report,
        "violationsFound": len(active),
        "severityCounts": severity_counts(((r["severity"], r["violationCount"]) for r in active), SEVERITIES),
        "scan": {**report["scan"], "violationsFound": len(active)},
        "results": marked,
    }


def sanitize_limitations(items: Iterable[str | None] | None) -> list[str]:
    """Control characters to spaces, stripped, blanks dropped, each ≤ 240 chars, distinct, at most 20."""
    out: list[str] = []
    for item in items or ():
        if item is None:
            continue
        value = _CONTROL.sub(" ", item).strip()[:_MAX_LIMITATION]
        if value and value not in out:
            out.append(value)
            if len(out) == _MAX_LIMITATIONS:
                break
    return out


def evidence(
    usable: bool = False, coverage_complete: bool = False, limitations: Iterable[str] | None = None
) -> dict[str, Any]:
    """``AdvisorEvidenceDto``; no arguments gives ``AdvisorEvidenceDto.unknown()``."""
    if limitations is None and not usable and not coverage_complete:
        limitations = [UNKNOWN_EVIDENCE]
    return {"usable": usable, "coverageComplete": coverage_complete, "limitations": sanitize_limitations(limitations)}
