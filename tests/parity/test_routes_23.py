"""Panel GET route parity tests against BootUI 2.3.0 live goldens (W3 lane C1)."""

from __future__ import annotations

import ast
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

pytestmark = [
    pytest.mark.bootui("route:GET /loggers"),
    pytest.mark.bootui("route:GET /mappings/flat"),
    pytest.mark.bootui("route:GET /mcp-server"),
    pytest.mark.bootui("route:GET /panels"),
]


def _empty_list_paths(value: Any, path: str = "") -> set[str]:
    if isinstance(value, list):
        return {path} if not value else set().union(*(_empty_list_paths(item, f"{path}[]") for item in value))
    if isinstance(value, dict):
        return set().union(*(_empty_list_paths(item, f"{path}.{key}" if path else key) for key, item in value.items()))
    return set()


def _canonical_difference(value: str) -> str:
    prefix, difference = value.split(" parity: ", maxsplit=1)
    # The thread endpoint reflects xdist's live worker threads, so repeated row gaps vary in count.
    return prefix + " parity: " + "; ".join(sorted(set(difference.split("; "))))


def test_no_matched_golden_contains_an_empty_list() -> None:
    empty_lists = json.loads((_FIXTURES_DIR / "meta.json").read_text(encoding="utf-8")).get("emptyLists", {})
    with_empty_lists = [
        item["golden"]
        for item in _MATCHED
        if _empty_list_paths(json.loads((_FIXTURES_DIR / item["golden"]).read_text(encoding="utf-8")))
        or item["golden"] in empty_lists
    ]
    assert not with_empty_lists, f"matched rows have shapeless empty-list goldens: {with_empty_lists}"


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

    counts = {
        status: sum(item["status"] == status for item in _ROUTES) for status in ("matched", "partial", "missing", "n-a")
    }
    assert _STATUS_DATA["counts"] == {**counts, "total": len(_ROUTES)}
    assert len(_ROUTES) == 96


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
    actual_diff = str(exc_info.value)
    if item["golden"] == "threads/captured.json":
        assert _canonical_difference(actual_diff) == _canonical_difference(expected_diff)
    else:
        assert actual_diff == expected_diff


def test_error_contract_records_its_bootui_23_parity_gap(client: TestClient) -> None:
    response = client.get("/sharpit/api/rest-api/error-contract")
    assert response.status_code == 200
    with pytest.raises(AssertionError) as exc_info:
        assert_parity(
            "rest-api",
            "error-contract",
            response.json(),
            fixture_version="2.3.0",
            matched=True,
        )
    assert str(exc_info.value) == (
        "rest-api/error-contract.captured.json parity: entries: non-empty golden list requires a non-empty payload list"
    )


@pytest.mark.parametrize("item", _MISSING, ids=lambda r: str(r["golden"]))
def test_missing_routes_return_404(client: TestClient, item: dict[str, Any]) -> None:
    route = item["route"]
    assert route not in {getattr(r, "path", "") for r in client.app.routes}
    response = client.get(route)
    assert response.status_code == 404, f"{route} unexpectedly returned HTTP {response.status_code}"


@pytest.mark.parametrize("item", _NA, ids=lambda r: str(r["golden"]))
def test_na_routes_have_empty_list_in_fixture(item: dict[str, Any]) -> None:
    meta = json.loads((_FIXTURES_DIR / "meta.json").read_text(encoding="utf-8"))
    empty_lists = meta.get("emptyLists", {})
    golden = item["golden"]
    fixture = json.loads((_FIXTURES_DIR / golden).read_text(encoding="utf-8"))
    actual_empty_paths = _empty_list_paths(fixture)
    assert actual_empty_paths, f"{golden} contains no empty list"
    assert item["status"] == "n-a"
    recorded_paths = empty_lists.get(golden, [])
    assert not recorded_paths or set(recorded_paths) <= actual_empty_paths, (
        f"{golden} emptyLists paths do not point to empty lists"
    )
    assert item["difference"] is not None


def test_matched_cases_fail_if_golden_mutated(client: TestClient) -> None:
    for item in _MATCHED:
        sharpit_id, name = _fixture_parts(item["golden"])
        response = client.get(item["route"])
        assert response.status_code == 200
        mutated = dict(response.json())
        expected = json.loads((_FIXTURES_DIR / item["golden"]).read_text(encoding="utf-8"))
        key = next(key for key, value in expected.items() if value is not None)
        original = expected[key]
        mutated[key] = (
            []
            if isinstance(original, dict)
            else {}
            if isinstance(original, list)
            else None
            if isinstance(original, str)
            else "__mutation__"
        )
        with pytest.raises(AssertionError):
            assert_parity(sharpit_id, name, mutated, fixture_version="2.3.0", matched=True)


def test_bootui_marks_equal_the_matched_rows() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    marked = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "bootui"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    route_keys = {f"route:GET {item['route'].removeprefix('/sharpit/api')}" for item in _MATCHED}
    assert marked == route_keys
