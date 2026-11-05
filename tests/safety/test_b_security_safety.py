"""``security`` advisor reads have no side effects; its scan is CLI-only and gated (lane B-security)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install

PANEL = "security"
GET_ROWS = ["/sharpit/api/security", "/sharpit/api/security/rules/{rule_id}/violations"]
WRITE_ROWS = [("POST", "/sharpit/api/security/scan")]
PATH_PARAMS = {"rule_id": "SEC-CORS-002"}
CLI_ACTIONS = ["security_scan"]


def _violating_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
    app.get("/items")(lambda: "items")
    return app


def _args(scanned: dict[str, Any]) -> dict[str, Any]:
    results = scanned["results"]
    return {"id": results[0]["id"] if results else "SEC-FAPI-001", "scanId": scanned["violationDetails"]["scanId"]}


def _tool_args(handle: Any) -> dict[str, Any]:
    from sharpit.engine.tools04.security import security_service  # noqa: PLC0415 - only while the flag is on

    return _args(security_service(handle.context).scan())


def _tool_seed(ctx: Any) -> dict[str, Any]:
    """A bare context has no app: seed the service with one violating app's inputs, then scan it."""
    from sharpit.engine.advisors.dismissals import DismissalStore  # noqa: PLC0415
    from sharpit.engine.collectors.security import Inputs  # noqa: PLC0415
    from sharpit.engine.collectors.security.report import SecurityService  # noqa: PLC0415
    from sharpit.engine.singleflight import SingleFlight  # noqa: PLC0415
    from sharpit.fastapi.introspector import FastApiIntrospector  # noqa: PLC0415

    introspector = FastApiIntrospector(_violating_app())
    inputs = Inputs(introspector.security_model(), introspector.security_facts(), None)
    store = DismissalStore(Path(ctx.settings.state_dir))
    service = ctx.lazy(
        "security", lambda: SecurityService(lambda: inputs, store, ctx.masker, SingleFlight(), max_retained=100)
    )
    return _args(service.scan())


TOOL_ARGS = {"get_security_rule_violations": _tool_args}
TOOL_SEEDS = {"get_security_rule_violations": _tool_seed}


def test_security_get_no_side_effects(no_side_effects: SideEffectGuard):
    app = _violating_app()
    install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        scanned = client.post("/sharpit/api/security/scan")
        assert scanned.status_code == 200, scanned.text
        scan_id = scanned.json()["violationDetails"]["scanId"]
        no_side_effects.block_network()
        statuses = [
            client.get("/sharpit/api/security").status_code,
            client.get("/sharpit/api/security/rules/SEC-CORS-002/violations", params={"scanId": scan_id}).status_code,
        ]
    assert statuses == [200, 200]
    assert no_side_effects.violations == []


def test_inactive_security_paths_404():
    # AGENTS.md safety model 1: an inactive sharpit answers the host's 404 on every path of this panel and its tools
    app = FastAPI()
    install(app, enabled="OFF", show_banner=False, config_scan=False, mcp_enabled="ON")
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_security_report"}}
    statuses = [
        client.get("/sharpit/api/security").status_code,
        client.get("/sharpit/api/security/rules/SEC-CORS-002/violations").status_code,
        client.post("/sharpit/api/security/scan").status_code,
        client.post("/sharpit/api/mcp", json=call).status_code,
    ]
    assert statuses == [404, 404, 404, 404]
