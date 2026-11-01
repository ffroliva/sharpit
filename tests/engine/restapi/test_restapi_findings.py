"""REST API advisor on the finding contract (0.3.0 spec §5.3, §5.5, §5.6).

The ``CASES`` table doubles as the per-rule target list: for every rule, one route set that triggers it and the
target each occurrence gets. Route rules target ``"<METHOD> <path>"`` (several methods sorted and joined with
``" | "``), ``RAPI-MAP-002`` the duplicated ``"<METHOD> <path>"``, and the two app-wide rules ``"application"``.
No ported rule is about a handler with no route, so none targets ``module:qualname`` today.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.findings import severity_counts_of
from sharpit.engine.collectors.restapi.rules import RULES, evaluate, violations
from sharpit.engine.collectors.restapi.service import RestApiService, assess
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.spi import ApiModel, ApiRouteInfo

APP_HANDLER = ("app.errors:on_error",)
LIMITATION = "Mounted application at /legacy has no inspectable routes."


class Pet:
    pass


class PetTable:
    __table__ = object()


def route(
    path: str = "/v1/pets", methods: Sequence[str] = ("GET",), name: str = "read_pets", **kw: Any
) -> ApiRouteInfo:
    fields: dict[str, Any] = {
        "status_code": None,
        "response_model": None,
        "return_annotation": Pet,
        "summary": "Documented",
        "tags": ("pets",),
        **kw,
    }
    return ApiRouteInfo(tuple(methods), path, f"app.pets:{name}", **fields)


# rule id -> (routes, exception handlers, expected target of each violation, in rule order)
CASES: dict[str, tuple[list[ApiRouteInfo], tuple[str, ...], list[str]]] = {
    "RAPI-MAP-001": ([route(methods=("POST", "GET"))], APP_HANDLER, ["GET /v1/pets | POST /v1/pets"]),
    "RAPI-MAP-002": ([route(), route(name="again")], APP_HANDLER, ["GET /v1/pets"]),
    "RAPI-MAP-003": ([route(name="delete_pet")], APP_HANDLER, ["GET /v1/pets"]),
    "RAPI-MAP-005": ([route("/v1/pets/")], APP_HANDLER, ["GET /v1/pets/"]),
    "RAPI-MAP-007": ([route(methods=("DELETE",), has_body=True)], APP_HANDLER, ["DELETE /v1/pets"]),
    "RAPI-MAP-010": ([route("/v1/files/{rest:path}")], APP_HANDLER, ["GET /v1/files/{rest:path}"]),
    "RAPI-MAP-011": ([route("/v1/a/{a}/b/{b}/c/{c}/d/{d}")], APP_HANDLER, ["GET /v1/a/{a}/b/{b}/c/{c}/d/{d}"]),
    "RAPI-NAME-001": ([route("/v1/getPets")], APP_HANDLER, ["GET /v1/getPets"]),
    "RAPI-NAME-002": ([route("/v1/pet", return_annotation=list[Pet])], APP_HANDLER, ["GET /v1/pet"]),
    "RAPI-NAME-003": ([route("/v1/petTypes")], APP_HANDLER, ["GET /v1/petTypes"]),
    "RAPI-RESP-001": ([route(methods=("POST",), name="create_pet")], APP_HANDLER, ["POST /v1/pets"]),
    "RAPI-RESP-002": ([route(methods=("DELETE",), return_annotation=type(None))], APP_HANDLER, ["DELETE /v1/pets"]),
    "RAPI-RESP-006": ([route(status_code=204, return_annotation=Pet)], APP_HANDLER, ["GET /v1/pets"]),
    "RAPI-DTO-001": ([route(response_model=PetTable)], APP_HANDLER, ["GET /v1/pets"]),
    "RAPI-DTO-002": ([route(return_annotation=None)], APP_HANDLER, ["GET /v1/pets"]),
    "RAPI-PAGE-001": ([route(return_annotation=list[Pet])], APP_HANDLER, ["GET /v1/pets"]),
    "RAPI-VER-001": ([route("/pets")], APP_HANDLER, ["application"]),
    "RAPI-ERR-001": ([route()], (), ["application"]),
    "RAPI-DOC-001": ([route(summary=None)], APP_HANDLER, ["GET /v1/pets"]),
    "RAPI-DOC-002": ([route(tags=())], APP_HANDLER, ["GET /v1/pets"]),
}

# the 0.2.0 violation strings for CASES, frozen from the code before this change
FROZEN_TEXT: dict[str, list[str]] = {
    "RAPI-DOC-001": ["app.pets:read_pets [GET /v1/pets] — no summary or description"],
    "RAPI-DOC-002": ["app.pets:read_pets [GET /v1/pets] — no tags"],
    "RAPI-DTO-001": ["app.pets:read_pets [GET /v1/pets] — returns persistence class PetTable"],
    "RAPI-DTO-002": ["app.pets:read_pets [GET /v1/pets] — no response model or return annotation"],
    "RAPI-ERR-001": [
        "No application-wide exception handler was registered in app.exception_handlers for 1 route handler(s)."
    ],
    "RAPI-MAP-001": ["app.pets:read_pets [POST GET /v1/pets] — GET combined with POST"],
    "RAPI-MAP-002": ["GET /v1/pets with matching dispatch conditions handled by app.pets:read_pets, app.pets:again"],
    "RAPI-MAP-003": ["app.pets:delete_pet [GET /v1/pets] — mutation-like name on GET"],
    "RAPI-MAP-005": ["app.pets:read_pets [GET /v1/pets/] — trailing slash"],
    "RAPI-MAP-007": ["app.pets:read_pets [DELETE /v1/pets] — request body on DELETE"],
    "RAPI-MAP-010": ["app.pets:read_pets [GET /v1/files/{rest:path}] — catch-all path parameter"],
    "RAPI-MAP-011": ["app.pets:read_pets [GET /v1/a/{a}/b/{b}/c/{c}/d/{d}] — 4 levels of collection/{id} nesting"],
    "RAPI-NAME-001": ["app.pets:read_pets [GET /v1/getPets] — verb in path"],
    "RAPI-NAME-002": ["app.pets:read_pets [GET /v1/pet] — singular collection name 'pet'"],
    "RAPI-NAME-003": ["app.pets:read_pets [GET /v1/petTypes] — segment 'petTypes' is not lowercase kebab-case"],
    "RAPI-PAGE-001": [
        "app.pets:read_pets [GET /v1/pets] — collection response without limit/offset/page/cursor parameters"
    ],
    "RAPI-RESP-001": ["app.pets:create_pet [POST /v1/pets] — creation-like POST with the default 200 status"],
    "RAPI-RESP-002": ["app.pets:read_pets [DELETE /v1/pets] — DELETE with the default 200 status and no response body"],
    "RAPI-RESP-006": ["app.pets:read_pets [GET /v1/pets] — 204 declared with a content-capable return type"],
    "RAPI-VER-001": [
        "No API version signal (no /vN path, version header/param, or versioned media type) was "
        "detected across 1 handler(s)."
    ],
}

# frozen fingerprints (sha256 of rule, target, "" computed independently of the code)
FROZEN_FINGERPRINTS: dict[str, str] = {
    "RAPI-DOC-001": "rest-api:RAPI-DOC-001:d6900900c9dc9df4",
    "RAPI-DOC-002": "rest-api:RAPI-DOC-002:efbf3d8a5e791f62",
    "RAPI-DTO-001": "rest-api:RAPI-DTO-001:9f4d91b35e73e822",
    "RAPI-DTO-002": "rest-api:RAPI-DTO-002:f343b4f44cffcb55",
    "RAPI-ERR-001": "rest-api:RAPI-ERR-001:87254157ae547365",
    "RAPI-MAP-001": "rest-api:RAPI-MAP-001:d67b3bc552e9b6de",
    "RAPI-MAP-002": "rest-api:RAPI-MAP-002:98f3455ef40e7396",
    "RAPI-MAP-003": "rest-api:RAPI-MAP-003:af725f599da4413a",
    "RAPI-MAP-005": "rest-api:RAPI-MAP-005:251bed2ea5bb42db",
    "RAPI-MAP-007": "rest-api:RAPI-MAP-007:9541c9fadf6a5dc4",
    "RAPI-MAP-010": "rest-api:RAPI-MAP-010:f96c9d051567f3a8",
    "RAPI-MAP-011": "rest-api:RAPI-MAP-011:c9a72e74bb6b7dab",
    "RAPI-NAME-001": "rest-api:RAPI-NAME-001:feacef0115f2d48f",
    "RAPI-NAME-002": "rest-api:RAPI-NAME-002:1c029f31f03e7e1b",
    "RAPI-NAME-003": "rest-api:RAPI-NAME-003:b852598fd1d0d646",
    "RAPI-PAGE-001": "rest-api:RAPI-PAGE-001:e00cb87448c015fb",
    "RAPI-RESP-001": "rest-api:RAPI-RESP-001:036b89f56cd649a6",
    "RAPI-RESP-002": "rest-api:RAPI-RESP-002:2153958625930ed9",
    "RAPI-RESP-006": "rest-api:RAPI-RESP-006:23f0a67feddf63df",
    "RAPI-VER-001": "rest-api:RAPI-VER-001:222e408e5ca73df7",
}


def _masker() -> Masker:
    return Masker(Exposure.MASKED, True)


def _case_findings(rule_id: str) -> list[str]:
    routes, handlers, _ = CASES[rule_id]
    found, _errored = evaluate(routes, handlers)
    return [v.target for v in found[rule_id]]


def test_cases_cover_every_rule():
    assert set(CASES) == {r.id for r in RULES}


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_targets_per_rule(rule_id: str):
    assert _case_findings(rule_id) == CASES[rule_id][2]


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_violation_text_unchanged(rule_id: str):
    routes, handlers, _ = CASES[rule_id]
    found, _errored = evaluate(routes, handlers)
    assert [v.text for v in found[rule_id]] == FROZEN_TEXT[rule_id]
    assert violations(routes, handlers)[rule_id] == FROZEN_TEXT[rule_id]


def test_counts_never_appear_in_a_target():
    routes, handlers, _ = CASES["RAPI-VER-001"]
    found, _errored = evaluate([*routes, route("/owners")], handlers)
    assert {v.target for v in found["RAPI-VER-001"]} == {"application"}


def _model(
    routes: Sequence[ApiRouteInfo], handlers: Sequence[str] = APP_HANDLER, limitations: Sequence[str] = ()
) -> ApiModel:
    return ApiModel(tuple(routes), tuple(handlers), tuple(limitations))


def _fingerprints(rule_id: str) -> list[str]:
    routes, handlers, _ = CASES[rule_id]
    return [f.fingerprint for f in assess(_model(routes, handlers), _masker()).findings if f.rule_id == rule_id]


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_fingerprints_golden(rule_id: str):
    assert _fingerprints(rule_id) == [FROZEN_FINGERPRINTS[rule_id]] * len(CASES[rule_id][2])


def test_no_routes_is_confirmed_empty():
    # ported: RestApiScannerTests.scanWithNoControllersProducesEmptyScannedReport (usable false, coverage complete)
    run = assess(_model([]), _masker())
    assert run.evidence == {"usable": False, "coverageComplete": True, "limitations": []}
    assert run.status == "PASSED"
    assert run.findings == ()


def test_partial_scan_is_unknown():
    run = assess(_model([route()], limitations=[LIMITATION]), _masker(), fail_on="CRITICAL")
    assert run.status == "UNKNOWN"
    assert run.reason == LIMITATION


def test_partial_scan_with_gate_finding_still_fails():
    run = assess(_model([route(), route(name="again")], limitations=[LIMITATION]), _masker())
    assert run.status == "FAILED"  # RAPI-MAP-002 is HIGH


def test_assess_masks_the_message():
    secret = route("/v1/pets/token=ghp_abcdefghijklmnopqrstuvwxyz0123456789")
    run = assess(_model([secret]), _masker())
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in str(run.to_dto())


def test_dismissed_set_marks_rule_and_fingerprint():
    routes = [route("/v1/getPets", name="read_pets"), route("/v1/getOwners", name="read_owners")]  # two NAME-001
    both = [f.fingerprint for f in assess(_model(routes), _masker()).findings if f.rule_id == "RAPI-NAME-001"]
    assert len(set(both)) == 2
    by_fingerprint = assess(_model(routes), _masker(), dismissed=both[:1])
    by_rule = assess(_model(routes), _masker(), dismissed=["RAPI-NAME-001"])
    assert [f.fingerprint for f in by_fingerprint.findings if f.dismissed] == both[:1]
    assert {f.rule_id for f in by_rule.findings if f.dismissed} == {"RAPI-NAME-001"}
    assert sum(f.dismissed for f in by_rule.findings if f.rule_id == "RAPI-NAME-001") == 2


# --- the service (single-flight, cached) -----------------------------------------------------------------------

PETS = (
    route("/v1/get-pets", name="read_pets"),  # NAME-001 (INFO)
    route("/v1/get-owners", name="read_owners"),  # NAME-001 (INFO)
    route("/v1/petTypes", name="read_types"),  # NAME-003 (INFO)
    route("/v1/owners/{id}", name="delete_owner"),  # MAP-003 (LOW)
    route("/v1/a", name="read_a", tags=()),  # DOC-002 (INFO)
)


def _service(tmp_path: Path, routes: Sequence[ApiRouteInfo] = PETS, limitations: Sequence[str] = ()) -> RestApiService:
    model = _model(routes, limitations=limitations)
    return RestApiService(lambda: model, DismissalStore(tmp_path), _masker(), SingleFlight(), max_retained=10000)


def test_assess_matches_run(tmp_path: Path):
    run = _service(tmp_path).run()
    assert run.findings == assess(_model(PETS), _masker()).findings
    assert run.status == "PASSED"


def test_run_is_cached_for_the_panel(tmp_path: Path):
    service = _service(tmp_path)
    run = service.run()
    assert service.report()["violationsFound"] == len({f.rule_id for f in run.findings})


def test_panel_dto_shape_unchanged(tmp_path: Path):
    report = _service(tmp_path).scan()
    assert list(report) == [
        "localOnly",
        "disclaimer",
        "basePackages",
        "controllersAnalyzed",
        "handlersAnalyzed",
        "rulesEvaluated",
        "violationsFound",
        "severityCounts",
        "scan",
        "results",
        "evidence",
        "violationDetails",
    ]
    assert list(report["results"][0]) == [
        "id",
        "name",
        "category",
        "severity",
        "description",
        "status",
        "violationCount",
        "sampleViolations",
        "recommendation",
        "learnMoreUrl",
        "dismissed",
    ]


def _page(service: RestApiService, rule_id: str, offset: int | None = None, limit: int | None = None) -> dict[str, Any]:
    """A page of the cached scan's retained violations; the scan runs on first use."""
    scan_id = service.scan()["violationDetails"]["scanId"]
    page = service.violations(rule_id, scan_id, offset, limit, 1000)
    assert "fingerprints" in page
    return page


def _result(report: dict[str, Any], rule_id: str) -> dict[str, Any]:
    return next(r for r in report["results"] if r["id"] == rule_id)


def test_retained_page_has_fingerprints(tmp_path: Path):
    service = _service(tmp_path)
    page = _page(service, "RAPI-NAME-001")
    expected = [f.fingerprint for f in service.run().findings if f.rule_id == "RAPI-NAME-001"]
    assert page["fingerprints"] == expected
    assert len(page["fingerprints"]) == len(page["violations"])


def test_retained_page_fingerprints_follow_the_page_window(tmp_path: Path):
    service = _service(tmp_path)
    everything = _page(service, "RAPI-NAME-001")
    second = _page(service, "RAPI-NAME-001", 1, 1)
    assert second["fingerprints"] == everything["fingerprints"][1:2]


def test_fingerprint_dismissal_reduces_panel_count(tmp_path: Path):
    service = _service(tmp_path)
    page = _page(service, "RAPI-NAME-001")
    assert _result(service.report(), "RAPI-NAME-001")["violationCount"] == 2
    service.dismissals.add(page["fingerprints"][0])
    after = service.report()
    result = _result(after, "RAPI-NAME-001")
    assert result["violationCount"] == 1
    assert result["sampleViolations"] == [page["violations"][1]]
    assert result["dismissed"] is False
    assert {c["severity"]: c["count"] for c in after["severityCounts"]}["INFO"] == 3  # 4 INFO minus the dismissed one


def test_every_occurrence_dismissed_marks_the_rule(tmp_path: Path):
    service = _service(tmp_path)
    for fingerprint in _page(service, "RAPI-NAME-001")["fingerprints"]:
        service.dismissals.add(fingerprint)
    assert _result(service.report(), "RAPI-NAME-001")["dismissed"] is True


def test_panel_and_report_severity_counts_equal(tmp_path: Path):
    """5.6: the panel's ``severityCounts`` and the report's agree for the same app and dismissals."""
    service = _service(tmp_path)
    service.dismissals.add(_page(service, "RAPI-NAME-001")["fingerprints"][0])
    service.dismissals.add("RAPI-DOC-002")
    run = assess(_model(PETS), _masker(), dismissed=service.dismissals.list())
    assert service.report()["severityCounts"] == severity_counts_of(run.findings)
