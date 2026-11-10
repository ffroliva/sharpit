"""Panel GET route parity tests against BootUI 2.3.0 live goldens (W3 lane C1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from golden import assert_parity, bootui_ids

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "bootui" / "2.3.0"
_STATUS_FILE = Path(__file__).with_name("routes_23_status.json")

_STATUS_DATA = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
_ROUTES = _STATUS_DATA["routes"]
_ROUTES_BY_GOLDEN = {r["golden"]: r for r in _ROUTES}

_MATCHED = [r for r in _ROUTES if r["status"] == "matched"]
_PARTIAL = [r for r in _ROUTES if r["status"] == "partial"]
_MISSING = [r for r in _ROUTES if r["status"] == "missing"]
_NA = [r for r in _ROUTES if r["status"] == "n-a"]


@pytest.fixture
def client() -> TestClient:
    app = create_app(show_banner=False)
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def _fixture_parts(golden_rel: str) -> tuple[str, str]:
    folder, filename = golden_rel.split("/")
    name = "captured" if filename == "captured.json" else filename.removesuffix(".captured.json")
    ids = bootui_ids("2.3.0")
    sharpit_id = ids.get(folder, folder)
    return sharpit_id, name


def test_every_golden_file_is_classified() -> None:
    golden_files = []
    for p in sorted(_FIXTURES_DIR.rglob("*.json")):
        if p.name in {
            "ids.json",
            "meta.json",
            "panels.json",
            "routes.json",
            "tools.json",
            "rule-ids.json",
            "rule-ids-diff.json",
            "properties.json",
            "bootui-tests.json",
        } or p.name.endswith(".raw.json"):
            continue
        golden_files.append(p.relative_to(_FIXTURES_DIR).as_posix())

    assert len(golden_files) == 96
    classified_goldens = [r["golden"] for r in _ROUTES]
    assert classified_goldens == golden_files
    assert len(classified_goldens) == len(set(classified_goldens))

    counts = _STATUS_DATA["counts"]
    assert counts["matched"] == len(_MATCHED) == 16
    assert counts["partial"] == len(_PARTIAL) == 19
    assert counts["missing"] == len(_MISSING) == 57
    assert counts["n-a"] == len(_NA) == 4
    assert counts["total"] == 96


@pytest.mark.parametrize("item", _MATCHED, ids=lambda r: str(r["golden"]))
def test_matched_routes_pass_23_parity(client: TestClient, item: dict[str, Any]) -> None:
    route = item["route"]
    sharpit_id, name = _fixture_parts(item["golden"])
    response = client.get(route)
    assert response.status_code == 200, f"{route} returned HTTP {response.status_code}"
    payload = response.json()
    assert_parity(sharpit_id, name, payload, fixture_version="2.3.0", matched=True)


@pytest.mark.parametrize("item", _PARTIAL, ids=lambda r: str(r["golden"]))
def test_partial_routes_record_exact_gaps(client: TestClient, item: dict[str, Any]) -> None:
    route = item["route"]
    sharpit_id, name = _fixture_parts(item["golden"])
    response = client.get(route)
    assert response.status_code == 200, f"{route} returned HTTP {response.status_code}"
    payload = response.json()

    with pytest.raises(AssertionError) as exc_info:
        assert_parity(sharpit_id, name, payload, fixture_version="2.3.0", matched=True)

    expected_diff = item["difference"]
    assert expected_diff is not None
    if item["golden"] == "threads/captured.json":
        assert "hiddenBootUiThreads: missing from payload" in str(exc_info.value)
        assert "quality: missing from payload" in str(exc_info.value)
        assert "threads[].cpuTimeMillis: null in payload" in str(exc_info.value)
    else:
        assert str(exc_info.value) == expected_diff


@pytest.mark.parametrize("item", _MISSING, ids=lambda r: str(r["golden"]))
def test_missing_routes_return_404(client: TestClient, item: dict[str, Any]) -> None:
    route = item["route"]
    response = client.get(route)
    assert response.status_code == 404, f"{route} unexpectedly returned HTTP {response.status_code}"


@pytest.mark.parametrize("item", _NA, ids=lambda r: str(r["golden"]))
def test_na_routes_have_empty_list_in_fixture(item: dict[str, Any]) -> None:
    meta = json.loads((_FIXTURES_DIR / "meta.json").read_text(encoding="utf-8"))
    empty_lists = meta.get("emptyLists", {})
    golden = item["golden"]
    assert golden in empty_lists, f"{golden} expected in meta.json emptyLists"
    assert item["difference"] is not None


def test_matched_cases_fail_if_golden_mutated(client: TestClient) -> None:
    response = client.get("/sharpit/api/panels")
    assert response.status_code == 200
    mutated = dict(response.json())
    mutated["panels"] = "not-a-list"
    with pytest.raises(AssertionError) as exc_info:
        assert_parity("panels", "captured", mutated, fixture_version="2.3.0", matched=True)
    assert "payload is string, golden is array" in str(exc_info.value)
