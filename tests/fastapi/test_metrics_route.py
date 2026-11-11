import prometheus_client
import pytest
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, Gauge

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
