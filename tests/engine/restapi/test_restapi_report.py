"""REST API report and service (port of BootUI ``RestApiScanner`` report building, ``applyDismissals`` and the
``RestApiReport`` shape). The service reads an ``ApiModel`` callable: no FastAPI here."""

from pathlib import Path

import pytest

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.collectors.restapi.report import DISCLAIMER, NOT_SCANNED_MESSAGE
from sharpit.engine.collectors.restapi.service import OPERATION, RestApiService
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.singleflight import ActionBusy, SingleFlight
from sharpit.engine.spi import ApiModel, ApiRouteInfo

REPORT_KEYS = {
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
}
SCAN_KEYS = {
    "analyzer",
    "status",
    "message",
    "scannedAt",
    "rulesEvaluated",
    "controllersAnalyzed",
    "handlersAnalyzed",
    "violationsFound",
}


class Pet:
    pass


def _route(path: str, name: str, module: str = "app.pets", **kw: object) -> ApiRouteInfo:
    fields: dict[str, object] = {"summary": "s", "tags": ("pets",), "return_annotation": Pet, **kw}
    return ApiRouteInfo(("GET",), path, f"{module}:{name}", **fields)  # type: ignore[arg-type]


ROUTES = (
    _route("/v1/get-pets", "read_pets"),  # NAME-001 (INFO)
    _route("/v1/petTypes", "read_types", "app.types"),  # NAME-003 (INFO)
    _route("/v1/owners", "read_owners", "other.owners", tags=()),  # DOC-002 (INFO)
    _route("/v1/owners/{id}", "delete_owner", "other.owners"),  # MAP-003 (LOW)
    _route("/v1/a", "read_a"),
)
HANDLERS = ("app.errors:on_error",)


def _service(tmp_path: Path, routes: tuple[ApiRouteInfo, ...] = ROUTES, **kw: object) -> RestApiService:
    model = ApiModel(routes, HANDLERS, tuple(kw.pop("limitations", ())))  # type: ignore[arg-type]
    return RestApiService(
        lambda: model, DismissalStore(tmp_path), Masker(Exposure.MASKED, True), SingleFlight(), max_retained=10000
    )


def test_get_before_scan_not_scanned(tmp_path: Path):
    report = _service(tmp_path).report()
    assert set(report) == REPORT_KEYS and set(report["scan"]) == SCAN_KEYS
    assert report["scan"] == {
        "analyzer": "sharpit rest-api",
        "status": "NOT_SCANNED",
        "message": NOT_SCANNED_MESSAGE,
        "scannedAt": None,
        "rulesEvaluated": 0,
        "controllersAnalyzed": 0,
        "handlersAnalyzed": 0,
        "violationsFound": 0,
    }
    assert (report["results"], report["violationsFound"], report["localOnly"]) == ([], 0, True)
    assert report["evidence"] == {
        "usable": False,
        "coverageComplete": False,
        "limitations": ["Assessment evidence is unavailable."],
    }
    assert report["violationDetails"]["scanId"] is None


def test_shape_keys_match_bootui(tmp_path: Path):
    # ported: RestApiReport and RestApiScanStatusDto components (+ RESULT_KEYS for RestApiRuleResultDto)
    report = _service(tmp_path).scan()
    assert set(report) == REPORT_KEYS and set(report["scan"]) == SCAN_KEYS
    assert set(report["results"][0]) == RESULT_KEYS
    assert report["disclaimer"] == DISCLAIMER
    assert (report["basePackages"], report["controllersAnalyzed"], report["handlersAnalyzed"]) == (
        ["app", "other"],
        3,
        5,
    )
    assert report["rulesEvaluated"] == report["scan"]["rulesEvaluated"] == 20
    assert report["scan"]["status"] == "SCANNED" and isinstance(report["scan"]["scannedAt"], int)
    assert report["scan"]["message"] == (
        "REST API rules completed against 3 module(s) and 5 route handler(s) in the host application."
    )
    ids = [r["id"] for r in report["results"]]
    assert ids == ["RAPI-MAP-003", "RAPI-DOC-002", "RAPI-NAME-001", "RAPI-NAME-003"]  # severity, then count, then id
    assert all(r["status"] == "FAILED" and r["dismissed"] is False for r in report["results"])
    assert report["violationsFound"] == report["scan"]["violationsFound"] == 4
    assert {c["severity"]: c["count"] for c in report["severityCounts"]} == {
        "CRITICAL": 0,
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 1,
        "INFO": 3,
    }
    assert report["evidence"] == {"usable": True, "coverageComplete": True, "limitations": []}
    details = report["violationDetails"]
    assert (details["total"], details["retained"], details["truncated"]) == (4, 4, False)


def test_dismiss_restore_changes_counts(tmp_path: Path):
    service = _service(tmp_path)
    service.scan()
    service.dismissals.add("RAPI-NAME-001")
    report = service.report()
    assert report["violationsFound"] == 3
    assert next(r for r in report["results"] if r["id"] == "RAPI-NAME-001")["dismissed"] is True
    assert {c["severity"]: c["count"] for c in report["severityCounts"]}["INFO"] == 2
    service.dismissals.remove("RAPI-NAME-001")
    assert service.report()["violationsFound"] == 4


def test_violations_are_masked(tmp_path: Path):
    secret = _route("/v1/Token/password=hunter2", "read_token")  # NAME-003
    report = _service(tmp_path, (secret,)).scan()
    text = str(report)
    assert "hunter2" not in text and MASK in text


def test_limitations_mark_scan_partial(tmp_path: Path):
    report = _service(tmp_path, limitations=["Mounted application at /legacy has no inspectable routes."]).scan()
    assert report["scan"]["status"] == "PARTIAL"
    assert report["evidence"] == {
        "usable": True,
        "coverageComplete": False,
        "limitations": ["Mounted application at /legacy has no inspectable routes."],
    }


def test_no_routes(tmp_path: Path):
    report = _service(tmp_path, ()).scan()
    assert (report["scan"]["status"], report["rulesEvaluated"], report["results"]) == ("SCANNED", 0, [])
    assert report["scan"]["message"] == "No route handlers were found in the host application."


def test_violation_paging(tmp_path: Path):
    service = _service(tmp_path)
    scan_id = service.scan()["violationDetails"]["scanId"]
    page = service.violations("RAPI-NAME-001", scan_id, 0, 10, 1000)
    assert (page["violationCount"], page["violations"]) == (1, ["app.pets:read_pets [GET /v1/get-pets] — verb in path"])
    with pytest.raises(AdvisorViolationError) as missing:
        service.violations("RAPI-MAP-001", scan_id, None, None, 1000)
    assert missing.value.status == 404
    service.scan()
    with pytest.raises(AdvisorViolationError) as stale:
        service.violations("RAPI-NAME-001", scan_id, None, None, 1000)
    assert stale.value.status == 409


def test_scan_busy(tmp_path: Path):
    service = _service(tmp_path)
    release = service.single_flight.try_acquire(OPERATION)
    assert release is not None
    try:
        with pytest.raises(ActionBusy):
            service.scan()
    finally:
        release()
    assert service.scan()["scan"]["status"] == "SCANNED"


# derived: RestApiRuleResultDto components (review r0 finding 4)
RESULT_KEYS = {
    "id",
    "name",
    "category",
    "severity",
    "description",
    "recommendation",
    "learnMoreUrl",
    "status",
    "violationCount",
    "sampleViolations",
    "dismissed",
}


def test_result_keys_match_bootui(tmp_path: Path):
    # ported: RestApiRuleResultDto (11 components)
    assert set(_service(tmp_path).scan()["results"][0]) == RESULT_KEYS


def test_unknown_rule_violations_are_404(tmp_path: Path):
    # ported: AdvisorScanState.java:102 -- an unknown rule has no findings in the current scan (review r0 finding 1)
    service = _service(tmp_path)
    scan_id = service.scan()["violationDetails"]["scanId"]
    with pytest.raises(AdvisorViolationError) as unknown:
        service.violations("RAPI-NOPE-1", scan_id, None, None, 1000)
    assert (unknown.value.status, unknown.value.message) == (
        404,
        "Advisor rule has no findings in the current scan.",
    )


class _Meta(type):
    def __getattr__(cls, name: str) -> object:
        raise RuntimeError("lazy proxy")


class _Lazy(metaclass=_Meta):
    pass


def test_raising_rule_makes_scan_partial_not_crash(tmp_path: Path):
    # ported: RestApiScanner.evaluate catches per-rule failures and returns a PARTIAL report (review r0 finding 2)
    broken = ApiRouteInfo(("GET",), "/v1/things", "app.x:read_things", response_model=_Lazy)
    report = _service(tmp_path, (broken,)).scan()
    assert report["scan"]["status"] == "PARTIAL"
    assert "rule evaluation: required REST API evidence was unavailable." in report["evidence"]["limitations"]


def test_failed_build_leaves_retention_and_cache_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # a scan whose report cannot be built must not replace the retained details (review r0 finding 3)
    service = _service(tmp_path)
    first = service.scan()["violationDetails"]["scanId"]
    monkeypatch.setattr("sharpit.engine.collectors.restapi.service.report.build", lambda *a, **k: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        service.scan()
    assert service.report()["violationDetails"]["scanId"] == first
    assert service.violations("RAPI-NAME-001", first, None, None, 1000)["violationCount"] == 1  # still pages
