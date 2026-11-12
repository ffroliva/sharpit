"""Runtime Insights I1: each kind's default-listing outcome, copied from BootUI's ``ExternalValidation``."""

from __future__ import annotations

from sharpit.engine.collectors.insights import listing
from sharpit.engine.collectors.insights.finding import Finding
from sharpit.engine.collectors.insights.listing import Outcome
from sharpit.engine.collectors.insights.registry import KINDS

REPORTED = {
    "route-time-breakdown": "FAILED", "repeated-selects": "UNDER_SAMPLED", "lazy-sql-after-handler": "UNDER_SAMPLED",
    "exception-hotspots": "FAILED", "errors-behind-2xx": "PASSED", "connections-per-request": "FAILED",
    "safe-method-dml": "NOT_VALIDATED", "transaction-across-remote-call": "NOT_VALIDATED",
    "split-transaction-writes": "UNDER_SAMPLED", "after-commit-writes": "NOT_VALIDATED",
    "transactional-listener-skipped": "NOT_VALIDATED", "proxy-bypass": "NOT_VALIDATED",
    "framework-warnings-by-route": "UNDER_SAMPLED", "event-loop-blocking": "NOT_VALIDATED",
    "ai-usage-by-route": "FAILED", "anonymous-data-reach": "UNDER_SAMPLED",
    "anonymous-success-on-restricted-route": "NOT_VALIDATED", "orm-auto-flush": "NOT_VALIDATED",
    "large-persistence-context": "NOT_VALIDATED", "slow-flush": "NOT_JUDGED", "connection-reacquisition": "NOT_JUDGED",
    "readonly-candidate-transaction": "UNDER_SAMPLED", "paged-without-order": "UNDER_SAMPLED",
    "unbatched-write-loop": "UNDER_SAMPLED", "gc-inflated-latency": "NOT_LISTED", "heap-growth-after-gc": "NOT_LISTED",
    "work-after-response": "NOT_VALIDATED", "changed-code-not-executed": "PASSED",
}  # fmt: skip
M5 = (
    "exceptions-caught-in-code", "hidden-outbound-calls", "thread-local-left-set", "resource-not-closed",
    "threads-per-request", "request-input-in-sink",
)  # fmt: skip


def _finding(unlisted: str | None = None) -> Finding:
    return Finding("k", "k", True, "s", 3, 3, [], ["r1"], ["Request"], [["1"]], [], None, unlisted)


# ported: DefaultListingTests.everyKindOf20HasTheOutcomeItsPerKindGateRecorded
def test_every_kind_has_the_outcome_its_per_kind_gate_recorded() -> None:
    assert {spec.kind for spec in KINDS} == set(REPORTED)
    assert set(REPORTED) <= set(listing.KINDS)
    for kind, outcome in REPORTED.items():
        entry = listing.of(kind)
        assert entry.outcome.name == outcome, kind
        assert (entry.unlisted_reason is None) == entry.outcome.listed, kind
        assert entry.outcome.listed or entry.unlisted_reason, kind


# ported: DefaultListingTests.m5sObservationsAndUnknownKindsAreNotJudgedAndNotListedUntilTheyPassTheGate
def test_m5_observations_and_unknown_kinds_are_not_judged_and_not_listed() -> None:
    for kind in M5:
        assert listing.of(kind).outcome is Outcome.NOT_JUDGED, kind
    assert listing.of("a-kind-added-later").outcome is Outcome.NOT_JUDGED
    assert listing.apply("a-kind-added-later", _finding()).listed is False


# ported: DefaultListingTests.onlyKindsThatPassedOrStayedSilentAreListedAndTheOthersSayWhy
def test_only_kinds_that_passed_or_stayed_silent_are_listed_and_the_others_say_why() -> None:
    for kind, outcome in REPORTED.items():
        applied = listing.apply(kind, _finding())
        assert applied.listed is (outcome in {"PASSED", "NOT_VALIDATED"}), kind
        if not applied.listed:
            assert applied.unlisted == listing.of(kind).unlisted_reason, kind
    assert listing.apply("gc-inflated-latency", _finding()).unlisted == listing.MEMORY


# ported: DefaultListingTests.aKindThatFailedItsGateReplacesTheRowsOwnReasonAndNamesThePanelItIsFoldedInto
def test_a_failed_kind_replaces_the_rows_reason_and_names_the_panel_it_is_folded_into() -> None:
    own = _finding("not prominent")
    assert "Why this route is slow" in str(listing.apply("route-time-breakdown", own).unlisted)
    assert "Exceptions panel" in str(listing.apply("exception-hotspots", _finding()).unlisted)
    assert "Database connection pools panel" in str(listing.apply("connections-per-request", _finding()).unlisted)
    assert "AI panel" in str(listing.apply("ai-usage-by-route", _finding()).unlisted)
    assert listing.apply("safe-method-dml", own).unlisted == "not prominent"
