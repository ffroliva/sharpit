from __future__ import annotations

import math
import sys
from typing import Any

import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Summary

from sharpit.engine.collectors.metrics import metric_detail, metrics_report, prometheus


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> CollectorRegistry:
    value = CollectorRegistry()
    monkeypatch.setattr(prometheus, "REGISTRY", value)
    return value


def _ctx() -> Any:
    from fastapi import FastAPI
    from sharpit import install

    app = FastAPI()
    return install(app, enabled="ON", show_banner=False, config_scan=False).context


def test_metrics_groups_names_and_aggregates_label_values(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.metricsGroupsMetersByNameAndAggregatesTagValues
    Gauge("queue_depth", "queued work", ["region"], registry=registry).labels("west").set(2)
    result = metrics_report(_ctx())
    assert result["total"] == 1
    assert result["meters"][0]["availableTags"][0]["values"] == ["west"]


def test_prometheus_family_types_map_to_micrometer_names(registry: CollectorRegistry) -> None:
    Counter("requests", "", registry=registry).inc()
    Histogram("latency", "", registry=registry).observe(0.2)
    Summary("payload", "", registry=registry).observe(2)
    types = {meter["name"]: meter["type"] for meter in metrics_report(_ctx())["meters"]}
    assert types == {"latency": "DISTRIBUTION_SUMMARY", "payload": "DISTRIBUTION_SUMMARY", "requests": "COUNTER"}


def test_metrics_filters_pages_in_name_order(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.metricsFiltersAndPagesInDeterministicNameOrder
    Gauge("z_depth", "", registry=registry).set(1)
    Gauge("a_depth", "", registry=registry).set(2)
    result = metrics_report(_ctx(), offset="1", limit="1")
    assert result["meters"][0]["name"] == "z_depth"
    assert result["page"]["hasMore"] is False


def test_metrics_bounded_defaults_and_rejects_invalid_paging(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.metricsUsesBoundedDefaultsAndRejectsInvalidPaging
    Gauge("depth", "", registry=registry).set(1)
    assert metrics_report(_ctx())["page"]["limit"] == 200
    with pytest.raises(ValueError, match="Metric limit must be between 1 and 1000"):
        metrics_report(_ctx(), limit="1001")


def test_detail_filters_tags_and_aggregates_finite_measurements(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.detailFiltersByTagsAndAggregatesFiniteMeasurements
    gauge = Gauge("queue_depth", "", registry=registry, labelnames=["region"])
    gauge.labels("east").set(2)
    gauge.labels("west").set(5)
    gauge.labels("north").set(math.nan)
    gauge.labels("south").set(math.inf)
    result = metric_detail(_ctx(), "queue_depth", ["region:west"])
    assert result["totalSamples"] == 1
    assert result["measurements"] == [{"statistic": "value", "value": 5.0}]
    every = metric_detail(_ctx(), "queue_depth")
    assert every["totalSamples"] == 4
    assert every["measurements"] == [{"statistic": "value", "value": 7.0}]


def test_detail_bounds_tag_values(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.detailBoundsTagValuesWhileRetainingDeterministicValues
    gauge = Gauge("tag_values", "", registry=registry, labelnames=["value"])
    for value in range(105):
        gauge.labels(str(value)).set(value)
    tag = metric_detail(_ctx(), "tag_values")["availableTags"][0]
    assert len(tag["values"]) == 100
    assert tag["truncated"] is True


def test_detail_accepts_colon_in_tag_values(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.detailAcceptsColonInTagValues
    Gauge("tag_value", "", registry=registry, labelnames=["url"]).labels("http://x").set(1)
    assert metric_detail(_ctx(), "tag_value", ["url:http://x"])["totalSamples"] == 1


def test_detail_rejects_malformed_tag_filters(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.detailRejectsMalformedTagFilters
    with pytest.raises(ValueError, match="Metric tag filters must use key:value syntax"):
        metric_detail(_ctx(), "x", ["bad"])


def test_detail_rejects_blank_name_and_invalid_paging(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.detailRejectsBlankNameAndInvalidPaging
    with pytest.raises(ValueError, match="Metric name must not be blank"):
        metric_detail(_ctx(), " ")
    with pytest.raises(ValueError, match="Metric offset must be 0 or greater"):
        metric_detail(_ctx(), "x", offset="-1")


def test_metrics_unavailable_without_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: MetricsReportProviderTests.metricsReportUnavailableWhenNoRegistry
    monkeypatch.setattr(prometheus, "REGISTRY", None)
    monkeypatch.setattr(prometheus, "modules", {})
    report = metrics_report(_ctx())
    assert report["metricsAvailable"] is False
    assert report["catalogueVersion"] is None


def test_detail_unavailable_without_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: MetricsReportProviderTests.detailUnavailableWhenNoRegistry
    monkeypatch.setattr(prometheus, "REGISTRY", None)
    monkeypatch.setattr(prometheus, "modules", {})
    assert metric_detail(_ctx(), "x")["metricsAvailable"] is False


def test_metrics_rejects_unknown_provenance_filter(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.metricsRejectsUnknownProvenanceFiltersCanonically
    with pytest.raises(ValueError, match="Metric provenance must be one of: classified, unclassified"):
        metrics_report(_ctx(), provenance="invented")


def test_metrics_groups_cover_all_matching_names(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.metricsGroupsCoverEveryMatchingMeterEvenWhenThePageIsTruncated
    Gauge("a", "", registry=registry).set(1)
    Gauge("b", "", registry=registry).set(1)
    result = metrics_report(_ctx(), limit="1")
    assert result["groups"][0]["meterCount"] == 2


def test_group_summaries_stay_bounded_for_high_cardinality(registry: CollectorRegistry) -> None:
    # ported: MetricsReportProviderTests.groupSummariesStayBoundedForHighCardinalityRegistries
    gauge = Gauge("many", "", registry=registry, labelnames=["id"])
    for value in range(500):
        gauge.labels(str(value)).set(value)
    report = metrics_report(_ctx())
    assert len(report["meters"][0]["availableTags"][0]["values"]) == 100


def test_unavailable_registry_has_empty_catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: MetricsReportProviderTests.unavailableRegistryReportsAnEmptyCatalogueRatherThanGuessing
    monkeypatch.setattr(prometheus, "REGISTRY", None)
    monkeypatch.setattr(prometheus, "modules", {})
    assert metrics_report(_ctx())["groups"] == []


def test_metric_label_values_are_masked_before_filtering(registry: CollectorRegistry) -> None:
    Gauge("metric_name", "", registry=registry, labelnames=["url"]).labels("https://user:secret@example.test").set(1)
    ctx = _ctx()
    report = metrics_report(ctx, query="secret")
    assert report["page"]["matched"] == 0
    assert "secret" not in str(metrics_report(ctx))


def test_metrics_masks_help_before_filtering(registry: CollectorRegistry) -> None:
    Gauge("help_metric", "dsn https://user:secret@example.test", registry=registry).set(1)
    report = metrics_report(_ctx(), query="secret")
    assert report["page"]["matched"] == 0
    assert "secret" not in str(metrics_report(_ctx()))


def test_metrics_self_filter_uses_path_tag_only(registry: CollectorRegistry) -> None:
    # ported: MeterSelfFilterTests.recognizesMetersByPathTagOnly
    # ported: MeterSelfFilterTests.ignoresBootUiLookingValuesOnNonPathTags
    requests = Gauge("http_requests", "", registry=registry, labelnames=["path", "http_route", "uri"])
    requests.labels("/orders", "/orders", "/orders").set(1)
    requests.labels("/sharpit/api/metrics", "/x", "/x").set(1)
    requests.labels("/x", "/sharpit", "/x").set(1)
    requests.labels("/x", "/x", "http://localhost/sharpit/api/env").set(1)
    requests.labels("/sharpitfoo/x", "/x", "/x").set(1)
    Gauge("normal_route", "", registry=registry, labelnames=["route"]).labels("/sharpit/api/metrics").set(1)
    ctx = _ctx()
    assert [m["name"] for m in metrics_report(ctx)["meters"]] == ["http_requests", "normal_route"]
    paths = [{t["key"]: t["value"] for t in s["tags"]}["path"] for s in metric_detail(ctx, "http_requests")["samples"]]
    assert paths == ["/orders", "/sharpitfoo/x"]


def test_metrics_common_tag_keys_are_carried_by_half_the_meters(registry: CollectorRegistry) -> None:
    # BootUI MetricsReportProvider.commonTagKeys: at least half of the group's meters
    Gauge("a", "", ["region"], registry=registry).labels("w").set(1)
    Gauge("b", "", ["region", "pool"], registry=registry).labels("w", "p").set(1)
    Gauge("c", "", registry=registry).set(1)
    assert metrics_report(_ctx())["groups"][0]["commonTagKeys"] == ["region"]


def test_labelled_family_without_children_is_not_listed(registry: CollectorRegistry) -> None:
    Counter("idle", "", ["route"], registry=registry)
    Gauge("busy", "", registry=registry).set(1)
    assert [m["name"] for m in metrics_report(_ctx())["meters"]] == ["busy"]


def test_metrics_reads_otel_prometheus_collector_without_import(registry: CollectorRegistry) -> None:
    before = set(sys.modules)

    class OTelPrometheusCollector:
        def collect(self):
            from prometheus_client.core import GaugeMetricFamily

            family = GaugeMetricFamily("otel_exported", "from collector")
            family.add_metric([], 1)
            yield family

    registry.register(OTelPrometheusCollector())
    assert any(m["name"] == "otel_exported" for m in metrics_report(_ctx())["meters"])
    assert not {
        name for name in set(sys.modules) - before if name == "opentelemetry" or name.startswith("opentelemetry.")
    }


def test_metrics_golden_shape_23(registry: CollectorRegistry) -> None:
    Gauge("golden", "help", registry=registry).set(1)
    report = metrics_report(_ctx())
    assert set(report) == {
        "metricsAvailable",
        "total",
        "meters",
        "availableTypes",
        "page",
        "groups",
        "catalogueVersion",
    }
    assert set(report["meters"][0]) == {"name", "description", "baseUnit", "type", "availableTags", "provenance"}
    detail = metric_detail(_ctx(), "golden")
    assert set(detail) == {
        "metricsAvailable",
        "name",
        "description",
        "baseUnit",
        "type",
        "measurements",
        "availableTags",
        "samples",
        "totalSamples",
        "samplePage",
        "samplesTruncated",
        "provenance",
    }
