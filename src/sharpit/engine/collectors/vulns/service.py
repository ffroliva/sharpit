"""Vulnerability scan service (port of BootUI ``VulnerabilitiesController`` and the scan half of
``OsvVulnerabilityScanner``: ``scan``, ``fetchVulnerabilities``, ``validWithdrawal``, ``enrich``, ``applyEpss`` and
``scanMessage``; plus ``DependencyReports`` ``report``, ``evidence``, ordering and ``applyDismissals``).

``report()`` never touches the network: it renders the cached scan, or the bare inventory as ``NOT_SCANNED``. ``scan()``
is the only path to OSV/EPSS; it runs under the single-flight lock and caches its result from inside the worker, so a
scan that outlives its caller still lands in the cache. Dismissals are re-read and applied on every render; the cache
itself is never mutated by them.

PyPI adaptations: ``groupId`` is ``"pypi"``, ``artifactId``/``packageName`` the PEP 503 name, ``source``
``"importlib.metadata"``, and the Maven-worded messages are reworded. Coverage is always ``COMPLETE`` over the
inventory: there are no jar archives to identify (distributions without a name or version are not packages).
Dropped: BootUI's ``" <query failure>."`` message suffix, because ``OsvClient.querybatch`` reports failed packages
without the failure text.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from sharpit.engine.collectors.vulns.cvss import SEVERITIES
from sharpit.engine.collectors.vulns.dismissals import DismissalStore, rule_id
from sharpit.engine.collectors.vulns.epss import EpssClient, canonical_cve_id
from sharpit.engine.collectors.vulns.interpreter import Finding, compare_versions, interpret
from sharpit.engine.collectors.vulns.inventory import Package
from sharpit.engine.collectors.vulns.osv import OsvClient, OsvError, QueryResult
from sharpit.engine.singleflight import SingleFlight
from sharpit.settings import SharpitSettings

OPERATION = "vulnerabilities-scan"
NOT_SCANNED_MESSAGE = "Dependency inventory loaded. Click Scan with OSV.dev to check for known vulnerabilities."
DISABLED_MESSAGE = "OSV scanning is disabled. Set SHARPIT_VULNERABILITIES_OSV_ENABLED=true to allow on-demand scans."
EMPTY_MESSAGE = "No PyPI distributions were discovered to scan."
ADVISORY_FETCH_CONCURRENCY = 10
_SOURCE = "importlib.metadata"


@dataclass
class _Dependency:
    package: Package
    findings: list[Finding]
    query_complete: bool = False
    detail_complete: bool = False


@dataclass(frozen=True)
class _Scan:
    scanning_enabled: bool
    status: str
    message: str
    scanned_at: int | None
    packages_scanned: int
    packages_skipped: int
    dependencies: list[_Dependency]


class VulnerabilityService:
    def __init__(
        self,
        settings: SharpitSettings,
        osv: OsvClient,
        epss: EpssClient,
        inventory: Callable[[], list[Package]],
        dismissals: DismissalStore,
        single_flight: SingleFlight,
    ) -> None:
        self._settings = settings
        self._osv = osv
        self._epss = epss
        self._inventory = inventory
        self.dismissals = dismissals
        self._single_flight = single_flight
        self._cached: _Scan | None = None

    def report(self) -> dict[str, Any]:
        """The cached scan, else the inventory as ``NOT_SCANNED``; dismissals applied. Never networks."""
        cached = self._cached
        if cached is None:
            cached = self._inventory_only(
                "NOT_SCANNED", NOT_SCANNED_MESSAGE, self._settings.vulnerabilities_osv_enabled
            )
        return _render(cached, set(self.dismissals.list()))

    def scan(self, wait_timeout: float | None = None) -> dict[str, Any]:
        """Scan OSV.dev (single-flight ``ActionBusy``/``WaitTimeout``); DISABLED is returned but never cached."""
        if not self._settings.vulnerabilities_osv_enabled:
            result = self._inventory_only("DISABLED", DISABLED_MESSAGE, False)
        else:
            result = self._single_flight.run(OPERATION, self._scan_and_cache, wait_timeout)
        return _render(result, set(self.dismissals.list()))

    def _inventory_only(self, status: str, message: str, enabled: bool) -> _Scan:
        return _Scan(enabled, status, message, None, 0, 0, [_Dependency(p, []) for p in self._inventory()])

    def _scan_and_cache(self) -> _Scan:
        result = self._scan()
        self._cached = result  # inside the worker: a caller that stopped waiting still gets it cached
        return result

    def _scan(self) -> _Scan:
        settings = self._settings
        packages = self._inventory()
        scanned_at = int(time.time() * 1000)
        distinct = list(dict.fromkeys(packages))
        max_packages = max(1, settings.vulnerabilities_max_packages)
        candidates = distinct[:max_packages]
        skipped = max(0, len(distinct) - max_packages)
        if not candidates:
            return _Scan(True, "SCANNED", EMPTY_MESSAGE, scanned_at, 0, skipped, [])
        try:
            query = self._osv.querybatch(candidates)
        except OsvError as error:
            deps = [_Dependency(p, []) for p in packages]
            return _Scan(True, "ERROR", f"OSV scan failed: {error}", scanned_at, 0, skipped, deps)
        unique_ids = list(dict.fromkeys(i for ids in query.ids.values() for i in ids))
        max_advisories = max(1, settings.vulnerabilities_max_advisories)
        docs, withdrawn, failed_fetches = self._fetch(sorted(unique_ids)[:max_advisories])
        dependencies, unresolved = _enrich(packages, query, docs, withdrawn)
        epss_message = self._apply_epss(dependencies)
        limited = len(candidates) < len(distinct) or len(unique_ids) > max_advisories
        partial = limited or query.truncated or query.failed or failed_fetches or unresolved
        message = _scan_message(limited, query.truncated, len(candidates) - len(query.complete), failed_fetches)
        if unresolved:
            message += (
                f" {unresolved} finding associations could not be fully interpreted;"
                " query-derived findings were retained."
            )
        status = "PARTIAL" if partial else "SCANNED"
        return _Scan(True, status, message + epss_message, scanned_at, len(query.complete), skipped, dependencies)

    def _fetch(self, ids: list[str]) -> tuple[dict[str, dict[str, Any]], set[str], int]:
        """Advisory details over a bounded pool (BootUI ``fetchVulnerabilities``): (docs, withdrawn ids, failures)."""
        if not ids:
            return {}, set(), 0
        with ThreadPoolExecutor(min(ADVISORY_FETCH_CONCURRENCY, len(ids)), thread_name_prefix="sharpit-osv") as pool:
            fetched = list(pool.map(self._fetch_one, ids))
        docs: dict[str, dict[str, Any]] = {}
        withdrawn: set[str] = set()
        failed = 0
        for vuln_id, doc in zip(ids, fetched, strict=True):
            if doc is None or doc.get("id") != vuln_id:  # a mismatched document counts as a failed fetch
                failed += 1
            elif _is_withdrawn(doc):
                if _valid_withdrawal(doc):  # a malformed timestamp is excluded too, leaving the detail incomplete
                    withdrawn.add(vuln_id)
            else:
                docs[vuln_id] = doc
        return docs, withdrawn, failed

    def _fetch_one(self, vuln_id: str) -> dict[str, Any] | None:
        try:
            return self._osv.vuln(vuln_id)
        except Exception:  # BootUI counts any failed fetch task (its ExecutionException included) as one failure
            return None

    def _apply_epss(self, dependencies: list[_Dependency]) -> str:
        """Best-effort EPSS enrichment (BootUI ``applyEpss``/``applyEpssScores``); returns the message suffix."""
        if not self._settings.vulnerabilities_epss_enabled:
            return ""
        findings = [f for d in dependencies for f in d.findings]
        cves = list(dict.fromkeys(cve for f in findings for cve in _cve_ids(f)))
        if not cves:
            return ""
        result = self._epss.scores(cves)
        for finding in findings:
            best: tuple[str, tuple[float, float]] | None = None
            for cve in _cve_ids(finding):
                score = result.scores.get(cve)
                if score is not None and (
                    best is None or score[0] > best[1][0] or (score[0] == best[1][0] and cve < best[0])
                ):
                    best = (cve, score)
            if best is not None:
                finding.epss_score, finding.epss_percentile = best[1]
        tail = (
            "enrichment was incomplete or unavailable." if result.failed else "remaining CVEs have no available data."
        )
        return f" EPSS: {len(result.scores)} of {len(cves)} requested CVEs have scores; {tail}"


def _is_withdrawn(doc: dict[str, Any]) -> bool:
    value = doc.get("withdrawn")
    return isinstance(value, str) and bool(value.strip())


def _valid_withdrawal(doc: dict[str, Any]) -> bool:
    """BootUI ``validWithdrawal``: absent or null is valid; otherwise an ISO instant (with an offset) is required."""
    value = doc.get("withdrawn")
    if value is None:
        return True
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        if not value.endswith(("Z", "z")):
            return False
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError:
            return False
    return parsed.tzinfo is not None  # Instant.parse rejects a local date-time


def _enrich(
    packages: Sequence[Package], query: QueryResult, docs: dict[str, dict[str, Any]], withdrawn: set[str]
) -> tuple[list[_Dependency], int]:
    dependencies: list[_Dependency] = []
    unresolved = 0
    for pkg in packages:
        query_complete = pkg in query.complete
        detail_complete = query_complete
        findings: list[Finding] = []
        for vuln_id in dict.fromkeys(query.ids.get(pkg, [])):
            doc = docs.get(vuln_id)
            finding = interpret(doc, pkg, vuln_id) if doc is not None else None
            if doc is not None and finding is not None:
                if finding.unresolved:
                    unresolved += 1
                detail_complete &= not finding.unresolved and _valid_withdrawal(doc)
                findings.append(finding)
            elif vuln_id not in withdrawn:
                detail_complete = False
        findings.sort(key=_vulnerability_order)
        dependencies.append(_Dependency(pkg, findings, query_complete, detail_complete))
    return dependencies, unresolved


def _cve_ids(finding: Finding) -> list[str]:
    """The finding's own id (OSV records may be CVE records) then its aliases, canonical and distinct."""
    return list(dict.fromkeys(c for c in map(canonical_cve_id, [finding.id, *finding.aliases]) if c is not None))


def _scan_message(limited: bool, truncated: bool, failed_packages: int, failed_fetches: int) -> str:
    reasons: list[str] = []
    if limited:
        reasons.append("configured package or advisory limits were applied")
    if truncated:
        reasons.append("some advisories were paginated and not fully fetched")
    if failed_packages > 0:
        noun = "package query was" if failed_packages == 1 else "package queries were"
        reasons.append(f"{failed_packages} {noun} not completed")
    if failed_fetches > 0:
        reasons.append(f"{failed_fetches} advisory {'fetch' if failed_fetches == 1 else 'fetches'} failed")
    if not reasons:
        return "Scan completed against OSV.dev."
    return "Scan completed against OSV.dev, but " + "; ".join(reasons) + "."


# --- rendering (DependencyReports.report / applyDismissals / evidence) ---


def _rank(severity: str) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


def _vulnerability_order(finding: Finding) -> tuple[bool, int, str, str]:
    return finding.dismissed, _rank(finding.severity), finding.id.lower(), finding.id


def _highest(findings: Iterable[Finding]) -> str:
    return min((f.severity for f in findings), key=_rank, default="NONE")


def _known(finding: Finding) -> bool:
    return finding.severity in SEVERITIES and finding.severity != "UNKNOWN"


def _render(scan: _Scan, dismissed: set[str]) -> dict[str, Any]:
    rows: list[tuple[Package, str, list[Finding], int, dict[str, bool]]] = []
    counts = dict.fromkeys(SEVERITIES, 0)
    for dep in scan.dependencies:
        name = dep.package.name
        marked = sorted(
            (replace(f, dismissed=rule_id(f.id, name) in dismissed) for f in dep.findings), key=_vulnerability_order
        )
        active = [f for f in marked if not f.dismissed]
        for finding in active:
            if finding.severity in counts:
                counts[finding.severity] += 1
        assessment = {"queryComplete": dep.query_complete, "detailAssessmentComplete": dep.detail_complete}
        rows.append((dep.package, _highest(active), marked, len(active), assessment))
    version_key = functools.cmp_to_key(compare_versions)
    rows.sort(key=lambda r: (_rank(r[1]), r[0].name.lower(), r[0].name, version_key(r[0].version)))
    total = len(rows)
    return {
        "scanningEnabled": scan.scanning_enabled,
        "total": total,
        "vulnerable": sum(1 for r in rows if r[3] > 0),
        "severityCounts": [{"severity": s, "count": c} for s, c in counts.items()],
        "scan": {
            "scanner": "OSV.dev",
            "status": scan.status,
            "message": scan.message,
            "scannedAt": scan.scanned_at,
            "packagesScanned": scan.packages_scanned,
            "packagesSkipped": scan.packages_skipped,
            "vulnerabilitiesFound": sum(r[3] for r in rows),
        },
        "coverage": {
            "status": "COMPLETE",
            "archivesFound": total,
            "archivesIdentified": total,
            "archivesUnidentified": 0,
            "unidentifiedArchives": [],
            "unidentifiedArchivesTruncated": False,
        },
        "dependencies": [
            {
                "groupId": "pypi",
                "artifactId": pkg.name,
                "version": pkg.version,
                "packageName": pkg.name,
                "source": _SOURCE,
                "vulnerabilityCount": active_count,
                "highestSeverity": highest,
                "vulnerabilities": [f.to_dto() for f in marked],
                "assessment": assessment,
            }
            for pkg, highest, marked, active_count, assessment in rows
        ],
        "evidence": _evidence(scan),
    }


def _evidence(scan: _Scan) -> dict[str, Any]:
    """BootUI ``DependencyReports.evidence`` (dismissals do not change it); coverage is always complete here."""
    if scan.status not in ("SCANNED", "PARTIAL"):
        return {"usable": False, "coverageComplete": False, "limitations": ["Assessment evidence is unavailable."]}
    deps = scan.dependencies
    usable = any(
        (d.query_complete and d.detail_complete and all(map(_known, d.findings))) or any(map(_known, d.findings))
        for d in deps
    )
    limitations: list[str] = []
    if any(not d.query_complete for d in deps):
        limitations.append("Some dependency queries were not completed.")
    if any(d.query_complete and not d.detail_complete for d in deps):
        limitations.append("Some advisory details were unavailable or could not be fully interpreted.")
    if scan.packages_skipped > 0:
        limitations.append("Some inventory packages were excluded by the scan limit.")
    if any(not _known(f) for d in deps for f in d.findings):
        limitations.append("Findings with unknown severity are excluded from score penalties.")
    return {"usable": usable, "coverageComplete": not limitations, "limitations": limitations}
