"""ROADMAP.md and README.md state how close sharpit is to BootUI; these numbers are recomputed from the code and the
BootUI 2.3.0 fixtures, so the docs cannot drift from either."""

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
BOOTUI = ROOT / "tests" / "fixtures" / "bootui" / "2.3.0"


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
    routes = json.loads((ROOT / "tests" / "parity" / "routes_23_status.json").read_text("utf-8"))["counts"]
    implemented = [k for k in KINDS if k.module.IMPLEMENTED]
    evaluating = [k for k in implemented if k.reads <= PRODUCED_SOURCES]
    applicable = routes["total"] - routes["n-a"]
    return {
        "tools": f"| MCP/CLI tools | 54 | {len(ours)} | {len(bootui_tools)} | 116 |",
        "names": f"| Tools under BootUI's exact names | 45 | {len(ours & bootui_tools)} | - | - |",
        "panels": f"| Panels | 31 | {len(PANELS)} ({_listed_panels()} listed in the console) | "
        f"{len(json.loads((BOOTUI / 'panels.json').read_text('utf-8'))['panels'])} (Spring) | 65 (Spring) |",
        "insights": f"| Runtime insight kinds that evaluate | none | {len(evaluating)} of {len(KINDS)} registered | "
        f"{len(KINDS)} | 28 |",
        "routes": f"| BootUI API routes served, of the {applicable} that apply to Python | not measured | "
        f"{routes['matched'] + routes['partial']} ({routes['matched']} shape-identical, {routes['partial']} partial) | "
        f"{applicable} | not captured |",
    }


def test_roadmap_matrix_matches_the_code_and_the_bootui_fixtures():
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    for name, row in _matrix().items():
        assert row in roadmap, f"ROADMAP.md {name} row must read: {row}"


def test_readme_states_the_matrix_and_links_the_roadmap():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "(ROADMAP.md)" in readme, "README.md must link ROADMAP.md"
    for name, row in _matrix().items():
        assert row in readme, f"README.md {name} row must read: {row}"
