"""The advisor scan core and the ``RuleResult`` contract (0.5.0 spec §4.3, §4.4, §5 post-scan parity)."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from golden import ROOT, assert_enum_values, assert_parity
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope
from sharpit.engine.collectors.restapi.service import RestApiService
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.singleflight import ActionBusy, SingleFlight
from sharpit.engine.spi import ApiModel, ApiRouteInfo


class Pet:
    pass


def _rest_api_report(tmp_path: Path) -> dict[str, Any]:
    route = ApiRouteInfo(
        ("GET",), "/v1/get-pets", "app.pets:read_pets", summary="s", tags=("pets",), return_annotation=Pet
    )
    model = ApiModel((route,), ("app.errors:on_error",), ())
    service = RestApiService(
        lambda: model, DismissalStore(tmp_path), Masker(Exposure.MASKED, True), SingleFlight(), max_retained=10000
    )
    return service.scan()


def _enum_error(sharpit_id: str, payload: dict[str, Any]) -> str:
    try:
        assert_enum_values(sharpit_id, "captured", payload)
    except AssertionError as exc:
        return str(exc)
    return ""


def test_enum_values_checked_against_golden():
    golden = json.loads((ROOT / "rest-api" / "captured.json").read_text(encoding="utf-8"))
    assert _enum_error("rest-api", golden) == ""
    wrong = copy.deepcopy(golden)
    wrong["results"][0]["status"] = "FAILED"
    assert "results[].status" in _enum_error("rest-api", wrong)


def test_advisor_core_matches_rest_api_post_scan_golden(tmp_path: Path):
    report = _rest_api_report(tmp_path)
    assert report["results"][0]["status"] == "VIOLATION"
    assert "sampleLocations" in report["results"][0]
    assert_parity("rest-api", "captured", report)
    assert_enum_values("rest-api", "captured", report)


SECRET = "password=hunter2sharpit"
MASKER = Masker(Exposure.MASKED, True)
SPEC = ScanSpec("fake", "sharpit fake", "Fake advisor disclaimer.", "Fake advisor has not run yet.")
FAKE_RULES = (
    RuleDefinition("ADV-1", "One", "Category", "HIGH", "d", "r", "https://example.invalid/1"),
    RuleDefinition("ADV-2", "Two", "Category", "LOW", "d", "r", "https://example.invalid/2"),
)
_SUPPRESSION = {"suppressedFindings": 0, "incompleteRules": [], "findings": [], "omitted": 0}
# each 0.5.0 advisor's scope keys (lists, counts) and extra sections, as its pre-scan golden has them
GOLDEN_SCOPES: dict[str, tuple[Scope, dict[str, Any]]] = {
    "security": (Scope({"filterChains": []}, {"filterChainsAnalyzed": 0}), {"analysisErrors": []}),
    "architecture": (Scope({"basePackages": ["app"]}, {"classesAnalyzed": 0}), {"analysisErrors": []}),
    "fastapi": (Scope({"inspected": []}, {"componentsAnalyzed": 0}), {"analysisErrors": []}),
    "database-advisor": (
        Scope({"dataSourceNames": [], "dataSources": []}, {"tablesAnalyzed": 0}),
        {"rulesSkipped": 0, "rulesErrored": 0, "truncated": False, "diagnostics": [], "suppression": _SUPPRESSION},
    ),
}


def _finding(i: int) -> Finding:
    return Finding("ADV-1", "fake", "HIGH", f"target {i}", f"v {i}")


def _core(
    tmp_path: Path,
    done: Evaluation | None = None,
    scope: Scope | None = None,
    extra: dict[str, Any] | None = None,
) -> AdvisorScan:
    evaluation = done or Evaluation(
        "SCANNED", "Fake rules completed.", ("ADV-1", "ADV-2"), tuple(map(_finding, range(5))), evidence(True, True, [])
    )
    return AdvisorScan(
        SPEC,
        FAKE_RULES,
        lambda _request: evaluation,
        scope=lambda _done: scope or Scope({"basePackages": ["app"]}, {"classesAnalyzed": 1}),
        extra_sections=lambda _done: extra or {},
        dismissals=DismissalStore(tmp_path),
        masker=MASKER,
        single_flight=SingleFlight(),
        max_retained=10000,
    )


@pytest.mark.parametrize("sharpit_id", sorted(GOLDEN_SCOPES))
def test_advisor_core_pre_scan_shape_all_four_goldens(tmp_path: Path, sharpit_id: str):
    scope, extra = GOLDEN_SCOPES[sharpit_id]
    report = _core(tmp_path, scope=scope, extra=extra).report()
    assert_parity(sharpit_id, "captured", report)
    assert_enum_values(sharpit_id, "captured", report)


def test_advisor_core_single_flight(tmp_path: Path):
    # ported: ArchitectureScannerTests.duplicateScanFailsFastAndLaterRetryRuns
    core = _core(tmp_path)
    release = core.single_flight.try_acquire(SPEC.operation)
    assert release is not None
    busy = None
    try:
        core.scan()
    except ActionBusy as exc:
        busy = exc.body()["error"]
    finally:
        release()
    assert busy == "sharpit action already in progress"
    assert core.scan()["scan"]["status"] == "SCANNED"


def test_advisor_core_violations_paged(tmp_path: Path):
    core = _core(tmp_path)
    scan_id = core.scan()["violationDetails"]["scanId"]
    page = core.violations("ADV-1", scan_id, 1, 2)
    assert page["violations"] == ["v 1", "v 2"]
    assert page["violationCount"] == 5


def test_advisor_core_unknown_rule_404(tmp_path: Path):
    core = _core(tmp_path)
    scan_id = core.scan()["violationDetails"]["scanId"]
    status = None
    try:
        core.violations("NOPE-1", scan_id, None, None)
    except AdvisorViolationError as exc:
        status = exc.status
    assert status == 404


def test_advisor_core_masks_every_string(tmp_path: Path):
    secret = Finding("ADV-1", "fake", "HIGH", f"target {SECRET}", f"message {SECRET}")
    done = Evaluation("PARTIAL", f"scan {SECRET}", ("ADV-1",), (secret,), evidence(True, False, [f"limit {SECRET}"]))
    scope = Scope({"basePackages": [f"pkg {SECRET}"]}, {"classesAnalyzed": 1})
    core = _core(tmp_path, done, scope, {"analysisErrors": [{"detail": f"error {SECRET}"}]})
    report = core.scan()
    page = core.violations("ADV-1", report["violationDetails"]["scanId"], None, None)
    assert [r["sampleViolations"] for r in report["results"]] == [[MASKER.mask_text(f"message {SECRET}")]]
    assert "hunter2" not in json.dumps(report)
    assert "hunter2" not in json.dumps(core.report())
    assert "hunter2" not in json.dumps(page)
