"""Unit tests for live BootUI 2.3.0 capture script with hard allow-list."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from scripts.capture_bootui_live import (
    EXCLUDED_ROUTES,
    POST_ALLOW_LIST,
    REPO_ROOT,
    Step,
    build_plan,
    run,
)


class StubResponse:
    def __init__(self, data: Any, status: int = 200) -> None:
        self.data = data
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self.data).encode("utf-8")


def test_capture_plan_never_requests_raw_or_actions() -> None:
    routes = json.loads((REPO_ROOT / "tests/fixtures/bootui/2.3.0/routes.json").read_text(encoding="utf-8"))
    ids = json.loads((REPO_ROOT / "tests/fixtures/bootui/2.2.0/ids.json").read_text(encoding="utf-8"))
    plan = build_plan(routes, ids)
    assert len(plan) > 0, "plan must not be empty"
    for step in plan:
        assert "/raw" not in step.path, f"raw path requested: {step.path}"
        if step.method != "GET":
            assert step.method == "POST", f"non-GET method must be POST: {step.method}"
            assert step.path in POST_ALLOW_LIST, f"POST not in allow-list: {step.path}"
        assert not any(
            forbidden in step.path
            for forbidden in ("/github/refresh", "/heap-dump/capture", "/cache/clear", "/loggers/", "/restart")
        )


def test_capture_writes_raw_outside_the_repo(tmp_path: Path) -> None:
    plan = [
        Step(
            phase="pre-scan GET",
            method="GET",
            path="/overview",
            panel="overview",
            sharpit_id="overview",
            name="captured",
        )
    ]
    stub_opener = lambda req: StubResponse({"status": "UP"})  # noqa: E731
    with pytest.raises(ValueError, match="inside the git repo"):
        run(plan, stub_opener, REPO_ROOT / "fixtures_raw_capture")

    out_dir = tmp_path / "raw"
    run(plan, stub_opener, out_dir)
    assert (out_dir / "overview" / "captured.json").is_file(), "raw capture not written"


def test_uncaptured_entries_carry_a_status(tmp_path: Path) -> None:
    plan = [
        Step(
            phase="pre-scan GET",
            method="GET",
            path="/flyway/migrations",
            panel="flyway",
            sharpit_id="alembic",
            name="captured",
        )
    ]

    def stub_opener(req: Any) -> Any:
        url = getattr(req, "full_url", str(req))
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))

    out_dir = tmp_path / "raw"
    run(plan, stub_opener, out_dir)
    uncaptured_file = out_dir / "uncaptured.json"
    assert uncaptured_file.is_file(), "uncaptured.json must be written"
    data = json.loads(uncaptured_file.read_text(encoding="utf-8"))
    assert "GET /flyway/migrations" in data, "uncaptured entries must use route keys"
    allowed_statuses = {"404", 404, "disabled", "error", "needs-external", "not-probed"}
    for item_id, entry in data.items():
        assert entry["status"] in allowed_statuses, f"invalid status {entry['status']} for {item_id}"
        assert isinstance(entry["reason"], str)
        assert len(entry["reason"]) > 0
        assert entry["http"] is None or isinstance(entry["http"], int)


def test_run_rejects_unsafe_method_before_request(tmp_path: Path) -> None:
    calls: list[Any] = []
    step = Step("pre-scan GET", "DELETE", "/security/scan", "security", "security")
    with pytest.raises(ValueError, match="method/path not allowed"):
        run([step], lambda req: calls.append(req), tmp_path / "raw")
    assert calls == [], "unsafe method must be rejected before any request"


def test_uncaptured_subroutes_do_not_collide(tmp_path: Path) -> None:
    def fail(req: Any) -> Any:
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b""))

    plan = [
        Step("pre-scan GET", "GET", "/panel/a", "panel", "panel"),
        Step("pre-scan GET", "GET", "/panel/b", "panel", "panel"),
    ]
    result = run(plan, fail, tmp_path / "raw")
    assert "GET /panel/a" in result, "first route failure must be retained"
    assert "GET /panel/b" in result, "second route failure must not overwrite first"


def test_scanner_records_parameterized_route_ids(tmp_path: Path) -> None:
    requested: list[str] = []

    def stub(req: Any) -> StubResponse:
        requested.append(req.full_url)
        if req.full_url.endswith("/exceptions"):
            return StubResponse([{"id": "found-id"}])
        return StubResponse({"detail": "captured"})

    plan = [
        Step("pre-scan GET", "GET", "/exceptions", "exceptions", "exceptions"),
        Step("pre-scan GET", "GET", "/exceptions/{id}", "exceptions", "exceptions", "detail"),
    ]
    run(plan, stub, tmp_path / "raw")
    assert any(url.endswith("/exceptions/found-id") for url in requested), "list response id must fill detail route"


def test_plan_covers_every_starter_get() -> None:
    routes = json.loads((REPO_ROOT / "tests/fixtures/bootui/2.3.0/routes.json").read_text(encoding="utf-8"))
    ids = json.loads((REPO_ROOT / "tests/fixtures/bootui/2.2.0/ids.json").read_text(encoding="utf-8"))
    plan = build_plan(routes, ids)
    assert len(plan) > 0, "plan must not be empty"
    plan_paths = {step.path for step in plan}
    starter_gets = [
        m["path"] for m in routes.get("crossCheck", {}).get("starterMappings", []) if m.get("verb") == "GET"
    ]
    for path in starter_gets:
        covered = (
            path in plan_paths
            or path in EXCLUDED_ROUTES
            or (path == "/rules/{ruleId}/violations" and any("/rules/{ruleId}/violations" in s.path for s in plan))
        )
        assert covered, f"starter GET {path} is neither in plan nor in EXCLUDED_ROUTES"
