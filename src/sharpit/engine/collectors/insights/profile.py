"""The Profile resources floor (BootUI ``ResourceProfileService.java:85-125``): the three calls start nothing.

BootUI starts a bounded JFR session. sharpit has no resource sampler (proposed deviation P-I1), so status, start and
stop all answer BootUI's ``UNAVAILABLE`` shape with the reason: no journal, no ``resources`` source, or no sampler.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cmp_to_key
from typing import TYPE_CHECKING, Any

from sharpit.engine.collectors.insights.service import DISABLED

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

RESOURCES_OFF = (
    "Profile resources joins samples to the request segments the runtime journal's resources source measures: "
    "add resources to SHARPIT_RUNTIME_JOURNAL_SOURCES."
)
NO_SAMPLER = "sharpit has no resource sampler."


class ResourceProfile:
    def __init__(self, journal: Any, max_duration: float) -> None:
        self.journal = journal
        self.max_duration = max_duration

    def status(self) -> dict[str, Any]:
        return self._floor()

    def start(self) -> dict[str, Any]:
        return self._floor()

    def stop(self) -> dict[str, Any]:
        return self._floor()

    def _reason(self) -> str:
        if self.journal is None:
            return DISABLED
        sources = self.journal.sources  # None: no filter
        return NO_SAMPLER if sources is None or "resources" in sources else RESOURCES_OFF

    def _floor(self) -> dict[str, Any]:
        return {
            "state": "UNAVAILABLE", "reason": self._reason(), "sampler": None, "startedAt": None, "endsAt": None,
            "finishedAt": None, "maxDurationSeconds": int(self.max_duration), "cpuSamples": 0, "outsideSamples": 0,
            "requests": 0, "routes": [], "routesOmitted": 0, "limitations": [],
        }  # fmt: skip


def resource_profile(ctx: SharpitContext) -> ResourceProfile:
    return ctx.lazy(
        "runtime-insights.profile",
        lambda: ResourceProfile(ctx.capture.journal, ctx.settings.resources_jfr_max_duration),
    )


@dataclass(frozen=True)
class RequestTimelineItem:
    """One recorded piece of a request's work on its timeline (BootUI ``RequestTimelineItemDto``)."""

    label: str
    offset_millis: int = 0
    duration_micros: int | None = None
    detail: str | None = None
    source: str = "sql"
    severity: str = "OK"
    thread: str | None = None
    thread_kind: str | None = None


@dataclass(frozen=True)
class TimedItem:
    """A timeline item with its publication sequence and optional SQL start nanos (BootUI ``Timed``)."""

    item: RequestTimelineItem
    sequence: int
    start_nanos: int | None = None

    @property
    def offset_millis(self) -> int:
        return self.item.offset_millis


def sql_start_nanos(event: Mapping[str, Any]) -> int | None:
    """Monotonic execution start nanos of a SQL item (BootUI ``RequestJournalProfiles.startNanos``).

    Derived as ``completedNanos - durationNanos`` when non-negative, else None.
    """
    if event.get("source") != "sql":
        return None
    completed = event.get("completedNanos")
    duration = event.get("durationNanos")
    if (
        isinstance(completed, int)
        and not isinstance(completed, bool)
        and completed >= 0
        and isinstance(duration, int)
        and not isinstance(duration, bool)
        and duration >= 0
    ):
        return completed - duration
    return None


def timeline_comparator(left: TimedItem, right: TimedItem) -> int:
    """Comparator for request profile timeline items (BootUI ``RequestJournalProfiles.timed.sort``).

    Items with equal offsetMillis are ordered by SQL start nanos (when both items carry one),
    then by sequence. A SQL tie-break never moves SQL ahead of non-SQL items.
    """
    if left.offset_millis != right.offset_millis:
        return -1 if left.offset_millis < right.offset_millis else 1
    if left.start_nanos is not None and right.start_nanos is not None and left.start_nanos != right.start_nanos:
        return -1 if left.start_nanos < right.start_nanos else 1
    if left.sequence != right.sequence:
        return -1 if left.sequence < right.sequence else 1
    return 0


def order_timeline(items: Iterable[TimedItem]) -> list[RequestTimelineItem]:
    """Order request profile timeline items by offsetMillis, SQL start nanos, and sequence."""
    timed = list(items)
    timed.sort(key=cmp_to_key(timeline_comparator))
    return [t.item for t in timed]


@dataclass(frozen=True)
class RequestJournalProfile:
    timeline: list[RequestTimelineItem]


class RequestJournalProfiles:
    """Request-profile timeline ordering (BootUI ``RequestJournalProfiles``)."""

    def __init__(self, journal: Any = None) -> None:
        self.journal = journal

    def profile(self, request_id: str) -> RequestJournalProfile:
        if self.journal is None:
            return RequestJournalProfile(timeline=[])
        start = 0
        with self.journal._lock:
            for event, _, _, _ in self.journal._events:
                if event.get("requestId") == request_id and event.get("source") == "http":
                    start = int(event.get("epochMillis") or event.get("startedAt") or 0)
                    break
            timed: list[TimedItem] = []
            for seq, (event, _, _, _) in enumerate(self.journal._events):
                if event.get("requestId") != request_id or event.get("source") == "http":
                    continue
                source = str(event.get("source") or "")
                offset_millis = max(0, int(event.get("epochMillis") or event.get("startedAt") or 0) - start)
                duration_nanos = event.get("durationNanos")
                duration_micros = (
                    duration_nanos // 1000 if isinstance(duration_nanos, int) and duration_nanos >= 0 else None
                )
                if source == "connection":
                    ds = event.get("dataSource")
                    label = f"Connection held from {ds}" if ds else "Connection held"
                else:
                    label = str(event.get("sql") or event.get("label") or event.get("summary") or "")
                item = RequestTimelineItem(
                    source=source,
                    label=label,
                    offset_millis=offset_millis,
                    duration_micros=duration_micros,
                )
                start_n = sql_start_nanos(event)
                timed.append(TimedItem(item=item, sequence=seq, start_nanos=start_n))
        return RequestJournalProfile(timeline=order_timeline(timed))
