"""One request's time split into phases (BootUI ``RouteTimeBreakdown.Breakdown`` and ``Totals``).

sharpit's http event has a monotonic start (``startNanos``) but no handler or response marks and no authentication
time, so a request has two phases: SQL, placed as BootUI places it (``RouteTimeBreakdown.interval``: the statement ends
at ``completedNanos`` and began ``durationNanos`` before, both against the request's ``startNanos`` on one
``perf_counter_ns`` clock, clipped to the request and unioned so overlapping statements count once), and the
unattributed rest. A request without ``startNanos`` is unplaced, never guessed from wall clocks.
Connection waits (the ``connection`` event's ``waitNanos`` is always 0), REST client calls, authorization, Hibernate
flushes and message sends have no producer; AI calls carry no wall-clock start, so their time stays unattributed.
"""

from __future__ import annotations

from dataclasses import dataclass

from sharpit.engine.collectors.insights.requests import Request, count
from sharpit.engine.collectors.insights.text import median, millis

SQL, UNATTRIBUTED = "SQL", "Unattributed"
PHASES = (SQL, UNATTRIBUTED)  # BootUI's order among the phases sharpit can place
COLUMNS = ["Phase", "Total (ms)", "Share", "Median per request (ms)"]
OVERLAP = "Overlapping calls, counted once above"


@dataclass(frozen=True)
class Breakdown:
    request: Request
    duration: int
    phases: dict[str, int]  # only phases with time
    overlap: int


def _interval(event: dict[str, object], start_nanos: int, duration: int) -> tuple[int, int] | None:
    """The statement's span on its request, clipped to it; ``None`` with no completion, no time or outside it."""
    completed, took = count(event.get("completedNanos")), count(event.get("durationNanos"))
    if completed is None or completed < 0 or took is None or took <= 0:
        return None
    end = completed - start_nanos
    low, high = max(0, end - took), min(duration, end)
    return (low, high) if high > low else None


def breakdown_of(request: Request) -> Breakdown | None:
    """``Breakdown.of``: ``None`` when the request has no monotonic start or no duration (counted as unplaced)."""
    if request.start_nanos is None or request.duration_nanos is None:
        return None
    duration = request.duration_nanos
    spans = sorted(s for e in request.children["sql"] if (s := _interval(e, request.start_nanos, duration)) is not None)
    union, reach = 0, 0
    for low, high in spans:
        union += max(0, high - max(low, reach))
        reach = max(reach, high)
    phases = {SQL: union, UNATTRIBUTED: duration - union}
    overlap = sum(high - low for low, high in spans) - union
    return Breakdown(request, duration, {p: t for p, t in phases.items() if t > 0}, overlap)


def percent(part: int, whole: int) -> str:
    return f"{int(part * 100 / whole + 0.5)} %"


@dataclass(frozen=True)
class Totals:
    """Every phase over a route's requests: in total, and per request for its median."""

    per_phase: dict[str, list[int]]  # phase -> its time in each breakdown, in order
    total: int
    overlap: int
    durations: list[int]

    @classmethod
    def of(cls, breakdowns: list[Breakdown]) -> Totals:
        per_phase = {
            p: [b.phases.get(p, 0) for b in breakdowns] for p in PHASES if any(p in b.phases for b in breakdowns)
        }
        return cls(per_phase, sum(b.duration for b in breakdowns), sum(b.overlap for b in breakdowns),
                   [b.duration for b in breakdowns])  # fmt: skip

    @property
    def whole(self) -> int:
        """The total as a divisor (never 0)."""
        return max(1, self.total)

    def ranked(self) -> list[tuple[str, int]]:
        """Phases and their total time, most time first (a tie keeps ``PHASES`` order)."""
        return sorted(((p, sum(v)) for p, v in self.per_phase.items()), key=lambda pair: -pair[1])

    def only_unattributed(self) -> bool:
        """No time at all was placed in a named phase: no phase marks, and no recorded call took time."""
        return all(p == UNATTRIBUTED or sum(v) == 0 for p, v in self.per_phase.items())

    def rows(self) -> list[list[str]]:
        rows = [
            [phase, millis(sum(v)), percent(sum(v), self.whole), millis(median(v))]
            for phase, v in self.per_phase.items()
            if sum(v)
        ]
        return [*rows, [OVERLAP, millis(self.overlap), "", ""]] if self.overlap > 0 else rows
