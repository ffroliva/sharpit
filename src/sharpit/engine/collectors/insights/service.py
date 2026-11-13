"""The Runtime Insights report over the journal (BootUI ``RuntimeInsightsService.java:1032-1126``).

The journal is copied once (``snapshot.project``) and every kind runs on the copy, so a slow kind never holds the
journal lock. Insight text is built only from journal fields, which are masked and literal-free at offer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from sharpit.engine.collectors.insights import listing
from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.registry import KINDS
from sharpit.engine.collectors.insights.snapshot import (
    DEFAULT_AI_TOKEN_THRESHOLD,
    LEFT_OUT_BEFORE_LOSS,
    PanelEnabled,
    Snapshot,
    project,
)
from sharpit.engine.collectors.insights.sqlcapture import NOT_RECORDED_SUFFIX, SQL_SOURCES, SqlCapture
from sharpit.engine.collectors.insights.sqlcapture import UNREADABLE as SQL_CAPTURE_UNREADABLE
from sharpit.engine.collectors.insights.sqlcapture import for_context as sql_capture_for
from sharpit.engine.collectors.insights.text import UNDER_DEFAULT_FLOOR, counted, stable_hash

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

logger = logging.getLogger("sharpit")

DISABLED = "Runtime Insights reads the runtime journal, which is disabled: set SHARPIT_RUNTIME_JOURNAL_ENABLED=true."
NOT_IMPLEMENTED = "sharpit has not implemented this observation yet."
NOT_EVALUATED = "This observation could not be evaluated."
UNKNOWN_PREFIX = "No observation "
UNKNOWN_SUFFIX = " in this run's retained events: it may have been evicted or cleared."
UNCOUNTED_WITHHELD = "Some recorded work was not counted; the detail is withheld under METADATA_ONLY exposure."
TEXT_OMITTED = "The text of this observation is withheld under METADATA_ONLY exposure: counts, ids and statuses only."
MAX_EXEMPLARS, MAX_EVIDENCE_ROWS = 3, 20  # RuntimeInsightsService.MAX_EXEMPLARS, MAX_EVIDENCE_ROWS

Row = dict[str, object]
Mask = Callable[[str], str | None]  # None: METADATA_ONLY shows no text
Details = dict[str, tuple[Row, Finding]]


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
    def evaluate(self) -> Callable[[Snapshot], Evaluation] | None: ...  # None while a kind is a stub


def id_of(kind: str, key: str) -> str:
    return f"{kind}:{stable_hash(key)}"


def _not_recorded(source: str) -> str:
    return f"The runtime journal does not record the {source} source (SHARPIT_RUNTIME_JOURNAL_SOURCES)."


def _panels_label(panels: Sequence[str]) -> str:
    """``The sql-trace panel`` / ``The a, b and c panels`` (``RuntimeInsightsService.panelsLabel``)."""
    if len(panels) == 1:
        return f"The {panels[0]} panel"
    return f"The {', '.join(panels[:-1])} and {panels[-1]} panels"


def _verb(panels: Sequence[str]) -> str:
    return "is" if len(panels) == 1 else "are"


def _missing(snapshot: Snapshot, source: str) -> str:
    """Why a required source is absent (``missingSource``): not journaled, else its disabled panel is named."""
    if not snapshot.journaled(source):
        return _not_recorded(source)
    panels = snapshot.hidden[source]
    return f"{_panels_label(panels)}, whose evidence this reads, {_verb(panels)} disabled."


def _requests_hidden(observation: Observation, snapshot: Snapshot) -> str | None:
    """``missingSource``'s last rule (v2.3.0 :1362-1368): the http panel is off, so no request is visible to a kind
    that examines requests."""
    if not getattr(observation, "uses_requests", True) or not (panels := snapshot.hidden.get("http")):
        return None
    return f"{_panels_label(panels)} {_verb(panels)} disabled, so its unit-of-work evidence cannot be evaluated."


def _check(observation: Observation, status: str, eligible: int, findings: int, reason: str | None) -> Row:
    return {
        "kind": observation.kind, "title": observation.title, "status": status, "eligibleRequests": eligible,
        "findings": findings, "reason": reason,
    }  # fmt: skip


def _partial(observation: Observation, snapshot: Snapshot) -> str | None:
    sources = observation.reads | {s for s in observation.optional_reads if snapshot.available(s)}
    dropped = sum(snapshot.dropped(source) for source in sources)
    if not dropped:
        return None
    return (
        f"The journal dropped {dropped} events this observation reads, so its findings are incomplete: "
        "a dropped event can hide a finding, or make one appear."
    )


def _unseen(observation: Observation, snapshot: Snapshot) -> list[str]:
    unseen: list[str] = []
    for source in sorted(observation.optional_reads):
        if panels := snapshot.hidden.get(source):
            unseen.append(f"{_panels_label(panels)} {_verb(panels)} disabled, so its evidence is not counted.")
        elif not snapshot.journaled(source):
            unseen.append(
                f"Without the {source} source, which the runtime journal does not record, its evidence is not counted."
            )
    return unseen


def _row_status(sufficient: bool, partial: str | None) -> str:
    if not sufficient:
        return "INSUFFICIENT"
    return "OBSERVED" if partial is None else "PARTIAL"


def _check_status(worked: bool, partial: str | None) -> str:
    if not worked:
        return "INSUFFICIENT"
    return "EVALUATED" if partial is None else "PARTIAL"


def _ids(ids: Sequence[str], mask: Mask) -> list[str]:
    """Ids are metadata: METADATA_ONLY (``None``) keeps them, any other mask answer, even "", replaces them."""
    return [i if (m := mask(i)) is None else m for i in ids]


def _row(
    observation: Observation, found: Any, partial: str | None, unseen: list[str], mask: Mask
) -> tuple[Row, Finding]:
    finding = listing.apply(observation.kind, found)
    status = _row_status(finding.sufficient, partial)
    hidden = mask("") is None  # METADATA_ONLY: every text is withheld, and the row says so
    own = [] if hidden else [t for t in map(mask, finding.limitations) if t is not None]
    own += [TEXT_OMITTED, *(t for t in finding.limitations if t == UNDER_DEFAULT_FLOOR)] if hidden else []
    return {
        "id": id_of(observation.kind, finding.key), "kind": observation.kind, "subject": mask(finding.subject) or "",
        "status": status, "sentence": mask(finding.sentence) or "", "eligible": finding.eligible,
        "affected": finding.affected,
        "minimumTier": finding.tier or observation.minimum_tier,
        "whatToCheck": [t for t in map(mask, finding.what_to_check) if t is not None],
        "exemplarRequestIds": _ids(finding.exemplar_request_ids[:MAX_EXEMPLARS], mask),
        "evidenceRows": min(MAX_EVIDENCE_ROWS, len(finding.rows)),
        "limitations": [*own, *unseen, *([partial] if partial else [])],
        "listed": finding.listed, "unlistedReason": finding.unlisted,
    }, finding  # fmt: skip


def _link(snapshot: Snapshot, event: Row) -> int:
    """``InsightsSnapshot.java:171-220``: a request or execution id links by itself, a trace id only to an owner."""
    if event.get("requestId"):
        return 0
    if event.get("executionId"):
        return 1
    return 2 if snapshot.request_index.owner(event) is not None else 3


def _coverage(snapshot: Snapshot) -> list[Row]:
    rows: list[Row] = []
    index = snapshot.request_index
    for source, retained in snapshot.records.items():
        # InsightsSnapshot.of reads the visible entries; with nothing left out they are all of them
        events = [e for e in retained if not index.left_out_event(e)] if index.left_out else list(retained)
        if not events:
            continue
        linked = [_link(snapshot, event) for event in events]
        rows.append({
            "source": source, "events": len(events), "byRequestId": linked.count(0), "byExecutionId": linked.count(1),
            "byTraceId": linked.count(2), "unlinked": linked.count(3), "dropped": snapshot.dropped(source),
        })  # fmt: skip
    return rows


def _window(snapshot: Snapshot) -> Row:
    status, left_out = snapshot.status, snapshot.request_index.left_out
    return {
        "runId": status["runId"], "firstEventAt": status["oldestRetainedAt"], "lastEventAt": snapshot.newest_at,
        "retainedEvents": status["retainedEvents"], "requests": len(snapshot.records.get("http", ())) - left_out,
        "evictedEvents": status["evictedEvents"], "droppedEvents": status["droppedEvents"],
    }  # fmt: skip


def _left_out(units: int) -> str | None:
    """``leftOutBeforeLoss``: the requests left out because they started before an event the journal lost."""
    if not units:
        return None
    one = units == 1
    return (
        f"{counted(units, 'request or execution', 'requests or executions')} {LEFT_OUT_BEFORE_LOSS}, so "
        f"{'it is left out: some of its' if one else 'they are left out: some of their'} events may be missing."
    )


def _left_out_reasons(observation: Observation, snapshot: Snapshot) -> list[str]:
    left_out = _left_out(snapshot.request_index.left_out) if getattr(observation, "uses_requests", True) else None
    return [left_out] if left_out else []


def _limitations(snapshot: Snapshot) -> list[str]:
    evicted = int(snapshot.status["evictedEvents"])
    limitations: list[str] = []
    if evicted:
        limitations.append(
            f"The journal evicted {counted(evicted, 'older event')}, so requests before the oldest retained event "
            "are not projected."
        )
    if left_out := _left_out(snapshot.request_index.left_out):
        limitations.append(left_out)
    return limitations


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
    def __init__(
        self,
        journal: Any,
        observations: Sequence[Observation] | None = None,
        ai_token_threshold: int = DEFAULT_AI_TOKEN_THRESHOLD,
        panel_enabled: PanelEnabled | None = None,
        sql_capture: Callable[[], SqlCapture] | None = None,
    ) -> None:
        self.journal = journal
        self.sql_capture = sql_capture or SqlCapture.capturing  # RuntimeInsightsService.sqlCapture, default capturing
        self.panel_enabled = panel_enabled  # None: every panel counts as enabled
        # BootUI rejects a non-positive threshold at startup; sharpit takes the default (settings fail-safe)
        self.ai_token_threshold = ai_token_threshold if ai_token_threshold >= 1 else DEFAULT_AI_TOKEN_THRESHOLD
        self.observations: Sequence[Observation] = KINDS if observations is None else observations
        masker = getattr(journal, "masker", None)
        self._mask: Mask = masker.mask_text if masker else str

    def report(self) -> Row:
        return self._build()[0]

    def insight(self, observation_id: str) -> Row:
        """One observation with its evidence (``RuntimeInsightsService.insight``): at most 20 masked rows."""
        if self.journal is None:
            return _detail(False, DISABLED, None, [], [], 0)
        found = self._build()[1].get(observation_id)
        if found is None:
            return _detail(False, f"{UNKNOWN_PREFIX}{observation_id}{UNKNOWN_SUFFIX}", None, [], [], 0)
        row, finding = found
        shown = (
            []
            if self._mask("") is None
            else [[self._mask(c) or "" for c in r] for r in finding.rows[:MAX_EVIDENCE_ROWS]]
        )
        return _detail(True, None, row, finding.columns, shown, len(finding.rows) - len(shown))

    def _build(self) -> tuple[Row, Details]:
        if self.journal is None:
            return _report(False, DISABLED, None, [], [], [], []), {}
        snapshot = project(self.journal, self.ai_token_threshold, self.panel_enabled)
        capture = self._capture()
        checks: list[Row] = []
        found: list[tuple[Row, Finding]] = []
        for observation in self.observations:
            check, rows = self._evaluate(observation, snapshot, capture)
            checks.append(check)
            found += rows
        found.sort(
            key=lambda pair: (pair[0]["status"] == "INSUFFICIENT", -int(str(pair[0]["affected"])), str(pair[0]["id"]))
        )
        rows = [row for row, _ in found]
        return _report(True, None, _window(snapshot), _coverage(snapshot), checks, rows, _limitations(snapshot)), {
            str(row["id"]): (row, finding) for row, finding in found
        }

    def _capture(self) -> SqlCapture:
        """RuntimeInsightsService.sqlCapture: asked once per report; null is capturing, a failure is not recorded."""
        try:
            return self.sql_capture() or SqlCapture.capturing()
        except Exception as error:  # noqa: BLE001 - the report never fails over this question
            return SqlCapture.not_recorded(SQL_CAPTURE_UNREADABLE.format(type(error).__name__))

    def _evaluate(
        self, observation: Observation, snapshot: Snapshot, capture: SqlCapture
    ) -> tuple[Row, list[tuple[Row, Finding]]]:
        missing = next((s for s in sorted(observation.reads) if not snapshot.available(s)), None)
        if missing is not None:
            return _check(observation, "NOT_APPLICABLE", 0, 0, _missing(snapshot, missing)), []
        if (hidden := _requests_hidden(observation, snapshot)) is not None:
            return _check(observation, "NOT_APPLICABLE", 0, 0, hidden), []
        gate = getattr(observation, "not_applicable", None)  # BootUI Observation.notApplicable; a stub has none
        reason = gate(snapshot) if gate else None
        if reason is not None:
            return _check(observation, "NOT_APPLICABLE", 0, 0, reason), []
        evaluate = observation.evaluate
        if evaluate is None:
            return _check(observation, "NOT_APPLICABLE", 0, 0, NOT_IMPLEMENTED), []
        reads_sql = bool(observation.reads & SQL_SOURCES)
        if not capture.recorded and reads_sql:
            return _check(observation, "UNAVAILABLE", 0, 0, capture.reason), []
        partial, unseen = _partial(observation, snapshot), _unseen(observation, snapshot)
        caveat = _sql_capture_caveat(observation, snapshot, capture)
        if caveat:
            unseen.append(caveat)
        try:
            evaluation: Evaluation = evaluate(snapshot)
        except Exception:  # noqa: BLE001 - a kind never crashes the host or the other kinds
            logger.debug("insights kind %s could not be evaluated", observation.kind)  # the id only, never the error
            return _check(observation, "UNAVAILABLE", 0, 0, NOT_EVALUATED), []
        reasons = [partial, caveat] if partial and caveat else [partial] if partial else list(unseen)
        if evaluation.uncounted:
            reasons.append(
                self._mask(evaluation.uncounted) or UNCOUNTED_WITHHELD
            )  # masked away: still say work went uncounted
        reasons += _left_out_reasons(observation, snapshot)  # what it did not judge: empty is not "nothing found"
        if not evaluation.worked:
            reasons.insert(0, "No eligible work was recorded for this check.")
        status = _check_status(evaluation.worked, partial)
        reason = " ".join(r for r in reasons if r) or None
        check = _check(observation, status, evaluation.eligible, len(evaluation.findings), reason)
        return check, [_row(observation, f, partial, unseen, self._mask) for f in evaluation.findings]


def _sql_capture_caveat(observation: Observation, snapshot: Snapshot, capture: SqlCapture) -> str | None:
    """The SQL-capture caveat for a read of SQL (required or optional) while a SQL source is enabled and producing for
    the journal (BootUI ``snapshot.records``: the source is on, not that statements exist), else None."""
    if capture.reason is None or not any(snapshot.journaled(s) for s in SQL_SOURCES):
        return None
    if not (observation.reads | observation.optional_reads) & SQL_SOURCES:
        return None
    return capture.reason if capture.recorded else capture.reason + NOT_RECORDED_SUFFIX


def _detail(
    available: bool,
    reason: str | None,
    observation: Row | None,
    columns: list[str],
    rows: list[list[str]],
    truncated: int,
) -> Row:
    return {
        "available": available, "unavailableReason": reason, "observation": observation, "columns": list(columns),
        "rows": [{"cells": cells} for cells in rows], "truncated": truncated,
    }  # fmt: skip


def insights_service(ctx: SharpitContext) -> InsightsService:
    """The install's service over its journal, shared by the routes and the tools (a test seeds it through ``lazy``)."""
    threshold = ctx.settings.runtime_insights_ai_token_threshold

    def panel_enabled(panel_id: str) -> bool:  # settings only: a panel sharpit has not shipped yet is not "disabled"
        panel = ctx.settings.panels.get(panel_id)
        return panel is None or panel.enabled

    return ctx.lazy(
        "runtime-insights",
        lambda: InsightsService(ctx.capture.journal, None, threshold, panel_enabled, lambda: sql_capture_for(ctx)),
    )
