"""Which findings the default list shows (BootUI ``ExternalValidation`` and ``DefaultListing``).

BootUI's per-kind gate outcomes are copied verbatim (``ExternalValidation.java:80-142``). sharpit has run no validation
of its own: the copy is parity, not a claim. The outcome is never shown; only whether a row is listed and its reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sharpit.engine.collectors.insights.finding import Finding


class Outcome(Enum):
    PASSED = "passed"  # listed
    NOT_VALIDATED = "not-validated"  # silent or never exercised: listed
    FAILED = "failed"  # folded into the panel that shows the same evidence
    UNDER_SAMPLED = "under-sampled"
    NOT_LISTED = "not-listed"  # not listed by design
    NOT_JUDGED = "not-judged"  # added after the gate: rows of its own panel

    @property
    def listed(self) -> bool:
        return self in {Outcome.PASSED, Outcome.NOT_VALIDATED}


@dataclass(frozen=True)
class Entry:
    kind: str
    outcome: Outcome
    unlisted_reason: str | None


MEMORY = "Garbage collection and heap rows are reached from the Memory panel rather than listed by default."
ON_REQUEST = "Its rows appear when all rows are shown, or when a search or a query names this check or its route."
OWN_PANEL = "Its rows are shown in their own panel rather than listed by default."
_FOLDED = {
    "route-time-breakdown": "A request's Why this route is slow, in Live Activity, shows its route's breakdown.",
    "exception-hotspots": "The Exceptions panel lists the same exceptions and links here.",
    "connections-per-request": "The Database connection pools panel shows the pools and links here.",
    "ai-usage-by-route": "The AI panel lists the same calls with their tokens and links here.",
}
_OUTCOMES = {  # ExternalValidation.build, in its order
    "route-time-breakdown": Outcome.FAILED, "repeated-selects": Outcome.UNDER_SAMPLED,
    "lazy-sql-after-handler": Outcome.UNDER_SAMPLED, "exception-hotspots": Outcome.FAILED,
    "errors-behind-2xx": Outcome.PASSED, "connections-per-request": Outcome.FAILED,
    "safe-method-dml": Outcome.NOT_VALIDATED, "transaction-across-remote-call": Outcome.NOT_VALIDATED,
    "split-transaction-writes": Outcome.UNDER_SAMPLED, "unbatched-write-loop": Outcome.UNDER_SAMPLED,
    "after-commit-writes": Outcome.NOT_VALIDATED, "transactional-listener-skipped": Outcome.NOT_VALIDATED,
    "proxy-bypass": Outcome.NOT_VALIDATED, "framework-warnings-by-route": Outcome.UNDER_SAMPLED,
    "event-loop-blocking": Outcome.NOT_VALIDATED, "ai-usage-by-route": Outcome.FAILED,
    "anonymous-data-reach": Outcome.UNDER_SAMPLED, "anonymous-success-on-restricted-route": Outcome.NOT_VALIDATED,
    "orm-auto-flush": Outcome.NOT_VALIDATED, "large-persistence-context": Outcome.NOT_VALIDATED,
    "slow-flush": Outcome.NOT_JUDGED, "connection-reacquisition": Outcome.NOT_JUDGED,
    "readonly-candidate-transaction": Outcome.UNDER_SAMPLED, "paged-without-order": Outcome.UNDER_SAMPLED,
    "gc-inflated-latency": Outcome.NOT_LISTED, "heap-growth-after-gc": Outcome.NOT_LISTED,
    "work-after-response": Outcome.NOT_VALIDATED, "changed-code-not-executed": Outcome.PASSED,
    **dict.fromkeys(  # M5's observations: Side Effects, Code Paths and Code Inventory rows until they pass the gate
        (
            "exceptions-caught-in-code", "hidden-outbound-calls", "thread-local-left-set", "resource-not-closed",
            "threads-per-request", "request-input-in-sink",
        ),
        Outcome.NOT_JUDGED,
    ),
}  # fmt: skip
_ON_REQUEST_KINDS = {"slow-flush", "connection-reacquisition"}  # NOT_JUDGED, yet ON_REQUEST in ExternalValidation
_REASONS = {Outcome.UNDER_SAMPLED: ON_REQUEST, Outcome.NOT_JUDGED: OWN_PANEL, Outcome.NOT_LISTED: MEMORY}


def _entry(kind: str, outcome: Outcome) -> Entry:
    if outcome.listed:
        return Entry(kind, outcome, None)
    reason = ON_REQUEST if kind in _ON_REQUEST_KINDS else _FOLDED.get(kind) or _REASONS[outcome]
    return Entry(kind, outcome, reason)


KINDS: dict[str, Entry] = {kind: _entry(kind, outcome) for kind, outcome in _OUTCOMES.items()}


def of(kind: str) -> Entry:
    """``kind``'s entry; a kind this registry does not name was added after the gate and is not judged."""
    return KINDS.get(kind) or Entry(kind, Outcome.NOT_JUDGED, OWN_PANEL)


def apply(kind: str, finding: Finding) -> Finding:
    """``finding`` of ``kind``; when the kind's gate says unlisted, its reason replaces the row's own."""
    entry = of(kind)
    return finding if entry.outcome.listed else finding.unlisted_whole(entry.unlisted_reason)
