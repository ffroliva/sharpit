"""The Runtime Insights report over the journal (BootUI ``RuntimeInsightsService.java:1032-1126``).

The journal is copied once (``snapshot.project``) and every kind runs on the copy, so a slow kind never holds the
journal lock. Insight text is built only from journal fields, which are masked and literal-free at offer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from sharpit.engine.collectors.insights import listing
from sharpit.engine.collectors.insights.finding import Evaluation
from sharpit.engine.collectors.insights.registry import KINDS
from sharpit.engine.collectors.insights.snapshot import Snapshot, project
from sharpit.engine.collectors.insights.text import counted, stable_hash

DISABLED = "Runtime Insights reads the runtime journal, which is disabled: set SHARPIT_RUNTIME_JOURNAL_ENABLED=true."
NOT_IMPLEMENTED = "sharpit has not implemented this observation yet."
NOT_EVALUATED = "This observation could not be evaluated."
MAX_EXEMPLARS, MAX_EVIDENCE_ROWS = 3, 20  # RuntimeInsightsService.MAX_EXEMPLARS, MAX_EVIDENCE_ROWS
_LINKS = ("requestId", "executionId", "traceId")

Row = dict[str, object]


class Observation(Protocol):
    @property
    def kind(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def minimum_tier(self) -> str: ...
    @property
    def reads(self) -> frozenset[str]: ...
    @property
    def optional_reads(self) -> frozenset[str]: ...

    @property
    def evaluate(self) -> Any: ...  # (Snapshot) -> Evaluation, or None while a kind is a stub


def id_of(kind: str, key: str) -> str:
    return f"{kind}:{stable_hash(key)}"


def _not_recorded(source: str) -> str:
    return f"The runtime journal does not record the {source} source (SHARPIT_RUNTIME_JOURNAL_SOURCES)."


def _check(observation: Observation, status: str, eligible: int, findings: int, reason: str | None) -> Row:
    return {
        "kind": observation.kind, "title": observation.title, "status": status, "eligibleRequests": eligible,
        "findings": findings, "reason": reason,
    }  # fmt: skip


def _partial(observation: Observation, snapshot: Snapshot) -> str | None:
    sources = observation.reads | {s for s in observation.optional_reads if snapshot.recorded(s)}
    dropped = sum(snapshot.dropped(source) for source in sources)
    if not dropped:
        return None
    return (
        f"The journal dropped {dropped} events this observation reads, so its findings are incomplete: "
        "a dropped event can hide a finding, or make one appear."
    )


def _unseen(observation: Observation, snapshot: Snapshot) -> list[str]:
    return [
        f"Without the {source} source, which the runtime journal does not record, its evidence is not counted."
        for source in sorted(observation.optional_reads)
        if not snapshot.recorded(source)
    ]


def _row(observation: Observation, found: Any, partial: str | None, unseen: list[str]) -> Row:
    finding = listing.apply(observation.kind, found)
    status = "INSUFFICIENT" if not finding.sufficient else "OBSERVED" if partial is None else "PARTIAL"
    return {
        "id": id_of(observation.kind, finding.key), "kind": observation.kind, "subject": finding.subject,
        "status": status, "sentence": finding.sentence, "eligible": finding.eligible, "affected": finding.affected,
        "minimumTier": finding.tier or observation.minimum_tier, "whatToCheck": list(finding.what_to_check),
        "exemplarRequestIds": list(finding.exemplar_request_ids[:MAX_EXEMPLARS]),
        "evidenceRows": min(MAX_EVIDENCE_ROWS, len(finding.rows)),
        "limitations": [*finding.limitations, *unseen, *([partial] if partial else [])],
        "listed": finding.listed, "unlistedReason": finding.unlisted,
    }  # fmt: skip


def _coverage(snapshot: Snapshot) -> list[Row]:
    rows: list[Row] = []
    for source, events in snapshot.records.items():
        if not events:
            continue
        linked = [next((i for i, key in enumerate(_LINKS) if event.get(key)), 3) for event in events]
        rows.append({
            "source": source, "events": len(events), "byRequestId": linked.count(0), "byExecutionId": linked.count(1),
            "byTraceId": linked.count(2), "unlinked": linked.count(3), "dropped": snapshot.dropped(source),
        })  # fmt: skip
    return rows


def _window(snapshot: Snapshot) -> Row:
    status = snapshot.status
    return {
        "runId": status["runId"], "firstEventAt": status["oldestRetainedAt"], "lastEventAt": snapshot.newest_at,
        "retainedEvents": status["retainedEvents"], "requests": len(snapshot.records.get("http", ())),
        "evictedEvents": status["evictedEvents"], "droppedEvents": status["droppedEvents"],
    }  # fmt: skip


def _limitations(snapshot: Snapshot) -> list[str]:
    evicted = int(snapshot.status["evictedEvents"])
    if not evicted:
        return []
    return [
        f"The journal evicted {counted(evicted, 'older event')}, so requests before the oldest retained event "
        "are not projected."
    ]


def _report(
    available: bool, reason: str | None, window: Row | None, coverage: list[Row], checks: list[Row],
    observations: list[Row], limitations: list[str],
) -> Row:  # fmt: skip
    return {
        "available": available, "unavailableReason": reason, "window": window, "coverage": coverage,
        "checks": checks, "observations": observations, "limitations": limitations, "notExercised": [],
        "notExercisedOmitted": 0,
    }  # fmt: skip


class InsightsService:
    def __init__(self, journal: Any, observations: Sequence[Observation] | None = None) -> None:
        self.journal = journal
        self.observations: Sequence[Observation] = KINDS if observations is None else observations

    def report(self) -> Row:
        if self.journal is None:
            return _report(False, DISABLED, None, [], [], [], [])
        snapshot = project(self.journal)
        checks: list[Row] = []
        rows: list[Row] = []
        for observation in self.observations:
            check, found = self._evaluate(observation, snapshot)
            checks.append(check)
            rows += found
        rows.sort(key=lambda row: (row["status"] == "INSUFFICIENT", -int(str(row["affected"])), str(row["id"])))
        return _report(True, None, _window(snapshot), _coverage(snapshot), checks, rows, _limitations(snapshot))

    def _evaluate(self, observation: Observation, snapshot: Snapshot) -> tuple[Row, list[Row]]:
        missing = next((s for s in sorted(observation.reads) if not snapshot.recorded(s)), None)
        if missing is not None:
            return _check(observation, "NOT_APPLICABLE", 0, 0, _not_recorded(missing)), []
        evaluate = observation.evaluate
        if evaluate is None:
            return _check(observation, "NOT_APPLICABLE", 0, 0, NOT_IMPLEMENTED), []
        partial, unseen = _partial(observation, snapshot), _unseen(observation, snapshot)
        try:
            evaluation: Evaluation = evaluate(snapshot)
        except Exception:  # noqa: BLE001 - a kind never crashes the host or the other kinds
            return _check(observation, "UNAVAILABLE", 0, 0, NOT_EVALUATED), []
        reasons = [partial] if partial else list(unseen)
        if evaluation.uncounted:
            reasons.append(evaluation.uncounted)
        if not evaluation.worked:
            reasons.insert(0, "No eligible work was recorded for this check.")
        status = "INSUFFICIENT" if not evaluation.worked else "EVALUATED" if partial is None else "PARTIAL"
        check = _check(observation, status, evaluation.eligible, len(evaluation.findings), " ".join(reasons) or None)
        return check, [_row(observation, found, partial, unseen) for found in evaluation.findings]
