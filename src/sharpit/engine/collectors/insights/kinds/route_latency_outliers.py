"""``route-latency-outliers``: BootUI ``E/insights/RouteLatencyOutliers.java``."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.sql_readability import read_statement
from sharpit.engine.collectors.insights.text import counted, millis

KIND = "route-latency-outliers"
TITLE = "Slow route outliers vs. baseline"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http"})
OPTIONAL_READS: frozenset[str] = frozenset({"sql", "connection", "cache", "rest-client", "orm"})
IMPLEMENTED = True

MIN_WARM_REQUESTS = 5
MIN_PRELIMINARY_WARM_REQUESTS = 2
MIN_OUTLIER_MULTIPLIER = 4
MIN_OUTLIER_DELTA_NANOS = 100_000_000
MAX_DISTINGUISHING_SQL_SHAPES = 5
COLUMNS = ["Dimension", "Outlier", "Baseline", "Delta"]
CHECKS = [
    "Open the outlier request in Live Activity to inspect its timeline and the Compared with baseline request card.",
    "Compare the distinguishing SQL shapes, cache misses, and outbound calls between the outlier and the "
    "baseline request.",
]


@dataclass
class _Metrics:
    sql_executions: int = 0
    sql_nanos: int = 0
    unverified_sql: bool = False
    sql_shapes: dict[str, list[int]] = field(default_factory=dict[str, list[int]])
    sql_display_shapes: dict[str, str] = field(default_factory=dict[str, str])
    connection: bool = False
    connection_wait: int = 0
    cache: bool = False
    cache_hits: int = 0
    cache_misses: int = 0
    rest_calls: int = 0
    rest_nanos: int = 0
    orm: bool = False
    orm_flushes: int = 0
    orm_auto_flushes: int = 0
    orm_entities_measured: bool = False
    orm_entities_unmeasured: bool = False
    orm_max_entities: int = 0

    @classmethod
    def of(cls, request: Request) -> _Metrics:
        result = cls()
        for source, add in _METRIC_ADDITIONS.items():
            for event in request.children[source]:
                add(result, event)
        return result


def _add_sql(result: _Metrics, event: dict[str, object]) -> None:
    if event.get("provenance") != "EXECUTION":
        result.unverified_sql = True
        return
    duration = max(0, _integer(event.get("durationNanos")))
    result.sql_executions += 1
    result.sql_nanos += duration
    text = event.get("sql")
    if isinstance(text, str) and text.strip():
        display_shape = read_statement(text).normalized
        shape = display_shape.casefold()
        if shape:
            result.sql_display_shapes.setdefault(shape, display_shape)
            tally = result.sql_shapes.setdefault(shape, [0, 0])
            tally[0] += 1
            tally[1] += duration


def _add_connection(result: _Metrics, event: dict[str, object]) -> None:
    result.connection = True
    result.connection_wait += max(0, _integer(event.get("waitNanos")))


def _add_cache(result: _Metrics, event: dict[str, object]) -> None:
    result.cache = True
    operation = event.get("operation")
    result.cache_hits += isinstance(operation, str) and operation.upper() == "HIT"
    result.cache_misses += isinstance(operation, str) and operation.upper() == "MISS"


def _add_rest(result: _Metrics, event: dict[str, object]) -> None:
    result.rest_calls += 1
    result.rest_nanos += max(0, _integer(event.get("durationNanos")))


def _add_orm(result: _Metrics, event: dict[str, object]) -> None:
    result.orm = True
    result.orm_flushes += _integer(event.get("flushes"))
    result.orm_auto_flushes += _integer(event.get("partialFlushes"))
    entities = _integer(event.get("entitiesInContext"), -1)
    if entities >= 0:
        result.orm_entities_measured = True
        result.orm_max_entities = max(result.orm_max_entities, entities)
    else:
        result.orm_entities_unmeasured = True


_METRIC_ADDITIONS: dict[str, Callable[[_Metrics, dict[str, object]], None]] = {
    "sql": _add_sql,
    "connection": _add_connection,
    "cache": _add_cache,
    "rest-client": _add_rest,
    "orm": _add_orm,
}


def _integer(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _signed(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def _signed_ms(nanos: int) -> str:
    return ("+" if nanos >= 0 else "-") + millis(abs(nanos))


def _shape_diffs(target: _Metrics, baseline: _Metrics) -> list[tuple[str, int, int]]:
    candidates: list[tuple[int, int, int, int, str, int, int]] = []
    for order, (shape, (count, nanos)) in enumerate(target.sql_shapes.items()):
        baseline_count = baseline.sql_shapes.get(shape, [0])[0]
        delta = count - baseline_count
        if delta > 0:
            candidates.append((-int(baseline_count == 0), -delta, -nanos, order, shape, baseline_count, delta))
    candidates.sort()
    return [
        (target.sql_display_shapes[shape], base, delta)
        for _, _, _, _, shape, base, delta in candidates[:MAX_DISTINGUISHING_SQL_SHAPES]
    ]


def _compare(
    slowest: Request, baseline: Request, p50: int, target: _Metrics, base: _Metrics, snapshot: Snapshot
) -> tuple[list[str], list[list[str]]]:
    rows = [
        [
            "Request",
            f"{slowest.request_id} ({slowest.status})",
            f"{baseline.request_id} ({baseline.status})",
            _signed_ms((slowest.duration_nanos or 0) - (baseline.duration_nanos or 0)) + " ms",
        ],
        [
            "Duration (ms)",
            millis(slowest.duration_nanos or 0),
            f"{millis(baseline.duration_nanos or 0)} (warm p50 {millis(p50)})",
            _signed_ms((slowest.duration_nanos or 0) - (baseline.duration_nanos or 0)),
        ],
    ]
    highlights: list[str] = []
    for difference in (_sql_diff, _connection_diff, _cache_diff, _rest_diff, _orm_diff):
        source_highlights, source_rows = difference(target, base, snapshot)
        highlights.extend(source_highlights)
        rows.extend(source_rows)
    return highlights, rows


def _sql_diff(target: _Metrics, base: _Metrics, snapshot: Snapshot) -> tuple[list[str], list[list[str]]]:
    if not snapshot.available("sql") or target.unverified_sql or base.unverified_sql:
        return [], []
    if not (target.sql_executions or base.sql_executions):
        return [], []
    delta, nanos = target.sql_executions - base.sql_executions, target.sql_nanos - base.sql_nanos
    shapes = _shape_diffs(target, base)
    if not (delta or nanos or shapes):
        return [], []
    rows = [
        [
            "SQL executions",
            f"{target.sql_executions} ({millis(target.sql_nanos)} ms)",
            f"{base.sql_executions} ({millis(base.sql_nanos)} ms)",
            f"{_signed(delta)} ({_signed_ms(nanos)} ms)",
        ]
    ]
    rows.extend(
        [["Distinguishing SQL", shape, f"{count} execution(s)", _signed(change)] for shape, count, change in shapes]
    )
    if delta > 0:
        return [f"+{counted(delta, 'SQL execution')} ({_signed_ms(nanos)} ms)"], rows
    if nanos >= 10_000_000:
        return [f"{_signed_ms(nanos)} ms in SQL"], rows
    return ([f"different SQL query shape `{shapes[0][0]}`"] if shapes else []), rows


def _connection_diff(target: _Metrics, base: _Metrics, snapshot: Snapshot) -> tuple[list[str], list[list[str]]]:
    delta = target.connection_wait - base.connection_wait
    if not snapshot.available("connection") or not (target.connection or base.connection) or not delta:
        return [], []
    highlight = [f"{_signed_ms(delta)} ms connection wait"] if delta >= 5_000_000 else []
    row = ["Connection wait (ms)", millis(target.connection_wait), millis(base.connection_wait), _signed_ms(delta)]
    return highlight, [row]


def _cache_diff(target: _Metrics, base: _Metrics, snapshot: Snapshot) -> tuple[list[str], list[list[str]]]:
    miss, hit = target.cache_misses - base.cache_misses, target.cache_hits - base.cache_hits
    if not snapshot.available("cache") or not (target.cache or base.cache) or not (miss or hit):
        return [], []
    row = [
        "Cache (misses / hits)",
        f"{target.cache_misses} / {target.cache_hits}",
        f"{base.cache_misses} / {base.cache_hits}",
        f"{_signed(miss)} misses, {_signed(hit)} hits",
    ]
    return ([f"+{counted(miss, 'cache miss', 'cache misses')}"] if miss > 0 else []), [row]


def _rest_diff(target: _Metrics, base: _Metrics, snapshot: Snapshot) -> tuple[list[str], list[list[str]]]:
    delta, nanos = target.rest_calls - base.rest_calls, target.rest_nanos - base.rest_nanos
    if not snapshot.available("rest-client") or not (target.rest_calls or base.rest_calls) or not (delta or nanos):
        return [], []
    row = [
        "REST client calls",
        f"{target.rest_calls} ({millis(target.rest_nanos)} ms)",
        f"{base.rest_calls} ({millis(base.rest_nanos)} ms)",
        f"{_signed(delta)} ({_signed_ms(nanos)} ms)",
    ]
    if delta > 0:
        highlight = [f"+{counted(delta, 'REST client call')} ({_signed_ms(nanos)} ms)"]
    elif nanos >= 10_000_000:
        highlight = [f"{_signed_ms(nanos)} ms in REST client calls"]
    else:
        highlight = []
    return highlight, [row]


def _orm_diff(target: _Metrics, base: _Metrics, snapshot: Snapshot) -> tuple[list[str], list[list[str]]]:
    if not snapshot.available("orm") or not (target.orm or base.orm):
        return [], []
    highlights: list[str] = []
    rows: list[list[str]] = []
    flushes, auto = target.orm_flushes - base.orm_flushes, target.orm_auto_flushes - base.orm_auto_flushes
    if flushes or auto:
        rows.append(
            [
                "Hibernate (flushes / auto-flushes)",
                f"{target.orm_flushes} / {target.orm_auto_flushes}",
                f"{base.orm_flushes} / {base.orm_auto_flushes}",
                f"{_signed(flushes)} flushes, {_signed(auto)} auto-flushes",
            ]
        )
        if auto > 0:
            highlights.append(f"+{counted(auto, 'auto-flush', 'auto-flushes')}")
        elif flushes > 0:
            highlights.append(f"+{counted(flushes, 'Hibernate flush', 'Hibernate flushes')}")
    if (
        not target.orm_entities_unmeasured
        and not base.orm_entities_unmeasured
        and (target.orm_entities_measured or base.orm_entities_measured)
    ):
        delta = target.orm_max_entities - base.orm_max_entities
        if delta:
            rows.append(
                ["Peak entities in context", str(target.orm_max_entities), str(base.orm_max_entities), _signed(delta)]
            )
            if delta > 0 and not highlights:
                highlights.append(f"+{counted(delta, 'entity', 'entities')} in context")
    return highlights, rows


def _outlier_pair(warm: list[Request]) -> tuple[Request, Request, int, int, int] | None:
    warm_2xx = [r for r in warm if r.status is not None and 200 <= r.status < 300]
    if len(warm_2xx) < MIN_PRELIMINARY_WARM_REQUESTS:
        return None
    p50 = sorted(r.duration_nanos or 0 for r in warm_2xx)[(len(warm_2xx) - 1) // 2]
    threshold = max(p50 * MIN_OUTLIER_MULTIPLIER, p50 + MIN_OUTLIER_DELTA_NANOS)
    slowest = max(enumerate(warm), key=lambda pair: (pair[1].duration_nanos or 0, pair[0]))[1]
    if (slowest.duration_nanos or 0) < threshold:
        return None
    candidates = [r for r in warm_2xx if r is not slowest]
    if not candidates:
        return None
    baseline = min(enumerate(candidates), key=lambda pair: (abs((pair[1].duration_nanos or 0) - p50), -pair[0]))[1]
    return slowest, baseline, p50, threshold, len(warm_2xx)


def evaluate(snapshot: Snapshot) -> Evaluation:
    by_route: dict[str, list[Request]] = defaultdict(list)
    eligible = 0
    for request in project_requests(snapshot, "sql", "connection", "cache", "rest-client", "orm"):
        by_route[request.route].append(request)
    findings: list[Finding] = []
    for route, requests in by_route.items():
        if len(requests) <= 1:
            continue
        warm = requests[1:]
        eligible += len(warm)
        if not (comparison := _outlier_pair(warm)):
            continue
        slowest, baseline, p50, threshold, warm_2xx_count = comparison
        target_metrics, baseline_metrics = _Metrics.of(slowest), _Metrics.of(baseline)
        highlights, rows = _compare(slowest, baseline, p50, target_metrics, baseline_metrics, snapshot)
        if not highlights:
            continue
        limitations: list[str] = []
        if int(snapshot.status.get("evictedEvents", 0)) != 0:
            limitations.append(
                "Events were evicted or cleared, so the route's first retained request may not be its cold first "
                "request in this run."
            )
        if target_metrics.unverified_sql or baseline_metrics.unverified_sql:
            limitations.append("Unverified SQL preparations do not establish JDBC execution counts or database time.")
        sufficient = warm_2xx_count >= MIN_WARM_REQUESTS
        if sufficient:
            sentence = (
                f"On `{route}`, slowest request `{slowest.request_id}` took "
                f"{millis(slowest.duration_nanos or 0)} ms against "
                f"{millis(baseline.duration_nanos or 0)} ms in warm baseline `{baseline.request_id}` "
                f"(warm median {millis(p50)} ms across {counted(warm_2xx_count, 'warm 2xx request')}): "
                f"{', '.join(highlights)}."
            )
        else:
            sentence = (
                f"On `{route}`, request `{slowest.request_id}` took "
                f"{millis(slowest.duration_nanos or 0)} ms against "
                f"{millis(baseline.duration_nanos or 0)} ms in `{baseline.request_id}` ({', '.join(highlights)}), over "
                f"{counted(warm_2xx_count, 'warm 2xx request')}; comparing against a warm baseline "
                f"needs {MIN_WARM_REQUESTS}."
            )
        findings.append(
            Finding(
                route,
                route,
                sufficient,
                sentence,
                len(warm),
                sum((r.duration_nanos or 0) >= threshold for r in warm),
                CHECKS,
                [slowest.request_id, baseline.request_id],
                COLUMNS,
                rows,
                limitations,
            )
        )
    return Evaluation(eligible, findings)
