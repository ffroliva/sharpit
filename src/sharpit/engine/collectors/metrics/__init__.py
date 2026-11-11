"""Read-only view of the host's already-imported Prometheus registry.

A read runs every host collector once, as Micrometer function gauges do when BootUI reads its registry. There is no
family or sample cap: the host's own ``collect()`` is the cost, and a cap after it bounds nothing; responses are paged.
"""

from __future__ import annotations

import contextlib
import math
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlsplit

from sharpit.engine.collectors.metrics.prometheus import registry

DEFAULT_LIMIT = 200
DEFAULT_SAMPLE_LIMIT = 100
MAX_LIMIT = 1000
MAX_TAG_VALUES = 100
MAX_COMMON_TAG_KEYS = 8
_TYPES = ("COUNTER", "DISTRIBUTION_SUMMARY", "GAUGE", "LONG_TASK_TIMER", "OTHER", "TIMER")
UNAVAILABLE = "This collector raised an error while collecting; its meters are unavailable."
# BootUI SelfTelemetryClassifier.PATH_TAG_KEYS, their Prometheus spellings, and prometheus-fastapi-instrumentator's
_PATH_KEYS = frozenset(
    {"uri", "path", "endpoint", "http.route", "http.target", "http.path", "http.url", "url.path", "url.full"}
    | {"http_route", "http_target", "http_path", "http_url", "url_path", "url_full", "handler"}
)
# Prometheus sample suffix -> Micrometer Statistic tag value; any other suffix is a value
_STATISTICS = {"_total": "count", "_count": "count", "_gcount": "count", "_sum": "total", "_gsum": "total"}
_DROPPED = frozenset({"_created", "_bucket"})  # a creation epoch and cumulative buckets are not BootUI statistics
_CLOSING = frozenset("/?#])},'\"")


class MetricsRequestError(ValueError):
    """A request input BootUI answers with 400 ``{"error": message}``; nothing else becomes a 400."""


def _label(ctx: Any, key: str, value: object) -> str:
    shown, _masked = ctx.masker.mask(key, value)
    return (ctx.masker.mask_text(shown) or "") if isinstance(shown, str) else ""


def _type(value: str) -> str:
    return {
        "counter": "COUNTER",
        "gauge": "GAUGE",
        "histogram": "DISTRIBUTION_SUMMARY",
        "summary": "DISTRIBUTION_SUMMARY",
    }.get(value, "OTHER")


def _contains_path(value: str, path: str) -> bool:
    """BootUI ``containsPathWithBoundaries``: ``path`` in ``value`` with a path boundary on both sides."""
    index = value.find(path)
    while index >= 0:
        before = value[index - 1] if index else ""
        after = value[index + len(path) : index + len(path) + 1]
        if not (before.isalnum() or before in {"_", "-", "."}) and (not after or after in _CLOSING or after.isspace()):
            return True
        index = value.find(path, index + 1)
    return False


def _is_self_path(value: str, path: str) -> bool:
    """BootUI ``isBootUiPath``: the mount at a path boundary, in the value's URL path or the value itself."""
    candidate = value.strip()
    if "://" in candidate:
        with contextlib.suppress(ValueError):
            if _contains_path(urlsplit(candidate).path, path):
                return True
    return bool(candidate) and _contains_path(candidate, path)


def _is_self(ctx: Any, labels: dict[str, str]) -> bool:
    path = ctx.settings.path.rstrip("/")  # api_path is under path, so the mount covers both
    return bool(path) and any(k in _PATH_KEYS and _is_self_path(v, path) for k, v in labels.items())


def _statistic(family: str, sample: str) -> str | None:
    suffix = sample[len(family) :] if sample.startswith(family) else ""
    return None if suffix in _DROPPED else _STATISTICS.get(suffix, "value")


def _finite(value: object) -> float | None:
    try:
        number = float(value)  # pyright: ignore[reportArgumentType]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _unavailable(ctx: Any, collector: object) -> dict[str, Any]:
    name = ctx.masker.mask_text(type(collector).__name__) or ""
    return {"name": name, "description": UNAVAILABLE, "baseUnit": None, "type": "OTHER", "tags": {}, "samples": []}


def _sample(ctx: Any, raw: tuple[tuple[str, str], ...], values: dict[str, float]) -> dict[str, Any]:
    return {
        "tags": [{"key": k, "value": _label(ctx, k, v)} for k, v in raw],
        "measurements": [{"statistic": k, "value": values[k]} for k in sorted(values)],
    }


def _family(ctx: Any, family: Any) -> dict[str, Any] | None:
    """One meter per family and one sample per label set, as BootUI's meter per tag set; ``None`` when none is left."""
    series: dict[tuple[tuple[str, str], ...], dict[str, float]] = {}
    for sample in family.samples:
        statistic = _statistic(str(family.name), str(sample.name))
        labels = {str(k): str(v) for k, v in sample.labels.items()}
        if statistic is None or _is_self(ctx, labels):
            continue
        values = series.setdefault(tuple(sorted(labels.items())), {})
        value = _finite(sample.value)
        if value is not None:
            values[statistic] = value
    if not series:
        return None
    samples = sorted(
        (_sample(ctx, raw, values) for raw, values in series.items()),
        key=lambda sample: tuple((tag["key"], tag["value"]) for tag in sample["tags"]),
    )
    tags: dict[str, set[str]] = defaultdict(set)
    for sample in samples:
        for tag in sample["tags"]:
            tags[tag["key"]].add(tag["value"])
    documentation = family.documentation
    return {
        "name": str(family.name),
        "description": (ctx.masker.mask_text(documentation) or None) if isinstance(documentation, str) else None,
        "baseUnit": getattr(family, "unit", None) or None,
        "type": _type(str(family.type)),
        "tags": tags,
        "samples": samples,
    }


def _families(ctx: Any) -> list[dict[str, Any]]:
    """Each host collector on its own: one that raises, or yields a malformed family, never hides the others."""
    source = registry()
    if source is None:
        return []
    # prometheus_client internals; any other registry is read as one collector. target_info is not shown.
    collectors: Any = getattr(source, "_collector_to_names", None)
    candidates: list[Any] = list(collectors) if isinstance(collectors, dict) else [source]  # pyright: ignore[reportUnknownArgumentType]
    families: list[dict[str, Any]] = []
    for collector in candidates:
        try:
            found = [meter for meter in (_family(ctx, family) for family in collector.collect()) if meter is not None]
        except Exception:  # noqa: BLE001 - host code; its message is never shown (it may carry a DSN)
            found = [_unavailable(ctx, collector)]
        families.extend(found)
    return sorted(families, key=lambda x: x["name"])


def _aggregate(meter: dict[str, Any], samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """BootUI ``aggregateMeasurements``: finite values summed per statistic.

    Micrometer keeps a summary's percentiles as meters of their own, so quantile samples are not summed in.
    """
    totals: dict[str, float] = {}
    for sample in samples:
        if meter["type"] == "DISTRIBUTION_SUMMARY" and any(tag["key"] == "quantile" for tag in sample["tags"]):
            continue
        for measurement in sample["measurements"]:
            totals[measurement["statistic"]] = totals.get(measurement["statistic"], 0.0) + measurement["value"]
    return [{"statistic": k, "value": v} for k, v in sorted(totals.items())]


def _provenance(description: str | None) -> dict[str, Any]:
    return {
        "groupId": "application",
        "groupLabel": "Application / unclassified",
        "contributor": "Application or unrecognized instrumentation",
        "familyId": None,
        "familyLabel": None,
        "classified": False,
        "explanation": description,
        "explanationSource": "NATIVE" if description else "UNKNOWN",
        "interpretation": None,
    }


def _common_tag_keys(meters: list[dict[str, Any]]) -> list[str]:
    """BootUI ``commonTagKeys``: keys on at least half the meters, most common first, then alphabetical."""
    counts = Counter(key for meter in meters for key in meter["tags"])
    threshold = max(1, (len(meters) + 1) // 2)
    return sorted((k for k, n in counts.items() if n >= threshold), key=lambda k: (-counts[k], k))[:MAX_COMMON_TAG_KEYS]


def _available_tags(tags: dict[str, set[str]]) -> list[dict[str, Any]]:
    return [
        {"key": k, "values": sorted(v)[:MAX_TAG_VALUES], "truncated": len(v) > MAX_TAG_VALUES}
        for k, v in sorted(tags.items())
    ]


def _page(offset: str | None, limit: str | None, default: int) -> tuple[int, int]:
    try:
        start = 0 if offset is None else int(offset.strip())
    except ValueError:
        start = -1
    if start < 0:
        raise MetricsRequestError("Metric offset must be 0 or greater")
    try:
        size = default if limit is None else int(limit.strip())
    except ValueError:
        size = 0
    if not 1 <= size <= MAX_LIMIT:
        raise MetricsRequestError("Metric limit must be between 1 and 1000")
    return start, size


def _metadata(total: int, matched: int, offset: int, limit: int, returned: int) -> dict[str, Any]:
    return {
        "total": total,
        "matched": matched,
        "offset": offset,
        "limit": limit,
        "returned": returned,
        "hasMore": offset + returned < matched,
    }


def metrics_report(
    ctx: Any,
    query: str | None = None,
    type: str | None = None,
    group: str | None = None,
    provenance: str | None = None,
    explanation: str | None = None,
    offset: str | None = None,
    limit: str | None = None,
) -> dict[str, Any]:
    start, size = _page(offset, limit, DEFAULT_LIMIT)
    requested_type = type.strip().upper() if type else ""
    if requested_type and requested_type not in _TYPES:
        raise MetricsRequestError("Metric type must be one of: " + ", ".join(_TYPES))
    requested_group = group.strip().lower() if group else ""
    if requested_group and requested_group != "application":
        raise MetricsRequestError("Metric group must be one of: application")
    if provenance and provenance.strip().lower() not in {"classified", "unclassified"}:
        raise MetricsRequestError("Metric provenance must be one of: classified, unclassified")
    requested_explanation = explanation.strip().upper() if explanation else ""
    if requested_explanation and requested_explanation not in {"CURATED", "NATIVE", "UNKNOWN"}:
        raise MetricsRequestError("Metric explanation source must be one of: CURATED, NATIVE, UNKNOWN")
    items = _families(ctx)
    available = registry() is not None
    q = query.strip().lower() if query else ""
    matching = [
        m
        for m in items
        if (not q or q in m["name"].lower() or q in (m["description"] or "").lower())
        and (not requested_type or requested_type == m["type"])
        and (not provenance or provenance.strip().lower() == "unclassified")
        and (not requested_explanation or requested_explanation == ("NATIVE" if m["description"] else "UNKNOWN"))
    ]
    names = [
        {
            "name": m["name"],
            "description": m["description"],
            "baseUnit": m["baseUnit"],
            "type": m["type"],
            "availableTags": _available_tags(m["tags"]),
            "provenance": _provenance(m["description"]),
        }
        for m in matching
    ]
    groups = (
        []
        if not matching
        else [
            {
                "id": "application",
                "label": "Application / unclassified",
                "contributor": "Application or unrecognized instrumentation",
                "summary": "Meters whose names match no known integration convention.",
                "interpretation": None,
                "meterCount": len(matching),
                "describedMeterCount": sum(m["description"] is not None for m in matching),
                "families": [],
                "commonTagKeys": _common_tag_keys(matching),
                "baseUnits": sorted({m["baseUnit"] for m in matching if m["baseUnit"]}),
            }
        ]
    )
    return {
        "metricsAvailable": available,
        "total": len(items),
        "meters": names[start : start + size],
        "availableTypes": sorted({m["type"] for m in items}),
        "page": _metadata(len(items), len(matching), start, size, len(names[start : start + size])),
        "groups": groups,
        "catalogueVersion": None,
    }


def metric_detail(
    ctx: Any,
    name: str | None,
    tag_filters: list[str] | None = None,
    offset: str | None = None,
    limit: str | None = None,
) -> dict[str, Any]:
    if name is None or not name.strip():
        raise MetricsRequestError("Metric name must not be blank")
    required: dict[str, str] = {}
    for item in tag_filters or []:
        key, sep, value = item.partition(":")
        if not sep or not key.strip():
            raise MetricsRequestError("Metric tag filters must use key:value syntax")
        required[key] = _label(ctx, key, value)
    start, size = _page(offset, limit, DEFAULT_SAMPLE_LIMIT)
    meter = next((m for m in _families(ctx) if m["name"] == name.strip()), None)
    if meter is None:
        return {
            "metricsAvailable": registry() is not None,
            "name": name.strip(),
            "description": None,
            "baseUnit": None,
            "type": None,
            "measurements": [],
            "availableTags": [],
            "samples": [],
            "totalSamples": 0,
            "samplePage": _metadata(0, 0, start, size, 0),
            "samplesTruncated": False,
            "provenance": None,
        }
    samples = [
        s
        for s in meter["samples"]
        if all({t["key"]: t["value"] for t in s["tags"]}.get(k) == v for k, v in required.items())
    ]
    page = samples[start : start + size]
    return {
        "metricsAvailable": registry() is not None,
        "name": meter["name"],
        "description": meter["description"],
        "baseUnit": meter["baseUnit"],
        "type": meter["type"],
        "measurements": _aggregate(meter, samples),
        "availableTags": _available_tags(meter["tags"]),
        "samples": page,
        "totalSamples": len(samples),
        "samplePage": _metadata(len(samples), len(samples), start, size, len(page)),
        "samplesTruncated": start > 0 or start + len(page) < len(samples),
        "provenance": _provenance(meter["description"]),
    }
