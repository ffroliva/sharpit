"""Shape conformance with the BootUI 1.17.0 golden captures (spec §12): for every MVP endpoint with a golden
fixture, the recursive key set of sharpit's response equals the golden's, minus the documented deviations below.

Not compared: ``health.json`` (health is a non-goal, spec §14), ``meta.json`` (capture metadata, not an endpoint) and
``mappings.json``, which is the raw Spring Actuator ``GET /mappings`` descriptor that contract §4 drops; the MVP
endpoint ``mappings/flat`` is checked against the contract §4 DTO instead.
"""

from __future__ import annotations

import time
from statistics import median

import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from conftest import FIXTURES, SideEffectGuard, golden
from sharpit import install

LOCAL = ("127.0.0.1", 50000)
ENDPOINTS = {
    "overview": "overview",
    "panels": "panels",
    "config": "config",
    "loggers": "loggers",
    "beans": "beans",
    "vulnerabilities": "vulnerabilities",
}
NOT_COMPARED = {"health", "meta", "mappings"}

# fixture -> {recursive key path: reason}. Paths are excluded from both sides; value-only deviations are listed so
# the record stays complete, and their keys must exist on both sides.
DEVIATIONS: dict[str, dict[str, str]] = {
    "overview": {
        "javaVersion": "value only: the Python version under the contract key (spec §14)",
        "javaVendor": "value only: the Python implementation under the contract key (spec §14)",
        "webApplicationType": "value only: ASGI (spec §14)",
    },
    "panels": {"platform": "value only: fastapi, not spring-boot (spec §14)"},
    "config": {
        "sources": "value only: settings instances, environ and the getenv scan, not Spring property sources (§14)",
        "properties[].defaultValue": "value only: masked like values, Python defaults come from code (spec §7.7)",
    },
    "beans": {
        "beans[].resource": "value only: the defining module, plus overridden_by for a dependency override (§14)",
        "beans[].scope": "value only: request or singleton, FastAPI has no IoC container scopes (spec §14)",
    },
    "vulnerabilities": {
        "scan.scannedAt": "value only: null while NOT_SCANNED (contract §8); the golden's 0 is a capture artefact",
        "scan.vulnerabilitiesFound": "value only: withdrawn OSV advisories are dropped, so finding counts can differ",
        "dependencies[].groupId": "value only: pypi, not Maven group ids (spec §14)",
    },
}


def keys(value: object, prefix: str = "") -> set[str]:
    """Every dotted key path in ``value``; list items share one ``[]`` segment (their keys are unioned)."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found |= {path} | keys(item, path)
    elif isinstance(value, list):
        for item in value:
            found |= keys(item, prefix + "[]")
    return found


def test_keys_is_recursive():
    assert keys({"a": [{"b": 1}, {"c": {"d": None}}], "e": []}) == {"a", "a[].b", "a[].c", "a[].c.d", "e"}


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    app = create_app(show_banner=False, state_dir=str(tmp_path_factory.mktemp("state")))
    return TestClient(app, base_url="http://localhost", client=LOCAL)


def test_every_golden_fixture_is_accounted_for():
    assert {p.stem for p in FIXTURES.glob("*.json")} == set(ENDPOINTS) | NOT_COMPARED
    assert set(DEVIATIONS) <= set(ENDPOINTS)


@pytest.mark.parametrize("name", sorted(ENDPOINTS))
def test_shape_matches_golden(client: TestClient, name: str):
    resp = client.get(f"/sharpit/api/{ENDPOINTS[name]}", params={"limit": 500})
    assert resp.status_code == 200
    ours, theirs = keys(resp.json()), keys(golden(name))
    deviations = set(DEVIATIONS.get(name, {}))
    assert deviations <= ours & theirs, f"value-only deviation keys missing: {deviations - (ours & theirs)}"
    assert ours - deviations == theirs - deviations, {
        "missing": sorted(theirs - ours),
        "extra": sorted(ours - theirs),
    }


def test_documented_value_deviations_hold(client: TestClient):
    scan = client.get("/sharpit/api/vulnerabilities").json()["scan"]
    assert (scan["status"], scan["scannedAt"]) == ("NOT_SCANNED", None)
    assert client.get("/sharpit/api/panels").json()["platform"] == "fastapi"


def test_mappings_flat_matches_contract_dto(client: TestClient):
    # contract §4: MappingsReport { total, mappings: MappingDto[], page: PageMetadata }
    body = client.get("/sharpit/api/mappings/flat").json()
    assert keys(body) == {
        "total",
        "mappings", "mappings[].method", "mappings[].pattern", "mappings[].handler", "mappings[].produces",
        "mappings[].consumes",
        "page", "page.total", "page.matched", "page.offset", "page.limit", "page.returned", "page.hasMore",
    }  # fmt: skip
    assert keys(golden("config")["page"]) == {k.removeprefix("page.") for k in keys(body) if k.startswith("page.")}


def test_install_budget(no_side_effects: SideEffectGuard):
    # install() on the sample app, sockets blocked. The sample is built inactive (its own install() only mounts the 404
    # stub), so the timed call is the full active install on a host with every panel's material in place. Building the
    # host app itself (FastAPI's per-route pydantic schemas) is the host's cost, not install()'s, and is not timed.
    def run() -> float:
        app = create_app(enabled="OFF")
        start = time.perf_counter()
        install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))
        return time.perf_counter() - start

    runs = [run() for _ in range(5)]
    assert median(runs) <= 0.050, [f"{r * 1000:.1f} ms" for r in runs]
    assert no_side_effects.violations == []
