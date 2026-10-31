"""VulnerabilityService (port of BootUI ``VulnerabilitiesController`` and the scan half of ``OsvVulnerabilityScanner``:
``scan``, ``fetchVulnerabilities``, ``enrich``, ``applyEpss``, ``scanMessage``; plus ``DependencyReports`` ordering,
evidence and ``applyDismissals``).

The real OSV and EPSS clients run against a fake opener routed by URL, so no socket is ever opened.
"""

import json
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from vulnfakes import FakeOpener, Reply, fixture_text

from conftest import SideEffectGuard, golden
from sharpit.engine.collectors.vulns.dismissals import DismissalStore
from sharpit.engine.collectors.vulns.epss import EpssClient
from sharpit.engine.collectors.vulns.inventory import Package
from sharpit.engine.collectors.vulns.osv import OsvClient
from sharpit.engine.collectors.vulns.service import OPERATION, VulnerabilityService, _valid_withdrawal  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.singleflight import ActionBusy, SingleFlight
from sharpit.settings import SharpitSettings

JINJA = Package("jinja2", "3.1.3", None)
FLASK = Package("flask", "3.0.0", None)
NO_EPSS: Reply = (200, '{"data": []}')
VULN_KEYS = {
    "id",
    "summary",
    "details",
    "severity",
    "score",
    "aliases",
    "references",
    "fixedVersions",
    "fixAvailable",
    "epssScore",
    "epssPercentile",
    "dismissed",
}


def advisory(vuln_id: str, pkg: Package, severity: str = "HIGH", aliases: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "id": vuln_id,
        "aliases": list(aliases),
        "database_specific": {"severity": severity},
        "affected": [{"package": {"ecosystem": "PyPI", "name": pkg.name}, "versions": [pkg.version]}],
    }


class FakeOsv:
    """Routes requests by URL: querybatch from ``ids`` (or the queued ``query`` replies), advisories from ``docs``."""

    def __init__(self, ids: dict[str, list[str]] | None = None, docs: dict[str, Any] | None = None) -> None:
        self.ids = ids or {}
        self.docs = docs or {}
        self.query: list[Reply] = []
        self.epss: Reply = NO_EPSS
        self.release: threading.Event | None = None  # when set, querybatch blocks until released (max 2 s)
        self.opener = FakeOpener(self)

    def __call__(self, request: urllib.request.Request) -> Reply:
        path = urllib.parse.urlsplit(request.full_url).path
        if path == "/v1/querybatch":
            if self.release is not None:
                self.release.wait(2.0)
            if self.query:
                return self.query.pop(0)
            queries = json.loads(request.data)["queries"]  # type: ignore[arg-type]
            results = [{"vulns": [{"id": i} for i in self.ids.get(q["package"]["name"], [])]} for q in queries]
            return 200, json.dumps({"results": results})
        if path.startswith("/v1/vulns/"):
            doc = self.docs.get(urllib.parse.unquote(path.removeprefix("/v1/vulns/")))
            if doc is None:
                return 404, "{}"
            return 200, doc if isinstance(doc, str) else json.dumps(doc)
        assert path == "/data/v1/epss", path
        return self.epss

    def paths(self) -> list[str]:
        return [urllib.parse.urlsplit(r.full_url).path for r in self.opener.requests]


def service(
    osv: FakeOsv, packages: list[Package], state_dir: Path, flight: SingleFlight | None = None, **settings: Any
) -> VulnerabilityService:
    return VulnerabilityService(
        SharpitSettings(**settings),
        OsvClient("http://osv.test", 2.0, osv.opener),
        EpssClient("http://epss.test", 2.0, osv.opener),
        lambda: list(packages),
        DismissalStore(state_dir),
        flight or SingleFlight(),
    )


def fixture_osv() -> FakeOsv:
    osv = FakeOsv(
        docs={
            "GHSA-h75v-3vvj-5mfj": fixture_text("osv/GHSA-h75v-3vvj-5mfj.json"),
            "PYSEC-2017-9999": fixture_text("osv/PYSEC-2017-9999.json"),
        }
    )
    osv.query = [(200, fixture_text("osv/querybatch.json"))]
    osv.epss = (200, fixture_text("epss/CVE-2024-34064.json"))
    return osv


def dep(report: dict[str, Any], name: str) -> dict[str, Any]:
    return next(d for d in report["dependencies"] if d["artifactId"] == name)


def test_get_never_network(no_side_effects: SideEffectGuard, tmp_state_dir: Path):
    osv = FakeOsv()
    svc = service(osv, [JINJA], tmp_state_dir)
    report = svc.report()
    assert report["scan"]["status"] == "NOT_SCANNED"
    assert svc.report() == report
    assert osv.opener.requests == []


def test_not_scanned_shape_matches_golden_keys(tmp_state_dir: Path):
    expected = golden("vulnerabilities")
    report = service(FakeOsv(), [JINJA, FLASK], tmp_state_dir).report()
    assert report.keys() == expected.keys()
    for key in ("scan", "coverage", "evidence"):
        assert report[key].keys() == expected[key].keys(), key
    assert report["dependencies"][0].keys() == expected["dependencies"][0].keys()
    assert report["dependencies"][0]["assessment"] == {"queryComplete": False, "detailAssessmentComplete": False}
    assert [c["severity"] for c in report["severityCounts"]] == [c["severity"] for c in expected["severityCounts"]]
    assert report["scan"] == {
        "scanner": "OSV.dev",
        "status": "NOT_SCANNED",
        "message": expected["scan"]["message"],
        "scannedAt": None,
        "packagesScanned": 0,
        "packagesSkipped": 0,
        "vulnerabilitiesFound": 0,
    }
    assert report["evidence"] == expected["evidence"]
    assert (report["scanningEnabled"], report["total"], report["vulnerable"]) == (True, 2, 0)
    assert report["dependencies"][0] | {"assessment": None} == {
        "groupId": "pypi",
        "artifactId": "flask",
        "version": "3.0.0",
        "packageName": "flask",
        "source": "importlib.metadata",
        "vulnerabilityCount": 0,
        "highestSeverity": "NONE",
        "vulnerabilities": [],
        "assessment": None,
    }


# ported: OsvVulnerabilityScannerTests.enrichesDependenciesWithOsvAdvisories
# ported: OsvVulnerabilityScannerTests.epssEnrichesCveAliasedVulnerabilityWithProbabilityAndPercentile
def test_scan_report_shape_matches_golden_keys(tmp_state_dir: Path):
    expected = golden("vulnerabilities")
    osv = fixture_osv()
    report = service(osv, [JINJA, FLASK], tmp_state_dir).scan()
    assert report.keys() == expected.keys()
    for key in ("scan", "coverage", "evidence"):
        assert report[key].keys() == expected[key].keys(), key
    jinja = dep(report, "jinja2")
    assert jinja.keys() == expected["dependencies"][0].keys()
    assert all(v.keys() == VULN_KEYS for v in jinja["vulnerabilities"])
    scan = report["scan"]
    assert scan["status"] == "SCANNED"
    assert scan["message"] == (
        "Scan completed against OSV.dev."
        " EPSS: 1 of 1 requested CVEs have scores; remaining CVEs have no available data."
    )
    assert isinstance(scan["scannedAt"], int) and scan["scannedAt"] > 0
    assert (scan["packagesScanned"], scan["packagesSkipped"], scan["vulnerabilitiesFound"]) == (2, 0, 1)
    assert (report["total"], report["vulnerable"]) == (2, 1)
    assert {c["severity"]: c["count"] for c in report["severityCounts"]} == {
        "CRITICAL": 0,
        "HIGH": 0,
        "MEDIUM": 1,
        "LOW": 0,
        "UNKNOWN": 0,
        "NONE": 0,
    }
    assert [d["artifactId"] for d in report["dependencies"]] == ["jinja2", "flask"]
    assert jinja["assessment"] == {"queryComplete": True, "detailAssessmentComplete": True}
    assert (jinja["vulnerabilityCount"], jinja["highestSeverity"]) == (1, "MEDIUM")
    (ghsa,) = jinja["vulnerabilities"]  # PYSEC-2017-9999 is withdrawn, so it is dropped
    assert (ghsa["id"], ghsa["severity"], ghsa["score"]) == ("GHSA-h75v-3vvj-5mfj", "MEDIUM", 5.4)
    assert (ghsa["fixedVersions"], ghsa["fixAvailable"]) == (["3.1.4"], True)
    assert (ghsa["epssScore"], ghsa["epssPercentile"], ghsa["dismissed"]) == (0.00045, 0.16372, False)
    assert report["evidence"] == {"usable": True, "coverageComplete": True, "limitations": []}
    assert osv.paths().count("/data/v1/epss") == 1


# ported: OsvVulnerabilityScannerTests.ordersVulnerabilitiesBySeverityRankNotAlphabetically
def test_ordering_as_bootui(tmp_state_dir: Path):
    zeta, alpha = Package("zeta", "1.0", None), Package("alpha", "1.0", None)
    beta9, beta10, gamma = Package("beta", "1.9", None), Package("beta", "1.10", None), Package("gamma", "2.0", None)
    osv = FakeOsv(
        ids={"zeta": ["V-B", "V-A", "V-C"], "beta": ["V-BETA"], "gamma": ["V-GAMMA"]},
        docs={
            "V-A": advisory("V-A", zeta, "CRITICAL"),
            "V-B": advisory("V-B", zeta, "LOW"),
            "V-C": advisory("V-C", zeta, "CRITICAL"),
            "V-BETA": {
                **advisory("V-BETA", beta9),
                "affected": [{"package": {"ecosystem": "PyPI", "name": "beta"}, "versions": ["1.9", "1.10"]}],
            },
            "V-GAMMA": advisory("V-GAMMA", gamma),
        },
    )
    svc = service(osv, [alpha, gamma, beta10, zeta, beta9], tmp_state_dir)
    report = svc.scan()
    order = [(d["packageName"], d["version"]) for d in report["dependencies"]]
    assert order == [("zeta", "1.0"), ("beta", "1.9"), ("beta", "1.10"), ("gamma", "2.0"), ("alpha", "1.0")]
    assert [v["id"] for v in dep(report, "zeta")["vulnerabilities"]] == ["V-A", "V-C", "V-B"]

    svc.dismissals.add("V-A::pypi:zeta")
    zeta_dto = dep(svc.report(), "zeta")
    assert [v["id"] for v in zeta_dto["vulnerabilities"]] == ["V-C", "V-B", "V-A"]
    assert zeta_dto["highestSeverity"] == "CRITICAL"


# ported: OsvVulnerabilityScannerTests.epssFailureDoesNotDegradeScanStatusOrDiscardOsvResults
def test_epss_failure_keeps_osv(tmp_state_dir: Path):
    osv = fixture_osv()
    osv.epss = (500, "{}")
    report = service(osv, [JINJA, FLASK], tmp_state_dir).scan()
    assert report["scan"]["status"] == "SCANNED"
    assert report["scan"]["message"].endswith(
        " EPSS: 0 of 1 requested CVEs have scores; enrichment was incomplete or unavailable."
    )
    assert [v["epssScore"] for v in dep(report, "jinja2")["vulnerabilities"]] == [None]
    assert dep(report, "jinja2")["vulnerabilityCount"] == 1


# ported: OsvVulnerabilityScannerTests.epssDisabledSkipsTheEpssRequestEntirely
def test_epss_disabled_skips_request(tmp_state_dir: Path):
    osv = fixture_osv()
    report = service(osv, [JINJA, FLASK], tmp_state_dir, vulnerabilities_epss_enabled=False).scan()
    assert report["scan"]["message"] == "Scan completed against OSV.dev."
    assert "/data/v1/epss" not in osv.paths()


# ported: OsvVulnerabilityScannerTests.reportsErrorWithoutDroppingDependencyInventory
def test_osv_failure_reports_status_and_releases_lock(tmp_state_dir: Path):
    osv = FakeOsv(ids={"jinja2": ["V-1"]}, docs={"V-1": advisory("V-1", JINJA)})
    osv.query = [(503, "busy")]
    svc = service(osv, [JINJA, FLASK], tmp_state_dir)
    failed = svc.scan()
    assert failed["scan"]["status"] == "ERROR"
    assert failed["scan"]["message"] == "OSV scan failed: OSV query returned HTTP 503"
    assert failed["total"] == 2 and failed["dependencies"][0]["vulnerabilities"] == []
    assert failed["evidence"] == {
        "usable": False,
        "coverageComplete": False,
        "limitations": ["Assessment evidence is unavailable."],
    }
    assert svc.report()["scan"]["status"] == "ERROR"  # ERROR is cached

    again = svc.scan()  # the single-flight lock was released
    assert again["scan"]["status"] == "SCANNED"
    assert svc.report()["scan"]["status"] == "SCANNED"


# ported: OsvVulnerabilityScannerTests.retainsValidatedPagesWhenLaterPaginationFails
def test_partial_on_failed_query(tmp_state_dir: Path):
    osv = FakeOsv(docs={"V-1": advisory("V-1", JINJA)})
    osv.query = [
        (200, json.dumps({"results": [{"vulns": [{"id": "V-1"}], "next_page_token": "t"}, {}]})),
        (503, "busy"),
    ]
    report = service(osv, [JINJA, FLASK], tmp_state_dir).scan()
    scan = report["scan"]
    assert scan["status"] == "PARTIAL"
    assert scan["message"] == "Scan completed against OSV.dev, but 1 package query was not completed."
    assert scan["packagesScanned"] == 1
    assert dep(report, "jinja2")["assessment"] == {"queryComplete": False, "detailAssessmentComplete": False}
    assert [v["id"] for v in dep(report, "jinja2")["vulnerabilities"]] == ["V-1"]  # the validated page is kept
    assert dep(report, "flask")["assessment"] == {"queryComplete": True, "detailAssessmentComplete": True}
    assert "Some dependency queries were not completed." in report["evidence"]["limitations"]


# ported: OsvVulnerabilityScannerTests.degradesToPartialWhenOsvPaginationExceedsTheSafetyBound
def test_partial_on_truncated_pagination(tmp_state_dir: Path):
    osv = FakeOsv()
    osv.query = [(200, json.dumps({"results": [{"next_page_token": "again"}]}))] * 20
    report = service(osv, [JINJA], tmp_state_dir).scan()
    assert report["scan"]["status"] == "PARTIAL"
    assert report["scan"]["message"] == (
        "Scan completed against OSV.dev, but some advisories were paginated and not fully fetched; "
        "1 package query was not completed."
    )


def test_disabled_not_cached(no_side_effects: SideEffectGuard, tmp_state_dir: Path):
    osv = FakeOsv()
    svc = service(osv, [JINJA], tmp_state_dir, vulnerabilities_osv_enabled=False)
    report = svc.scan()
    assert report["scanningEnabled"] is False
    assert report["scan"]["status"] == "DISABLED"
    assert report["scan"]["message"] == (
        "OSV scanning is disabled. Set SHARPIT_VULNERABILITIES_OSV_ENABLED=true to allow on-demand scans."
    )
    after = svc.report()
    assert (after["scan"]["status"], after["scanningEnabled"]) == ("NOT_SCANNED", False)
    assert osv.opener.requests == []


def test_running_scan_is_busy_then_cached(tmp_state_dir: Path):
    osv = FakeOsv(ids={"jinja2": ["V-1"]}, docs={"V-1": advisory("V-1", JINJA)})
    osv.release = threading.Event()
    svc = service(osv, [JINJA], tmp_state_dir)
    running = threading.Thread(target=svc.scan)  # stands in for a caller that stopped waiting (ToolGate timeout)
    running.start()
    try:
        while not osv.opener.requests:
            threading.Event().wait(0.01)
        with pytest.raises(ActionBusy) as busy:  # test_concurrent_scan_409 at the engine level
            svc.scan()
        assert busy.value.body()["activeOperation"] == OPERATION
        assert svc.report()["scan"]["status"] == "NOT_SCANNED"
    finally:
        osv.release.set()
        running.join(5)
    report = svc.report()
    assert report["scan"]["status"] == "SCANNED"
    assert dep(report, "jinja2")["vulnerabilityCount"] == 1


# ported: OsvVulnerabilityScannerTests.configuredLimitsDoNotBorrowCompletionFromAnotherDependency
def test_caps_max_packages(tmp_state_dir: Path):
    osv = FakeOsv(ids={"jinja2": ["V-1"]}, docs={"V-1": advisory("V-1", JINJA)})
    report = service(osv, [JINJA, FLASK], tmp_state_dir, vulnerabilities_max_packages=1).scan()
    scan = report["scan"]
    assert (scan["status"], scan["packagesScanned"], scan["packagesSkipped"]) == ("PARTIAL", 1, 1)
    assert scan["message"] == "Scan completed against OSV.dev, but configured package or advisory limits were applied."
    assert [len(json.loads(r.data)["queries"]) for r in osv.opener.requests if r.data] == [1]  # type: ignore[arg-type]
    assert dep(report, "flask")["assessment"] == {"queryComplete": False, "detailAssessmentComplete": False}
    assert "Some inventory packages were excluded by the scan limit." in report["evidence"]["limitations"]


def test_caps_max_advisories(tmp_state_dir: Path):
    osv = FakeOsv(ids={"jinja2": ["V-2", "V-1"]}, docs={v: advisory(v, JINJA) for v in ("V-1", "V-2")})
    report = service(osv, [JINJA], tmp_state_dir, vulnerabilities_max_advisories=1).scan()
    assert report["scan"]["status"] == "PARTIAL"
    assert [p for p in osv.paths() if p.startswith("/v1/vulns/")] == ["/v1/vulns/V-1"]  # sorted, then capped
    assert dep(report, "jinja2")["assessment"]["detailAssessmentComplete"] is False


def test_empty_inventory(tmp_state_dir: Path):
    osv = FakeOsv()
    report = service(osv, [], tmp_state_dir).scan()
    assert (report["scan"]["status"], report["scan"]["message"]) == (
        "SCANNED",
        "No PyPI distributions were discovered to scan.",
    )
    assert osv.opener.requests == []


def test_dismissed_applied_to_report(tmp_state_dir: Path):
    osv = fixture_osv()
    svc = service(osv, [JINJA, FLASK], tmp_state_dir)
    scanned = svc.scan()
    svc.dismissals.add("GHSA-h75v-3vvj-5mfj::pypi:jinja2")
    report = svc.report()
    jinja = dep(report, "jinja2")
    assert [v["dismissed"] for v in jinja["vulnerabilities"]] == [True]
    assert (jinja["vulnerabilityCount"], jinja["highestSeverity"]) == (0, "NONE")
    assert report["vulnerable"] == 0
    assert report["scan"]["vulnerabilitiesFound"] == 0
    assert len(report["severityCounts"]) == 6 and all(c["count"] == 0 for c in report["severityCounts"])
    assert report["evidence"] == scanned["evidence"]  # BootUI applyDismissals keeps the evidence

    svc.dismissals.remove("GHSA-h75v-3vvj-5mfj::pypi:jinja2")
    assert svc.report() == scanned


def test_dismissal_matches_package_name_not_other_packages(tmp_state_dir: Path):
    osv = FakeOsv(ids={"jinja2": ["V-1"], "flask": ["V-1"]}, docs={"V-1": advisory("V-1", JINJA)})
    osv.docs["V-1"]["affected"].append({"package": {"ecosystem": "PyPI", "name": "flask"}, "versions": ["3.0.0"]})
    svc = service(osv, [JINJA, FLASK], tmp_state_dir)
    svc.scan()
    svc.dismissals.add("V-1::pypi:flask")
    report = svc.report()
    assert dep(report, "flask")["vulnerabilities"][0]["dismissed"] is True
    assert dep(report, "jinja2")["vulnerabilities"][0]["dismissed"] is False


# ported: OsvVulnerabilityScannerTests.recordsPerDependencyCompletionRatherThanTreatingMissingDetailsAsClean
# (plus the Task 11 ruling: the fetch stage checks the id itself and ports validWithdrawal)
@pytest.mark.parametrize(
    ("outcome", "detail_complete", "kept"),
    [
        ("no-match", True, False),
        ("withdrawn", True, False),
        ("withdrawn-offset", True, False),
        ("missing", False, False),
        ("mismatch", False, False),
        ("malformed", False, False),
        ("unresolved", False, True),
        ("unknown", True, True),
        ("known", True, True),
        ("malformed-withdrawal", False, False),
        ("non-string-withdrawal", False, True),
        ("blank-withdrawal", False, True),
        ("null-withdrawal", True, True),
    ],
)
def test_per_dependency_completion(tmp_state_dir: Path, outcome: str, detail_complete: bool, kept: bool):
    widget, complete = Package("widget", "1.0.0", None), Package("complete", "1.0.0", None)
    known = advisory("V-RETAINED", widget, "UNSUPPORTED" if outcome == "unknown" else "HIGH")
    detail: Any = {
        "withdrawn": {"id": "V-RETAINED", "withdrawn": "2024-01-01T00:00:00Z"},
        "withdrawn-offset": {"id": "V-RETAINED", "withdrawn": "2024-01-01T00:00:00.123+02:00"},
        "malformed-withdrawal": {"id": "V-RETAINED", "withdrawn": "not-a-timestamp"},
        "non-string-withdrawal": {**known, "withdrawn": 1704067200},
        "blank-withdrawal": {**known, "withdrawn": " "},
        "null-withdrawal": {**known, "withdrawn": None},
        "mismatch": {"id": "OTHER"},
        "malformed": "{bad",
        "unresolved": {"id": "V-RETAINED", "affected": {}},
        "missing": None,
    }.get(outcome, known)
    osv = FakeOsv(ids={} if outcome == "no-match" else {"widget": ["V-RETAINED"]}, docs={"V-RETAINED": detail})
    report = service(osv, [complete, widget], tmp_state_dir).scan()
    assert report["scan"]["packagesScanned"] == 2
    assert dep(report, "complete")["assessment"] == {"queryComplete": True, "detailAssessmentComplete": True}
    widget_dto = dep(report, "widget")
    assert widget_dto["assessment"] == {"queryComplete": True, "detailAssessmentComplete": detail_complete}
    assert len(widget_dto["vulnerabilities"]) == (1 if kept else 0)
    if outcome == "unknown":
        assert widget_dto["vulnerabilities"][0]["severity"] == "UNKNOWN"
    fully_assessed = detail_complete and outcome != "unknown"
    assert report["evidence"]["usable"] is True
    assert report["evidence"]["coverageComplete"] is fully_assessed
    assert (report["evidence"]["limitations"] == []) is fully_assessed
    failed_fetch = outcome in ("missing", "mismatch", "malformed")
    assert ("1 advisory fetch failed" in report["scan"]["message"]) is failed_fetch


# ported: OsvVulnerabilityScannerTests.fetchesManyDistinctAdvisoriesConcurrentlyWithoutLosingOrMisattributingAny
# ported: OsvVulnerabilityScannerTests.countsConcurrentAdvisoryFetchFailuresCorrectlyAcrossTheBoundedPool
def test_concurrent_fetches_count_failures(tmp_state_dir: Path):
    ids = [f"GHSA-MIX-{i}" for i in range(16)]
    osv = FakeOsv(ids={"widget": ids}, docs={i: advisory(i, Package("widget", "1.0", None)) for i in ids[5:]})
    report = service(osv, [Package("widget", "1.0", None)], tmp_state_dir).scan()
    assert report["scan"]["status"] == "PARTIAL"
    assert report["scan"]["message"] == "Scan completed against OSV.dev, but 5 advisory fetches failed."
    assert sorted(v["id"] for v in report["dependencies"][0]["vulnerabilities"]) == sorted(ids[5:])


@pytest.mark.parametrize(
    ("withdrawn", "valid"),
    [
        ("2024-01-01T00:00:00Z", True),
        ("2024-01-01T00:00Z", True),
        ("2024-01-01T00:00:00.123456789+02:00", True),
        ("2024-01-01 00:00:00Z", False),
        ("20240101T000000Z", False),
        ("2024-01-01T00:00:00+0200", False),
        ("2024-01-01T00:00:00", False),
        ("2024-13-01T00:00:00Z", False),
    ],
)
def test_valid_withdrawal_is_strict_like_instant_parse(withdrawn: str, valid: bool):
    assert _valid_withdrawal({"withdrawn": withdrawn}) is valid


def test_report_before_a_scan_reads_the_inventory_once_and_a_scan_refreshes_it(tmp_state_dir: Path):
    # Task P1: the UI polls report(); the installed distributions do not change without a restart
    calls: list[int] = []

    def inventory() -> list[Package]:
        calls.append(1)
        return [JINJA]

    svc = VulnerabilityService(
        SharpitSettings(),
        OsvClient("http://osv.test", 2.0, FakeOsv().opener),
        EpssClient("http://epss.test", 2.0, FakeOsv().opener),
        inventory,
        DismissalStore(tmp_state_dir),
        SingleFlight(),
    )
    first = svc.report()
    assert svc.report() == first
    assert len(calls) == 1
    svc.scan()
    assert len(calls) == 2  # a scan always re-reads the inventory
