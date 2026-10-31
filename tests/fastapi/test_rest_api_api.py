"""REST API advisor endpoints and tools against a real FastAPI app (spec §7.10, §13.2). Route metadata is read from
``APIRoute`` attributes only: ``app.openapi()`` is never called."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastapi import APIRouter, FastAPI, Request, Response
from sharpit import install
from sharpit.engine.collectors.restapi.service import OPERATION
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.tools import CallContext, ToolCallError, call_tool

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/rest-api"


class Pet(BaseModel):
    name: str


class PetRow(BaseModel):
    """Stands in for a SQLModel ``table=True`` class: pydantic ignores the dunder, the advisor sees a table."""

    __table__ = object()
    name: str


def _app() -> FastAPI:
    app = FastAPI()
    router = APIRouter(prefix="/v1", tags=["pets"])

    @router.get("/pets", summary="List pets")
    def read_pets() -> list[Pet]:  # PAGE-001: a collection without paging parameters
        return []

    @router.get("/rows", summary="Rows")
    def read_rows() -> list[PetRow]:  # DTO-001 through list[...]
        return []

    @router.get("/row", summary="Row")
    def read_row() -> PetRow | None:  # DTO-001 through Optional
        return None

    @router.post("/pets", summary="Create")
    def create_pet(pet: Pet) -> Pet:  # RESP-001: create-like POST with the default 200
        return pet

    @router.delete("/pets/{name}", status_code=204, response_model=None, summary="Gone")
    def remove_pet(name: str) -> Pet:  # RESP-006: the only 204 + content shape FastAPI lets you build
        return Pet(name=name)

    app.include_router(router)

    @app.exception_handler(ValueError)
    async def on_value_error(_request: Request, exc: ValueError) -> Response:  # ERR-001 passes
        return JSONResponse({"error": str(exc)}, status_code=400)

    return app


def _client(state_dir: Path, app: FastAPI | None = None, **options: Any) -> tuple[TestClient, Any]:
    app = app or _app()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "state_dir": str(state_dir), **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False), handle.context


def _ids(report: dict[str, Any]) -> set[str]:
    return {r["id"] for r in report["results"]}


def test_get_before_scan_not_scanned(tmp_state_dir: Path):
    client, _ = _client(tmp_state_dir)
    report = client.get(API).json()
    assert (report["scan"]["status"], report["results"]) == ("NOT_SCANNED", [])


def test_scan_finds_fastapi_violations(tmp_state_dir: Path):
    client, _ = _client(tmp_state_dir)
    resp = client.post(f"{API}/scan")
    assert resp.status_code == 200
    report = resp.json()
    assert {"RAPI-PAGE-001", "RAPI-DTO-001", "RAPI-RESP-001", "RAPI-RESP-006"} <= _ids(report)
    assert "RAPI-ERR-001" not in _ids(report)
    assert report["handlersAnalyzed"] == 5  # sharpit's own routes and FastAPI's docs routes are not counted
    dto = next(r for r in report["results"] if r["id"] == "RAPI-DTO-001")
    assert dto["violationCount"] == 2
    assert client.get(API).json()["scan"]["status"] == "SCANNED"  # cached


def test_generic_types_unwrapped(tmp_state_dir: Path):
    client, _ = _client(tmp_state_dir)
    report = client.post(f"{API}/scan").json()
    dto = next(r for r in report["results"] if r["id"] == "RAPI-DTO-001")
    assert any("read_rows" in v for v in dto["sampleViolations"])
    assert any("read_row " in v for v in dto["sampleViolations"])
    page = next(r for r in report["results"] if r["id"] == "RAPI-PAGE-001")
    assert any("read_pets" in v for v in page["sampleViolations"])


def test_openapi_never_called(tmp_state_dir: Path, monkeypatch: pytest.MonkeyPatch):
    app = _app()

    def boom() -> dict[str, Any]:
        raise AssertionError("app.openapi() must never be called")

    monkeypatch.setattr(app, "openapi", boom)
    client, _ = _client(tmp_state_dir, app)
    assert client.post(f"{API}/scan").status_code == 200


def test_framework_routes_excluded(tmp_state_dir: Path):
    app = FastAPI()  # only FastAPI's own docs routes, plus sharpit's mount

    @app.exception_handler(ValueError)
    async def on_value_error(_request: Request, exc: ValueError) -> Response:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({}, status_code=400)

    client, _ = _client(tmp_state_dir, app)
    report = client.post(f"{API}/scan").json()
    assert (report["handlersAnalyzed"], report["results"]) == (0, [])


def test_mounted_app_without_routes_is_a_limitation(tmp_state_dir: Path):
    app = _app()

    async def raw(scope: Any, receive: Any, send: Any) -> None:  # an opaque ASGI app: nothing to inspect
        return None

    app.mount("/legacy", raw)
    client, _ = _client(tmp_state_dir, app)
    report = client.post(f"{API}/scan").json()
    assert report["scan"]["status"] == "PARTIAL"
    assert report["evidence"]["limitations"] == ["Mounted application at /legacy has no inspectable routes."]


def test_scan_409_when_busy(tmp_state_dir: Path):
    client, ctx = _client(tmp_state_dir)
    release = ctx.lazy(f"singleflight:{OPERATION}", SingleFlight).try_acquire(OPERATION)
    assert release is not None
    try:
        resp = client.post(f"{API}/scan")
        assert resp.status_code == 409
        assert resp.json()["operation"] == OPERATION
    finally:
        release()
    assert client.post(f"{API}/scan").status_code == 200


def test_scan_read_only_403(tmp_state_dir: Path):
    client, _ = _client(tmp_state_dir, panels={"rest-api": {"read_only": True}})
    resp = client.post(f"{API}/scan")
    assert resp.status_code == 403
    assert client.get(API).status_code == 200


def test_violations_paging_and_errors(tmp_state_dir: Path):
    client, _ = _client(tmp_state_dir)
    rule = "RAPI-DTO-001"
    assert client.get(f"{API}/rules/{rule}/violations", params={"scanId": "x"}).status_code == 409  # no scan yet
    scan_id = client.post(f"{API}/scan").json()["violationDetails"]["scanId"]
    first = client.get(f"{API}/rules/{rule}/violations", params={"scanId": scan_id, "limit": 1})
    assert first.status_code == 200
    body = first.json()
    assert (body["ruleId"], body["violationCount"], len(body["violations"])) == (rule, 2, 1)
    assert body["page"]["hasMore"] is True
    second = client.get(f"{API}/rules/{rule}/violations", params={"scanId": scan_id, "offset": 1, "limit": 1}).json()
    assert second["violations"] != body["violations"]
    for params, status in (
        ({}, 400),  # blank scanId
        ({"scanId": scan_id, "offset": "-1"}, 400),
        ({"scanId": scan_id, "limit": "0"}, 400),
        ({"scanId": scan_id, "limit": "x"}, 400),
        ({"scanId": "stale"}, 409),
    ):
        resp = client.get(f"{API}/rules/{rule}/violations", params=params)
        assert resp.status_code == status, (params, resp.text)
        assert set(resp.json()) == {"error"}
    resp = client.get(f"{API}/rules/RAPI-MAP-002/violations", params={"scanId": scan_id})
    assert (resp.status_code, resp.json()) == (404, {"error": "Advisor rule has no findings in the current scan."})


def test_unregistered_rapi_id_violations_404_dismissal_400(tmp_state_dir: Path):
    client, _ = _client(tmp_state_dir)
    scan_id = client.post(f"{API}/scan").json()["violationDetails"]["scanId"]
    resp = client.get(f"{API}/rules/RAPI-MAP-004/violations", params={"scanId": scan_id})
    assert (resp.status_code, resp.json()) == (404, {"error": "Advisor rule has no findings in the current scan."})
    assert client.post("/sharpit/api/dismissed-rules/RAPI-MAP-004").status_code == 400


def test_dismiss_restore_changes_counts(tmp_state_dir: Path):
    client, _ = _client(tmp_state_dir)
    before = client.post(f"{API}/scan").json()["violationsFound"]
    assert client.post("/sharpit/api/dismissed-rules/RAPI-DTO-001").status_code == 200
    report = client.get(API).json()
    assert report["violationsFound"] == before - 1
    assert next(r for r in report["results"] if r["id"] == "RAPI-DTO-001")["dismissed"] is True
    assert client.delete("/sharpit/api/dismissed-rules/RAPI-DTO-001").status_code == 200
    assert client.get(API).json()["violationsFound"] == before


def test_get_rest_api_report_mcp_never_scans(tmp_state_dir: Path):
    client, ctx = _client(tmp_state_dir)
    call = CallContext(ctx, {})
    assert call_tool(call, "get_rest_api_report", {}, via="mcp")["scan"]["status"] == "NOT_SCANNED"
    with pytest.raises(ToolCallError) as stale:
        call_tool(call, "get_rest_api_rule_violations", {"id": "RAPI-DTO-001", "scanId": "x"}, via="mcp")
    assert stale.value.status == 409
    assert call_tool(call, "get_rest_api_report", {}, via="mcp")["scan"]["status"] == "NOT_SCANNED"  # still
    scan_id = call_tool(call, "rest_api_scan", {}, via="cli")["violationDetails"]["scanId"]
    page = call_tool(
        call, "get_rest_api_rule_violations", {"id": "RAPI-DTO-001", "scanId": scan_id, "limit": 1}, via="mcp"
    )
    assert (page["violationCount"], len(page["violations"]), page["page"]["hasMore"]) == (2, 1, True)
    with pytest.raises(ToolCallError) as unknown:
        call_tool(call, "get_rest_api_rule_violations", {"id": "RAPI-NOPE-1", "scanId": scan_id}, via="mcp")
    assert unknown.value.status == 404
    assert client.get(API).json()["violationDetails"]["scanId"] == scan_id
