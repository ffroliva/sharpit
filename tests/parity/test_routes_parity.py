"""Panel GET route parity tests against BootUI 2.3.0 live goldens (W3 lane C1)."""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import httpx
import prometheus_client  # noqa: F401  the metrics goldens assume the observed registry is loaded (isolated run)
import pytest
from examples.fastapi_sample.app import create_app
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import SpanContext, TraceFlags

from conftest import SideEffectGuard
from fastapi import FastAPI
from golden import assert_parity, bootui_ids
from sharpit.engine.capture.traces import span_buffer
from sharpit.engine.collectors.vulns.osv import OsvClient

_API = "/sharpit/api"
_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "bootui" / "2.3.0"
_STATUS_FILE = Path(__file__).with_name("routes_status.json")
_TRACE_ID = 1
_TRACE_PATH = f"{_API}/traces/{_TRACE_ID:032x}"

_STATUS_DATA = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
_ROUTES = _STATUS_DATA["routes"]
_ROUTES_BY_GOLDEN = {r["golden"]: r for r in _ROUTES}
_PASSING_SCENARIOS = ("database-advisor/scanned.captured.json", "postgresql/scanned.captured.json")

_MATCHED = [r for r in _ROUTES if r["status"] == "matched"]
_PARTIAL = [r for r in _ROUTES if r["status"] == "partial" and r["golden"] not in _PASSING_SCENARIOS]
_MISSING = [r for r in _ROUTES if r["status"] == "missing"]
_NA = [r for r in _ROUTES if r["status"] == "n-a"]

pytestmark = [
    pytest.mark.bootui("route:GET /ai/tokens"),
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


@pytest.fixture(scope="module")
def asgi_request() -> Iterator[Callable[[FastAPI, str, str], httpx.Response]]:
    # Windows creates the event loop's self-pipe before the side-effect guard starts.
    with asyncio.Runner() as runner:
        runner.get_loop()

        async def send(app: FastAPI, method: str, path: str) -> httpx.Response:
            transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
                return await client.request(method, path)

        yield lambda app, method, path: runner.run(send(app, method, path))


@pytest.fixture
def make_app(tmp_state_dir: Path) -> Iterator[Callable[..., FastAPI]]:
    with ExitStack() as cleanup:

        def create(**options: Any) -> FastAPI:
            app = create_app(show_banner=False, state_dir=str(tmp_state_dir), **options)
            cleanup.callback(app.state.sharpit.uninstall_capture)
            return app

        yield create


def _seed_trace(app: FastAPI, attributes: dict[str, bool | str] | None = None) -> str:
    span = ReadableSpan(
        "sample",
        context=SpanContext(_TRACE_ID, 1, False, TraceFlags(1)),
        start_time=1,
        end_time=2,
        instrumentation_scope=InstrumentationScope("parity"),
        attributes=attributes,
    )
    span_buffer(app.state.sharpit.context).add(span)
    return f"{_TRACE_ID:032x}"


@pytest.fixture
def scenario_get(
    asgi_request: Callable[[FastAPI, str, str], httpx.Response],
    make_app: Callable[..., FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    no_side_effects: SideEffectGuard,
) -> Callable[..., httpx.Response]:
    def get(item: dict[str, Any], *, attributes: dict[str, bool | str] | None = None) -> httpx.Response:
        route = item["route"]
        scenario = item.get("scenario")
        options: dict[str, Any] = {}
        if scenario in ("post-scan", "post-read"):
            options["panels"] = {item["panel"]: {"read_only": False}}
        if scenario == "post-scan" and item["panel"] == "vulnerabilities":
            options["vulnerabilities_epss_enabled"] = False
            monkeypatch.setattr(OsvClient, "_query_page", lambda self, pending, deadline: [{} for _ in pending])

        app = make_app(**options)
        if scenario in ("post-scan", "post-read"):
            action = f"{route}/{scenario.removeprefix('post-')}"
            response = asgi_request(app, "POST", action)
            assert response.status_code == 200, f"POST {action} returned HTTP {response.status_code}"
        elif scenario == "seeded-trace":
            route = route.format(id=_seed_trace(app, attributes))
        else:
            assert scenario is None, f"Unknown scenario {scenario!r}"

        no_side_effects.rebaseline()
        return asgi_request(app, "GET", route)

    return get


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
    assert set(golden_files).issubset(set(classified_goldens))
    assert [g for g in classified_goldens if g in set(golden_files)] == golden_files
    assert len(classified_goldens) == len(set(classified_goldens))

    counts = {
        status: sum(item["status"] == status for item in _ROUTES) for status in ("matched", "partial", "missing", "n-a")
    }
    assert _STATUS_DATA["counts"] == {**counts, "total": len(_ROUTES)}
    assert len(_ROUTES) == 97


@pytest.mark.parametrize(
    ("golden", "path"),
    [
        ("architecture/scanned.captured.json", "/architecture"),
        ("database-advisor/scanned.captured.json", "/database-advisor"),
        ("fastapi/scanned.captured.json", "/fastapi"),
        ("memory/scanned.captured.json", "/memory"),
        ("postgresql/scanned.captured.json", "/postgresql"),
        ("rest-api/scanned.captured.json", "/rest-api"),
        ("runtime-insights/impact-symbols.captured.json", "/runtime-insights/impact/symbols"),
        ("security/scanned.captured.json", "/security"),
        ("traces/detail.captured.json", "/traces/{id}"),
        ("vulnerabilities/scanned.captured.json", "/vulnerabilities"),
    ],
)
def test_inventory_uses_canonical_paths(golden: str, path: str) -> None:
    assert _ROUTES_BY_GOLDEN[golden]["route"] == f"{_API}{path}"


@pytest.mark.parametrize(
    ("golden", "scenario"),
    [
        ("architecture/scanned.captured.json", "post-scan"),
        ("database-advisor/scanned.captured.json", "post-scan"),
        ("fastapi/scanned.captured.json", "post-scan"),
        ("postgresql/scanned.captured.json", "post-read"),
        ("rest-api/scanned.captured.json", "post-scan"),
        ("security/scanned.captured.json", "post-scan"),
        ("traces/detail.captured.json", "seeded-trace"),
        ("vulnerabilities/scanned.captured.json", "post-scan"),
    ],
)
def test_inventory_pins_served_scenario_setup(golden: str, scenario: str) -> None:
    assert _ROUTES_BY_GOLDEN[golden].get("scenario") == scenario


@pytest.mark.parametrize("item", _MATCHED, ids=lambda r: str(r["golden"]))
def test_matched_routes_pass_23_parity(scenario_get: Callable[..., httpx.Response], item: dict[str, Any]) -> None:
    route = item["route"]
    sharpit_id, name = _fixture_parts(item["golden"])
    response = scenario_get(item)
    assert response.status_code == 200, f"{route} returned HTTP {response.status_code}"
    payload = response.json()
    assert_parity(sharpit_id, name, payload, fixture_version="2.3.0", matched=True)


@pytest.mark.parametrize("item", _PARTIAL, ids=lambda r: str(r["golden"]))
def test_partial_routes_record_exact_gaps(scenario_get: Callable[..., httpx.Response], item: dict[str, Any]) -> None:
    route = item["route"]
    sharpit_id, name = _fixture_parts(item["golden"])
    response = scenario_get(item)
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


@pytest.mark.parametrize("golden", _PASSING_SCENARIOS)
def test_passing_scenarios_pin_empty_golden_lists(scenario_get: Callable[..., httpx.Response], golden: str) -> None:
    item = _ROUTES_BY_GOLDEN[golden]
    assert item["status"] == "partial"
    response = scenario_get(item)
    assert response.status_code == 200
    assert_parity(*_fixture_parts(golden), response.json(), fixture_version="2.3.0", matched=True)
    expected = json.loads((_FIXTURES_DIR / golden).read_text(encoding="utf-8"))
    assert _empty_list_paths(expected) == set(item["emptyGoldenLists"])


def test_seeded_trace_renders_attributes(scenario_get: Callable[..., httpx.Response]) -> None:
    golden = "traces/detail.captured.json"
    response = scenario_get(_ROUTES_BY_GOLDEN[golden], attributes={"parity.flag": True, "parity.label": "sample"})
    assert response.status_code == 200
    payload = response.json()
    assert_parity(*_fixture_parts(golden), payload, fixture_version="2.3.0", matched=True)
    assert payload["spans"][0]["attributes"] == [
        {"key": "parity.flag", "type": "BOOLEAN", "value": "true"},
        {"key": "parity.label", "type": "STRING", "value": "sample"},
    ]


def test_seeded_trace_does_not_resolve_literal_id(
    asgi_request: Callable[[FastAPI, str, str], httpx.Response],
    make_app: Callable[..., FastAPI],
    no_side_effects: SideEffectGuard,
) -> None:
    app = make_app()
    _seed_trace(app)
    no_side_effects.rebaseline()
    response = asgi_request(app, "GET", f"{_API}/traces/{{id}}")
    assert response.status_code == 404


def test_unknown_trace_returns_404(scenario_get: Callable[..., httpx.Response]) -> None:
    assert scenario_get({"route": _TRACE_PATH}).status_code == 404


def test_error_contract_records_its_bootui_23_parity_gap(scenario_get: Callable[..., httpx.Response]) -> None:
    response = scenario_get({"route": f"{_API}/rest-api/error-contract"})
    assert response.status_code == 200
    payload = response.json()
    with pytest.raises(AssertionError) as exc_info:
        assert_parity(
            "rest-api",
            "error-contract",
            payload,
            fixture_version="2.3.0",
            matched=True,
        )
    assert str(exc_info.value) == (
        "rest-api/error-contract.captured.json parity: entries: non-empty golden list requires a non-empty payload list"
    )


@pytest.mark.parametrize("item", _MISSING, ids=lambda r: str(r["golden"]))
def test_missing_routes_return_404(scenario_get: Callable[..., httpx.Response], item: dict[str, Any]) -> None:
    route = item["route"]
    response = scenario_get(item)
    assert response.status_code == 404, f"{route} unexpectedly returned HTTP {response.status_code}"


@pytest.mark.parametrize("item", _NA, ids=lambda r: str(r["golden"]))
def test_na_routes_have_empty_list_in_fixture(item: dict[str, Any]) -> None:
    assert item["status"] == "n-a"
    assert item["difference"] is not None
    if item["difference"].startswith("JVM-only:"):
        return
    meta = json.loads((_FIXTURES_DIR / "meta.json").read_text(encoding="utf-8"))
    empty_lists = meta.get("emptyLists", {})
    golden = item["golden"]
    fixture = json.loads((_FIXTURES_DIR / golden).read_text(encoding="utf-8"))
    actual_empty_paths = _empty_list_paths(fixture)
    assert actual_empty_paths, f"{golden} contains no empty list"
    recorded_paths = empty_lists.get(golden, [])
    assert not recorded_paths or set(recorded_paths) <= actual_empty_paths, (
        f"{golden} emptyLists paths do not point to empty lists"
    )


def test_matched_cases_fail_if_golden_mutated(scenario_get: Callable[..., httpx.Response]) -> None:
    for item in _MATCHED:
        sharpit_id, name = _fixture_parts(item["golden"])
        response = scenario_get(item)
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
    assert marked == route_keys | {"route:GET /mappings/flat"}
