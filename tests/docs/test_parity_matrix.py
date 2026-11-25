"""Pin the published parity columns and compute sharpit 0.10.0 from the code and fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine.collectors.insights.registry import KINDS  # noqa: E402
from sharpit.engine.collectors.insights.snapshot import PRODUCED_SOURCES  # noqa: E402
from sharpit.engine.panels import PANELS  # noqa: E402
from sharpit.engine.tools import TOOLS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BOOTUI = ROOT / "tests" / "fixtures" / "bootui" / "2.5.0"
ROUTE_STATUS = json.loads((ROOT / "tests" / "parity" / "routes_status.json").read_text("utf-8"))


def _route_counts() -> tuple[dict[str, int], int]:
    routes = ROUTE_STATUS["counts"]
    distinct_served = {item["route"] for item in ROUTE_STATUS["routes"] if item["status"] in ("matched", "partial")}
    return routes, len(distinct_served)


def _listed_panels() -> int:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False)
    try:
        client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
        return len(client.get("/sharpit/api/panels").json()["panels"])
    finally:
        handle.uninstall_capture()


def _matrix() -> dict[str, str]:
    bootui_tools = {t["name"] for t in json.loads((BOOTUI / "tools.json").read_text("utf-8"))["tools"]}
    ours = {t.name for t in TOOLS}
    routes, distinct_served = _route_counts()
    implemented = [k for k in KINDS if k.module.IMPLEMENTED]
    evaluating = [k for k in implemented if k.reads <= PRODUCED_SOURCES]
    return {
        "tools": f"| MCP/CLI tools | 54 | 71 | 71 | 73 | 73 | {len(ours)} | 116 | 116 | 116 |",
        "names": "| Tools under BootUI's exact names | 45 | 62 | 62 | 64 | 64 | "
        f"{len(ours & bootui_tools)} | - | - | - |",
        "panels": "| Panels | 31 | 48 (46 listed in the console) | 48 (46 listed in the console) | "
        f"49 (47 listed in the console) | 49 (47 listed in the console) | {len(PANELS)} "
        f"({_listed_panels()} listed in the console) | 65 (Spring) | 65 (Spring) | 65 (Spring) |",
        "insights": "| Runtime insight kinds that evaluate | none | 8 of 28 registered | 10 of 28 registered | "
        f"11 of 29 registered | 11 of 29 registered | {len(evaluating)} of {len(KINDS)} registered | 28 | 28 | 29 |",
        "routes": "| Applicable BootUI GET fixture cases served | not measured | "
        "33 (5 shape-identical, 28 partial) | 33 (5 shape-identical, 28 partial) | "
        "33 (5 shape-identical, 28 partial) | 33 (5 shape-identical, 28 partial) | "
        f"{routes['matched'] + routes['partial']} across {distinct_served} routes "
        f"({routes['matched']} shape-identical, {routes['partial']} partial) | "
        f"65 | not captured | {routes['total'] - routes['n-a']} |",
    }


def test_roadmap_matrix_matches_the_code_and_the_bootui_fixtures():
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    for name, row in _matrix().items():
        assert row in roadmap, f"ROADMAP.md {name} row must read: {row}"
    assert "| sharpit 0.9.0 | sharpit 0.10.0 | BootUI 2.3.0 |" in roadmap


def test_applicable_route_fixture_count_stays_pinned() -> None:
    routes, _ = _route_counts()
    assert routes["total"] - routes["n-a"] == 56


def test_roadmap_explains_route_fixture_counts() -> None:
    routes, distinct_served = _route_counts()
    applicable = routes["total"] - routes["n-a"]
    served = routes["matched"] + routes["partial"]
    jvm_only = sum(
        item["status"] == "n-a" and item["difference"].startswith("JVM-only:") for item in ROUTE_STATUS["routes"]
    )
    expected = (
        f"Sharpit 0.10.0 serves {served} of {applicable} applicable fixture cases across {distinct_served} GET routes. "
        f"Of these cases, {routes['matched']} match BootUI's shape and {routes['partial']} have recorded differences. "
        f"{routes['missing']} applicable cases are missing. "
        f"Of the {routes['n-a']} cases marked `n-a`, {jvm_only} are classified as JVM-only and "
        f"{routes['n-a'] - jvm_only} are served with fixtures that cannot establish parity."
    )
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    assert expected in " ".join(roadmap.split())


def test_readme_states_the_matrix_and_links_the_roadmap():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "(ROADMAP.md)" in readme, "README.md must link ROADMAP.md"
    for name, row in _matrix().items():
        assert row in readme, f"README.md {name} row must read: {row}"
    assert "| sharpit 0.9.0 | sharpit 0.10.0 | BootUI 2.3.0 |" in readme
