from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import golden

FIXTURES = Path(__file__).parent / "fixtures" / "bootui" / "2.3.0"
ROUTES = FIXTURES / "routes.json"
CONFORMANCE_PROBES = {
    "/activity/request/conformance-unknown-request",
    "/activity/request/conformance-unknown-request/journal",
    "/code-paths/requests/0000000000000000",
    "/code-paths/route?route=GET%20%2Fnot-a-route",
    "/runtime-insights/impact?symbol=conformanceUnknownSymbol",
    "/runtime-insights/insights/conformance-unknown:0000000000",
    "/runtime-insights/impact/symbols?query=conformanceUnknownSymbol",
    "/code-inventory/methods?status=never-executed",
    "/side-effects/sensor?sensor=processes",
}
UNCAPTURED_STATUSES = {"404", "disabled", "error", "needs-external", "not-probed"}
ADVISOR_PANELS = (
    "security",
    "architecture",
    "rest-api",
    "vulnerabilities",
    "database-advisor",
    "hibernate",
    "spring",
    "memory",
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _capture_name(path: str, panel: str) -> str:
    cleaned = path.strip("/")
    if cleaned == panel or not cleaned:
        return "captured.json"
    leaf = cleaned.split("/", 1)[1].split("?", 1)[0].replace("/", "-")
    return f"{leaf or 'captured'}.captured.json"


def _golden_route(route: str, panel: str, sharpit_id: str) -> bool:
    # The live trace detail was captured with a concrete id; its content stays opaque here.
    if route.startswith("/traces/{traceId}"):
        return (FIXTURES / sharpit_id / "detail.captured.json").is_file()
    return (FIXTURES / sharpit_id / _capture_name(route, panel)).is_file()


def _empty_list_paths(value: Any, path: str = "") -> list[str]:
    paths = [path] if isinstance(value, list) and not value else []
    if isinstance(value, dict):
        for key, child in value.items():
            paths.extend(_empty_list_paths(child, f"{path}.{key}" if path else key))
    elif isinstance(value, list):
        for child in value:
            paths.extend(_empty_list_paths(child, f"{path}[]"))
    return paths


def _computed_empty_lists() -> dict[str, list[str]]:
    files = sorted(FIXTURES.glob("*/captured.json")) + sorted(FIXTURES.glob("*/**/*.captured.json"))
    return {
        path.relative_to(FIXTURES).as_posix(): _empty_list_paths(_json(path))
        for path in files
        if _empty_list_paths(_json(path))
    }


def test_every_23_get_has_a_golden_or_an_uncaptured_status() -> None:
    routes = _json(ROUTES)
    ids = golden.bootui_ids("2.3.0")
    uncaptured = _json(FIXTURES / "meta.json").get("uncaptured", {})
    expected = {(item["path"], item["panel"]) for item in routes["reads"] if item["method"] == "GET"}
    expected |= {
        (item["path"], item["path"].strip("/").split("/", 1)[0])
        for item in routes["crossCheck"]["starterMappings"]
        if item["verb"] == "GET"
        and item["path"] not in CONFORMANCE_PROBES
        and item["path"] != "/rules/{ruleId}/violations"
    }
    expected |= {(f"/{panel}/rules/{{ruleId}}/violations?limit=5", panel) for panel in ADVISOR_PANELS}

    missing = []
    for path, panel in sorted(expected):
        key = f"GET {path}"
        sharpit_id = ids.get(panel, panel)
        if _golden_route(path, panel, sharpit_id):
            continue
        status = uncaptured.get(key, {}).get("status")
        if status not in UNCAPTURED_STATUSES and status != 404:
            missing.append(key)
    assert not missing, f"GET routes lack a golden or valid uncaptured status: {missing}"
    assert all("{" not in p.name and "}" not in p.name for p in FIXTURES.rglob("*") if p.is_file()), (
        "fixture file names must not contain route-template braces"
    )


def test_23_ids_cover_every_golden_folder() -> None:
    ids = golden.bootui_ids("2.3.0")
    folders = {path.name for path in FIXTURES.iterdir() if path.is_dir() and any(path.glob("*.captured.json"))}
    assert folders <= set(ids.values()), f"golden folders missing from ids.json: {sorted(folders - set(ids.values()))}"


def test_meta_lists_empty_list_goldens() -> None:
    meta = _json(FIXTURES / "meta.json")
    assert meta.get("emptyLists") == _computed_empty_lists(), "meta.json emptyLists differs from fixture contents"
