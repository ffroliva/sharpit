"""Safety rows for the architecture advisor panel (spec §4, §5.5)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install

PANEL = "architecture"
GET_ROWS = [
    "/sharpit/api/architecture",
    "/sharpit/api/architecture/rules/{rule_id}/violations",
]
WRITE_ROWS = [
    ("POST", "/sharpit/api/architecture/scan"),
]
PATH_PARAMS = {
    "rule_id": "ARCH-PKG-001",
}
CLI_ACTIONS = ("architecture_scan",)


def _seeded_violations(ctx: Any) -> dict[str, Any]:
    """Arguments for get_architecture_rule_violations: the context's architecture service, scanned.

    The sample app is built by a factory no module holds, so its own scan has no source to read; the service is
    seeded (before first use) with one evaluated finding, then scanned through its normal path.
    """
    from sharpit.engine.advisors.findings import Finding  # noqa: PLC0415
    from sharpit.engine.advisors.report import evidence  # noqa: PLC0415
    from sharpit.engine.advisors.scan import Evaluation  # noqa: PLC0415
    from sharpit.engine.collectors.architecture.report import (  # noqa: PLC0415
        RULES,
        ArchitectureScanDetail,
        ArchitectureService,
        architecture_service,
    )
    from sharpit.engine.singleflight import SingleFlight  # noqa: PLC0415
    from sharpit.engine.tools import dismissal_store  # noqa: PLC0415

    rule = RULES[0]  # ARCH-PKG-001
    finding = Finding(rule.id, "architecture", rule.severity, "app.a cycle", "Circular package dependency: a -> b -> a")
    done = Evaluation(
        "SCANNED", "seeded", (rule.id,), (finding,), evidence(True, True, []), ArchitectureScanDetail(2, ("app",))
    )
    ctx.lazy(
        "architecture",
        lambda: ArchitectureService(
            lambda: ["app"],
            dismissal_store(ctx),
            ctx.masker,
            SingleFlight(),
            max_retained=100,
            run_scan=lambda _r: done,
        ),
    )
    report = architecture_service(ctx).scan()
    assert report["results"], report
    return {"id": report["results"][0]["id"], "scanId": report["violationDetails"]["scanId"]}


TOOL_ARGS = {"get_architecture_rule_violations": lambda handle: _seeded_violations(handle.context)}
TOOL_SEEDS = {"get_architecture_rule_violations": _seeded_violations}

LOCAL = ("127.0.0.1", 50000)
PATHS = (
    "/sharpit/api/architecture",
    "/sharpit/api/architecture/rules/ARCH-PKG-001/violations",
)


def _client(**options: object) -> TestClient:
    app = FastAPI()
    install(app, show_banner=False, config_scan=False, **{"enabled": "ON", **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL)


@pytest.mark.parametrize("path", PATHS)
def test_cross_site_request_is_refused(path: str) -> None:
    # derived: guard chain runs on every request, including architecture routes
    response = _client().get(path, headers={"Origin": "http://evil.example"})
    assert response.status_code == 403
    assert response.json() == {"error": "sharpit rejected a cross-site request."}


@pytest.mark.parametrize("path", PATHS)
def test_inactive_install_answers_404(path: str) -> None:
    # derived: fails closed, an inactive mount answers 404 for every path
    assert _client(enabled="OFF").get(path).status_code == 404


def test_architecture_violations_tool_uses_rule_violations_schema() -> None:
    # derived: BootUiMcpService.schema RULE_VIOLATIONS, as get_rest_api_rule_violations (review fix 1: GET /cli 500)
    from sharpit.engine.tools import TOOLS  # noqa: PLC0415
    from sharpit.engine.tools04.architecture import TOOLS as ARCHITECTURE_TOOLS  # noqa: PLC0415

    rest_api = next(t for t in TOOLS if t.name == "get_rest_api_rule_violations")
    architecture = next(t for t in ARCHITECTURE_TOOLS if t.name == "get_architecture_rule_violations")

    assert architecture.input_schema == rest_api.input_schema
