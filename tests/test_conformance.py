"""Shape conformance with the BootUI 1.17.0 golden captures (spec §12): for every MVP endpoint with a golden
fixture, the recursive key set of sharpit's response equals the golden's, minus the documented deviations below.

Not compared: ``health.json`` (health is a non-goal, spec §14), ``meta.json`` (capture metadata, not an endpoint) and
``mappings.json``, which is the raw Spring Actuator ``GET /mappings`` descriptor that contract §4 drops; the MVP
endpoint ``mappings/flat`` is checked against the contract §4 DTO instead.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import time
from pathlib import Path
from statistics import median

import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from conftest import FIXTURES, SideEffectGuard, golden
from fastapi import FastAPI
from golden import _fixture, bootui_ids  # pyright: ignore[reportPrivateUsage]
from sharpit import install
from sharpit.fastapi.adapter import SharpitMount

LOCAL = ("127.0.0.1", 50000)
ENDPOINTS = {
    "overview": "overview",
    "panels": "panels",
    "config": "config",
    "loggers": "loggers",
    "beans": "beans",
    "vulnerabilities": "vulnerabilities",
}
_SANITIZE = Path(__file__).resolve().parents[1] / "scripts" / "sanitize_golden.py"
_spec = importlib.util.spec_from_file_location("sanitize_golden", _SANITIZE)
assert _spec
assert _spec.loader
_sanitize = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sanitize)
find_secrets = _sanitize.find_secrets
NOT_COMPARED = {"health", "meta", "mappings"}

# fixture -> {recursive key path: reason} for keys BootUI added after the 1.17.0 capture; they must be present in ours
NEWER_THAN_GOLDEN: dict[str, dict[str, str]] = {
    "overview": dict.fromkeys(
        ("run", "run.instanceId", "run.runId", "run.ordinal", "run.startedAt"),
        "BootUI 2.2.0 OverviewDto.run; the 1.17.0 golden predates it",
    ),
    "vulnerabilities": dict.fromkeys(
        (
            "runtimeReach",
            "runtimeReach.available",
            "runtimeReach.unavailableReason",
            "runtimeReach.generation",
            "runtimeReach.note",
            "runtimeReach.incompleteReason",
            "dependencies[].runtimeReach",
            "coverage.archivesFirstParty",
            "coverage.firstPartyArchives",
            "coverage.firstPartyArchivesTruncated",
        ),
        "BootUI 2.2.0 runtime reach and first-party coverage (contract 0.4 drift §7, lane D4)",
    ),
}
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
    """Every dotted key path in ``value``; list items share one ``[]`` segment. Every object in one list must have the
    same keys (every DTO key is emitted, nulls included), so the union never hides an item missing a key."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found |= {path} | keys(item, path)
    elif isinstance(value, list):
        shapes = {frozenset(item) for item in value if isinstance(item, dict)}
        assert len(shapes) <= 1, f"{prefix}[] items differ in keys: {sorted(map(sorted, shapes))}"
        for item in value:
            found |= keys(item, prefix + "[]")
    return found


def test_keys_is_recursive():
    assert keys({"a": [{"b": 1, "c": {"d": None}}, {"b": 2, "c": None}], "e": []}) == {
        "a",
        "a[].b",
        "a[].c",
        "a[].c.d",
        "e",
    }
    with pytest.raises(AssertionError, match=r"a\[\] items differ in keys"):
        keys({"a": [{"b": 1}, {"b": 2, "c": 3}]})


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
    newer = set(NEWER_THAN_GOLDEN.get(name, {}))
    assert newer <= ours, f"keys newer than the golden missing: {newer - ours}"
    ours -= newer
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
    apps: list[FastAPI] = []

    def run() -> float:
        app = create_app(enabled="OFF")
        # a second install() is a no-op (Task P1 item 5): drop the sample's inactive stub so the timed call mounts
        app.router.routes[:] = [r for r in app.router.routes if not isinstance(r, SharpitMount)]
        start = time.perf_counter()
        install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))
        elapsed = time.perf_counter() - start
        apps.append(app)
        return elapsed

    runs = [run() for _ in range(5)]
    assert median(runs) <= 0.050, [f"{r * 1000:.1f} ms" for r in runs]
    assert no_side_effects.violations == []
    no_side_effects.unblock_network()  # timing done; TestClient's Windows loop connects a self-pipe socketpair
    for app in apps:  # the timed install really mounted an active sharpit
        assert (
            TestClient(app, base_url="http://localhost", client=LOCAL).get("/sharpit/api/overview").status_code == 200
        )


GOLDEN_2_2_0 = FIXTURES / "2.2.0"
EXTRA_2_2_0_PANELS = ("overview", "panels", "dismissed-rules", "dismissed-findings")
# golden -> why no sharpit payload is checked against it
NOT_LIVE_2_2_0 = {
    "activity/service-map.captured.json": "the route is not built (CHANGELOG 0.5.0 Known limitations)",
}
# these test assert_parity itself on made-up payloads, so a call there proves nothing about an endpoint
PARITY_HELPER_TESTS = {
    "test_golden.py",
    "test_golden_shapes.py",
    "test_foundation_round2.py",
    "test_foundation_round3.py",
}


def _meta_2_2_0() -> dict[str, object]:
    assert (GOLDEN_2_2_0 / "meta.json").is_file()
    return json.loads((GOLDEN_2_2_0 / "meta.json").read_text(encoding="utf-8"))


def _expected_sharpit_ids() -> list[str]:
    return sorted({*bootui_ids().values(), *EXTRA_2_2_0_PANELS})


def test_golden_capture_manifest_has_all_2_2_0_panels_and_no_error_envelopes():
    meta = _meta_2_2_0()
    uncaptured = meta.get("uncaptured", {})
    assert isinstance(uncaptured, dict)
    provisional = meta.get("provisional", [])
    assert isinstance(provisional, list)
    missing: list[str] = []
    for sid in _expected_sharpit_ids():
        folder = GOLDEN_2_2_0 / sid
        has_live = (folder / "captured.json").is_file() or any(folder.glob("*.captured.json"))
        has_provisional = sid in provisional and any(folder.glob("*provisional.json"))
        if not (has_live or has_provisional or sid in uncaptured):
            missing.append(sid)
    assert missing == []
    assert meta.get("bootuiVersion") == "2.2.0"
    assert sorted(p.name for p in GOLDEN_2_2_0.glob("*.json")) == ["ids.json", "meta.json"]
    for reason in uncaptured.values():
        assert isinstance(reason, str)
        assert reason.strip()
    envelopes: list[str] = []
    for p in GOLDEN_2_2_0.glob("*/*captured.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and set(data) == {"error"}:  # pyright: ignore[reportUnknownArgumentType]
            envelopes.append(str(p.relative_to(GOLDEN_2_2_0)))
    assert envelopes == []


def test_conformance_2_2_0_goldens_and_ids_mapping():
    captured = sorted(GOLDEN_2_2_0.glob("*/*captured.json"))
    assert captured
    for path in captured:
        assert path.parent.name in _expected_sharpit_ids()
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), (dict, list))
    assert set(bootui_ids().values()) >= {"alembic", "sqlalchemy-statistics", "fastapi-security", "fastapi"}


def test_every_nullable_reason_is_a_non_empty_string():
    # assert_parity checks this too, but only for a panel some test calls it on
    bad = [
        f"{path.parent.name}: {key}"
        for path in GOLDEN_2_2_0.glob("*/nullable.json")
        for key, why in json.loads(path.read_text(encoding="utf-8")).items()
        if not (isinstance(why, str) and why.strip())
    ]
    assert bad == []


def _literal_parity_calls(source: str) -> set[tuple[str, str]]:
    """``(sharpit_id, name)`` of every ``assert_parity`` call with literal arguments in ``source``."""
    found: set[tuple[str, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or len(node.args) < 2:
            continue
        name = getattr(node.func, "attr", getattr(node.func, "id", ""))
        first, second = node.args[:2]
        if name == "assert_parity" and isinstance(first, ast.Constant) and isinstance(second, ast.Constant):
            found.add((str(first.value), str(second.value)))
    return found


def _goldens_with_a_live_call() -> set[str]:
    """Golden paths under ``GOLDEN_2_2_0`` that a real payload is checked against somewhere in the suite."""
    covered: set[str] = set()
    tests = Path(__file__).parent
    for path in tests.rglob("test_*.py"):
        source = path.read_text(encoding="utf-8")
        if "fixtures" in path.parts or path.name in PARITY_HELPER_TESTS or "assert_parity(" not in source:
            continue
        for sharpit_id, name in _literal_parity_calls(source):
            golden_path, _ = _fixture(GOLDEN_2_2_0 / sharpit_id, name)
            covered.add(golden_path.relative_to(GOLDEN_2_2_0).as_posix())
    return covered


def test_literal_parity_calls_are_found_in_both_call_forms_and_dynamic_ones_are_not():
    source = """
assert_parity("a", "captured", {})
golden.assert_parity("b", "report", {})
assert_parity(sharpit_id, "captured", {})
"""
    assert _literal_parity_calls(source) == {("a", "captured"), ("b", "report")}


def test_every_captured_golden_has_a_live_parity_call():
    goldens = {p.relative_to(GOLDEN_2_2_0).as_posix() for p in GOLDEN_2_2_0.glob("*/*captured.json")}
    uncovered = goldens - _goldens_with_a_live_call()
    assert uncovered == set(NOT_LIVE_2_2_0)


def test_a_golden_exempt_from_a_live_call_gives_a_reason():
    assert all(why.strip() for why in NOT_LIVE_2_2_0.values())


def test_golden_2_2_0_fixtures_hold_no_secrets():
    leaks = {
        str(p.relative_to(GOLDEN_2_2_0)): find_secrets(json.loads(p.read_text(encoding="utf-8")))
        for p in GOLDEN_2_2_0.glob("*/*.json")
    }
    assert {k: v for k, v in leaks.items() if v} == {}
