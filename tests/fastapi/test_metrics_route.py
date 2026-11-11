from typing import Any

import prometheus_client
import pytest
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Summary

from fastapi import FastAPI
from sharpit import install


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    registry = CollectorRegistry()
    Gauge("route_metric", "", registry=registry).set(2)
    monkeypatch.setattr(prometheus_client, "REGISTRY", registry)
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False)
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def test_metrics_route_is_available(client: TestClient) -> None:
    response = client.get("/sharpit/api/metrics")
    assert response.status_code == 200
    assert response.json()["meters"][0]["name"] == "route_metric"


def test_metrics_controller_maps_invalid_tag_filter_to_bad_request(client: TestClient) -> None:
    # ported: MetricsControllerTests.malformedTagFilterIsMappedToBadRequest
    response = client.get("/sharpit/api/metrics/detail", params={"name": "route_metric", "tag": "bad"})
    assert response.status_code == 400
    assert response.json() == {"error": "Metric tag filters must use key:value syntax"}


def test_metrics_controller_maps_invalid_limit_to_canonical_bad_request(client: TestClient) -> None:
    # ported: MetricsControllerTests.invalidListLimitIsMappedToCanonicalBadRequest
    response = client.get("/sharpit/api/metrics", params={"limit": "abc"})
    assert response.status_code == 400
    assert response.json() == {"error": "Metric limit must be between 1 and 1000"}


def test_metrics_controller_maps_unknown_provenance_to_bad_request(client: TestClient) -> None:
    # ported: MetricsControllerTests.unknownProvenanceFiltersAreMappedToCanonicalBadRequests
    response = client.get("/sharpit/api/metrics", params={"provenance": "unknown"})
    assert response.status_code == 400
    assert response.json() == {"error": "Metric provenance must be one of: classified, unclassified"}


def test_metrics_controller_requires_detail_name(client: TestClient) -> None:
    # ported: MetricsControllerTests.missingDetailNameIsMappedToCanonicalBadRequest
    response = client.get("/sharpit/api/metrics/detail")
    assert response.status_code == 400
    assert response.json() == {"error": "Metric name must not be blank"}


def test_default_self_filter_hides_sharpit_path_samples(client: TestClient) -> None:
    # ported: MetricsControllerTests.defaultSelfDataFilterHidesBootUiSamples
    response = client.get("/sharpit/api/metrics/detail", params={"name": "route_metric"})
    assert response.status_code == 200
    assert response.json()["totalSamples"] == 1


UNAVAILABLE = "This collector raised an error while collecting; its meters are unavailable."


@pytest.fixture
def private(monkeypatch: pytest.MonkeyPatch) -> tuple[CollectorRegistry, TestClient]:
    from sharpit.engine.collectors.metrics import prometheus

    registry = CollectorRegistry()
    monkeypatch.setattr(prometheus, "REGISTRY", registry)
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), raise_server_exceptions=False)
    return registry, client


def _detail(client: TestClient, name: str) -> dict[str, Any]:
    response = client.get("/sharpit/api/metrics/detail", params={"name": name})
    assert response.status_code == 200
    return response.json()


def test_counter_detail_reports_count_without_created(private: tuple[CollectorRegistry, TestClient]) -> None:
    registry, client = private
    Counter("reqs", "requests", registry=registry).inc(3)
    detail = _detail(client, "reqs")
    assert detail["measurements"] == [{"statistic": "count", "value": 3.0}]
    assert detail["totalSamples"] == 1


def test_histogram_detail_reports_count_and_total_not_buckets(private: tuple[CollectorRegistry, TestClient]) -> None:
    registry, client = private
    Histogram("lat", "", registry=registry).observe(0.2)
    detail = _detail(client, "lat")
    assert detail["measurements"] == [{"statistic": "count", "value": 1.0}, {"statistic": "total", "value": 0.2}]
    assert detail["totalSamples"] == 1


def test_summary_detail_reports_count_and_total(private: tuple[CollectorRegistry, TestClient]) -> None:
    registry, client = private
    summary = Summary("payload", "", ["region"], registry=registry)
    summary.labels("east").observe(2)
    summary.labels("west").observe(3)
    detail = _detail(client, "payload")
    assert detail["measurements"] == [{"statistic": "count", "value": 2.0}, {"statistic": "total", "value": 5.0}]
    assert detail["totalSamples"] == 2


def test_summary_quantiles_stay_samples_outside_the_aggregate(private: tuple[CollectorRegistry, TestClient]) -> None:
    # Micrometer publishes percentiles as their own meters, so BootUI's aggregate never sums them
    from prometheus_client.core import SummaryMetricFamily

    registry, client = private

    class Quantiles:
        def collect(self) -> Any:
            family = SummaryMetricFamily("rpc", "", count_value=2, sum_value=5)
            family.add_sample("rpc", {"quantile": "0.5"}, 2.5)
            yield family

    registry.register(Quantiles())
    detail = _detail(client, "rpc")
    assert detail["measurements"] == [{"statistic": "count", "value": 2.0}, {"statistic": "total", "value": 5.0}]
    assert detail["samples"][1] == {
        "tags": [{"key": "quantile", "value": "0.5"}],
        "measurements": [{"statistic": "value", "value": 2.5}],
    }


def test_label_values_are_masked_by_their_key(private: tuple[CollectorRegistry, TestClient]) -> None:
    registry, client = private
    Gauge("creds", "", ["password", "token", "api_key"], registry=registry).labels("hunter2", "tok3n", "k3y").set(1)
    text = client.get("/sharpit/api/metrics").text + client.get("/sharpit/api/metrics/detail?name=creds").text
    assert "hunter2" not in text
    assert "tok3n" not in text
    assert "k3y" not in text


class _Raises:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def collect(self) -> Any:
        raise self.exc


@pytest.mark.parametrize("path", ["/sharpit/api/metrics", "/sharpit/api/metrics/detail?name=ok"])
def test_host_value_error_is_not_echoed(private: tuple[CollectorRegistry, TestClient], path: str) -> None:
    registry, client = private
    Gauge("ok", "", registry=registry).set(1)
    registry.register(_Raises(ValueError("cannot reach postgres://app:S3cretPw@db/x")))
    response = client.get(path)
    assert response.status_code == 200
    assert "S3cretPw" not in response.text


def test_host_collector_error_marks_it_unavailable(private: tuple[CollectorRegistry, TestClient]) -> None:
    registry, client = private
    Gauge("ok", "", registry=registry).set(1)
    registry.register(_Raises(RuntimeError("boom S3cretPw")))
    response = client.get("/sharpit/api/metrics")
    assert response.status_code == 200
    meters = {m["name"]: m["description"] for m in response.json()["meters"]}
    assert meters == {"_Raises": UNAVAILABLE, "ok": None}


@pytest.mark.parametrize("via", ["mcp", "cli"])
def test_tool_survives_a_raising_collector(private: tuple[CollectorRegistry, TestClient], via: str) -> None:
    from sharpit.engine.tools import CallContext, call_tool

    registry, _client = private
    registry.register(_Raises(ValueError("cannot reach postgres://app:S3cretPw@db/x")))
    ctx = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False).context
    try:
        result = call_tool(CallContext(ctx, {}), "get_metrics", {}, via=via)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 - the unfixed tool lets the host error escape as an RPC error
        result = {"meters": [], "escaped": repr(exc)}
    assert [m["description"] for m in result["meters"]] == [UNAVAILABLE]
    assert "S3cretPw" not in str(result)
