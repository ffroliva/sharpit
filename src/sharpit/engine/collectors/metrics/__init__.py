"""Read-only view of the host's already-imported Prometheus registry.

Collection runs host collector code on request, matching BootUI's registry read.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from sharpit.engine.collectors.metrics.prometheus import registry

DEFAULT_LIMIT = 200
DEFAULT_SAMPLE_LIMIT = 100
MAX_LIMIT = 1000
MAX_TAG_VALUES = 100
_TYPES = ("COUNTER", "DISTRIBUTION_SUMMARY", "GAUGE", "LONG_TASK_TIMER", "OTHER", "TIMER")


def _mask(ctx: Any, value: object) -> str | None:
    return ctx.masker.mask_text(value) if isinstance(value, str) else None


def _type(value: str) -> str:
    return {
        "counter": "COUNTER",
        "gauge": "GAUGE",
        "histogram": "DISTRIBUTION_SUMMARY",
        "summary": "DISTRIBUTION_SUMMARY",
    }.get(value, "OTHER")


def _families(ctx: Any) -> list[dict[str, Any]]:
    source = registry()
    if source is None:
        return []
    families: list[dict[str, Any]] = []
    for family in source.collect():
        labels: dict[str, set[str]] = defaultdict(set)
        samples: list[dict[str, Any]] = []
        self_only = bool(family.samples)
        for sample in family.samples:
            tags: dict[str, str] = {str(k): _mask(ctx, str(v)) or "" for k, v in sample.labels.items()}
            if any(k == "path" and v.startswith(ctx.settings.path) for k, v in tags.items()):
                continue
            self_only = False
            for key, value in tags.items():
                labels[key].add(value)
            try:
                value = float(sample.value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                samples.append(
                    {
                        "tags": [{"key": k, "value": v} for k, v in sorted(tags.items())],
                        "measurements": [{"statistic": "VALUE", "value": value}],
                    }
                )
        if self_only:
            continue
        help_text = _mask(ctx, family.documentation) or None
        samples.sort(key=lambda sample: tuple((tag["key"], tag["value"]) for tag in sample["tags"]))
        families.append(
            {
                "name": str(family.name),
                "description": help_text,
                "baseUnit": getattr(family, "unit", None) or None,
                "type": _type(str(family.type)),
                "tags": labels,
                "samples": samples,
            }
        )
    return sorted(families, key=lambda x: x["name"])


def _page(offset: str | None, limit: str | None, default: int) -> tuple[int, int]:
    try:
        start = 0 if offset is None else int(offset.strip())
    except ValueError:
        start = -1
    if start < 0:
        raise ValueError("Metric offset must be 0 or greater")
    try:
        size = default if limit is None else int(limit.strip())
    except ValueError:
        size = 0
    if not 1 <= size <= MAX_LIMIT:
        raise ValueError("Metric limit must be between 1 and 1000")
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
        raise ValueError("Metric type must be one of: " + ", ".join(_TYPES))
    requested_group = group.strip().lower() if group else ""
    if requested_group and requested_group != "application":
        raise ValueError("Metric group must be one of: application")
    if provenance and provenance.strip().lower() not in {"classified", "unclassified"}:
        raise ValueError("Metric provenance must be one of: classified, unclassified")
    requested_explanation = explanation.strip().upper() if explanation else ""
    if requested_explanation and requested_explanation not in {"CURATED", "NATIVE", "UNKNOWN"}:
        raise ValueError("Metric explanation source must be one of: CURATED, NATIVE, UNKNOWN")
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
            "availableTags": [
                {"key": k, "values": sorted(v)[:MAX_TAG_VALUES], "truncated": len(v) > MAX_TAG_VALUES}
                for k, v in sorted(m["tags"].items())
            ],
            "provenance": {
                "groupId": "application",
                "groupLabel": "Application / unclassified",
                "contributor": "Application or unrecognized instrumentation",
                "familyId": None,
                "familyLabel": None,
                "classified": False,
                "explanation": m["description"],
                "explanationSource": "NATIVE" if m["description"] else "UNKNOWN",
                "interpretation": None,
            },
        }
        for m in matching
    ]
    common_tags: set[str] = set(matching[0]["tags"]) if matching else set()
    for meter in matching[1:]:
        common_tags.intersection_update(meter["tags"])
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
                "commonTagKeys": sorted(common_tags),
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
        raise ValueError("Metric name must not be blank")
    required: dict[str, str] = {}
    for item in tag_filters or []:
        key, sep, value = item.partition(":")
        if not sep or not key.strip():
            raise ValueError("Metric tag filters must use key:value syntax")
        required[key] = ctx.masker.mask_text(value) or ""
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
    measurements = (
        [{"statistic": "VALUE", "value": sum(s["measurements"][0]["value"] for s in samples)}] if samples else []
    )
    page = samples[start : start + size]
    return {
        "metricsAvailable": registry() is not None,
        "name": meter["name"],
        "description": meter["description"],
        "baseUnit": meter["baseUnit"],
        "type": meter["type"],
        "measurements": measurements,
        "availableTags": [
            {"key": k, "values": sorted(v)[:MAX_TAG_VALUES], "truncated": len(v) > MAX_TAG_VALUES}
            for k, v in sorted(meter["tags"].items())
        ],
        "samples": page,
        "totalSamples": len(samples),
        "samplePage": _metadata(len(samples), len(samples), start, size, len(page)),
        "samplesTruncated": start > 0 or start + len(page) < len(samples),
        "provenance": {
            "groupId": "application",
            "groupLabel": "Application / unclassified",
            "contributor": "Application or unrecognized instrumentation",
            "familyId": None,
            "familyLabel": None,
            "classified": False,
            "explanation": meter["description"],
            "explanationSource": "NATIVE" if meter["description"] else "UNKNOWN",
            "interpretation": None,
        },
    }
