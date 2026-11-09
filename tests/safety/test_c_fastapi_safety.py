"""Lane C-fastapi safety rows (spec §4.4, §5.6): the scan is POST/CLI-only; GETs serve the cached report."""

from __future__ import annotations

from typing import Any

# safety-matrix rows (tests/safety/__init__.py): read by the shared route-table tests while the flag is true
PANEL = "fastapi"
GET_ROWS = ["/sharpit/api/fastapi", "/sharpit/api/fastapi/rules/{rule_id}/violations"]
WRITE_ROWS = [("POST", "/sharpit/api/fastapi/scan")]
PATH_PARAMS = {"rule_id": "FASTAPI-ASYNC-002"}
CLI_ACTIONS = ["fastapi_scan"]


def _seeded_violations(ctx: Any) -> dict[str, Any]:
    """Arguments for get_fastapi_rule_violations: the context's fastapi advisor service, scanned.

    The sample app is built by a factory no module holds, so its own scan has no source to read; the service is
    seeded (before first use) with one evaluated finding, then scanned through its normal path.
    """
    from sharpit.engine.advisors.findings import Finding
    from sharpit.engine.advisors.report import evidence
    from sharpit.engine.advisors.scan import Evaluation
    from sharpit.engine.collectors.fastapi_advisor.report import RULES, FastapiAdvisor
    from sharpit.engine.singleflight import SingleFlight
    from sharpit.engine.tools import dismissal_store
    from sharpit.engine.tools04.fastapi import fastapi_service

    rule = RULES[1]  # FASTAPI-ASYNC-002
    finding = Finding(rule.id, "fastapi", rule.severity, "app.main:slow", "GET /slow (app.main:slow) calls time.sleep")
    done = Evaluation("SCANNED", "seeded", (rule.id,), (finding,), evidence(True, True, []), {})
    ctx.lazy(
        "fastapi-advisor",
        lambda: FastapiAdvisor(lambda _r: done, dismissal_store(ctx), ctx.masker, SingleFlight(), max_retained=100),
    )
    report = fastapi_service(ctx).scan()
    assert report["results"], report
    return {"id": report["results"][0]["id"], "scanId": report["violationDetails"]["scanId"]}


TOOL_ARGS = {"get_fastapi_rule_violations": lambda handle: _seeded_violations(handle.context)}
TOOL_SEEDS = {"get_fastapi_rule_violations": _seeded_violations}
