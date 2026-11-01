"""Merging the facts of every worker and deciding the run status (0.3.0 spec §6.6, §6.8).

Every session-level condition is evaluated here, once, over the merged facts (never per worker).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from sharpit.engine.advisors.findings import AdvisorRun, Finding
from sharpit.engine.advisors.rules import severity_rank
from sharpit.engine.testsession.facts import SessionFacts, TestFacts

type Status = Literal["pass", "fail", "unknown"]

SQL_SOURCES = ("sqlalchemy", "sqlite3")
APP_ADVISORS = ("rest-api",)  # advisors that read an application: with no app seen they are UNKNOWN
NO_APPLICATION = "no application: pass --sharpit-app or call sharpit.install in the tests"
NO_SQL_EXECUTED = "no SQL statement was executed"
ADVISORS_DISABLED = "advisors disabled"
FALLBACK_REASON = "assessment evidence is incomplete"
TOP_STATEMENTS = 20
# DB-API module -> the SQLAlchemy dialect drivers (``engine.dialect.driver``) that route its calls through an engine
DRIVER_DIALECTS: dict[str, frozenset[str]] = {
    "aiosqlite": frozenset({"aiosqlite"}),
    "asyncpg": frozenset({"asyncpg"}),
    "psycopg": frozenset({"psycopg", "psycopg_async"}),
    "psycopg2": frozenset({"psycopg2"}),
    "pymysql": frozenset({"pymysql", "aiomysql"}),
    "MySQLdb": frozenset({"mysqldb"}),
    "oracledb": frozenset({"oracledb", "oracledb_async"}),
    "pyodbc": frozenset({"pyodbc"}),
}


@dataclass(frozen=True)
class MergedFacts:
    tests: list[TestFacts] = field(default_factory=list[TestFacts])
    unattributed: int = 0
    top_unattributed: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    unattributed_exceptions: int = 0
    filtered: int = 0
    sources: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    workers: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    untraced_drivers: set[str] = field(default_factory=set[str])
    engine_drivers: set[str] = field(default_factory=set[str])
    preexisting: int = 0
    aliases: list[str] = field(default_factory=list[str])
    advisor_runs: list[AdvisorRun] = field(default_factory=list[AdvisorRun])
    findings: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    warnings: list[str] = field(default_factory=list[str])
    sql_attached: bool = False  # some worker had an SQL source attached
    unattached: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])  # (source, worker id)
    exceptions_lost: list[str] = field(default_factory=list[str])


def deciding(tests: Iterable[TestFacts]) -> list[TestFacts]:
    """The last attempt of every ``(node id, worker)``: the only one whose gates decide the outcome."""
    last: dict[tuple[str, str], TestFacts] = {}
    for test in tests:
        key = (test.key.node_id, test.key.worker)
        if key not in last or test.key.attempt >= last[key].key.attempt:
            last[key] = test
    return list(last.values())


def attributed_queries(tests: Iterable[TestFacts]) -> int:
    return sum(phase.queries for test in tests for phase in test.phases.values())


def unattributed_share(attributed: int, unattributed: int) -> float:
    """Percent of the non-filtered statements that no test owns, to one decimal."""
    total = attributed + unattributed
    return round(100 * unattributed / total, 1) if total else 0.0


def driver_covered(module: str, engine_drivers: set[str]) -> bool:
    return bool(DRIVER_DIALECTS.get(module, frozenset({module})) & engine_drivers)


def uncovered_drivers(merged: MergedFacts) -> list[str]:
    return sorted(d for d in merged.untraced_drivers if not driver_covered(d, merged.engine_drivers))


def _combine_sources(parts: Sequence[SessionFacts], untraced: set[str], engines: set[str]) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for part in parts:
        for entry in part.sources:
            combined = by_name.setdefault(
                entry["name"], {"name": entry["name"], "attached": True, "reason": None, "limitations": []}
            )
            if not entry["attached"]:
                combined["attached"] = False
                combined["reason"] = combined["reason"] or entry.get("reason")
            combined["limitations"] += [x for x in entry.get("limitations", []) if x not in combined["limitations"]]
    for module in sorted(untraced):
        if driver_covered(module, engines):
            note = f"{module} calls outside SQLAlchemy are not traced"
            through = by_name.get("sqlalchemy")
            if through is not None and note not in through["limitations"]:
                through["limitations"].append(note)
        else:
            by_name[module] = {"name": module, "attached": False, "reason": "not traced in 0.3.0", "limitations": []}
    return list(by_name.values())


def _worst(statuses: Iterable[str]) -> Literal["PASSED", "FAILED", "UNKNOWN"]:
    """FAILED over UNKNOWN over PASSED."""
    present = set(statuses)
    if "FAILED" in present:
        return "FAILED"
    return "UNKNOWN" if "UNKNOWN" in present else "PASSED"


def _merge_group(advisor: str, app: str | None, runs: list[AdvisorRun]) -> AdvisorRun:
    findings: dict[str, Finding] = {}
    for finding in (f for run in runs for f in run.findings):
        findings.setdefault(finding.fingerprint, finding)
    status = _worst(r.status for r in runs)
    chosen = next((r for r in runs if r.status == status), runs[0])
    reason = chosen.reason if status == "UNKNOWN" else None
    return AdvisorRun(advisor, status, tuple(findings.values()), chosen.evidence, reason, app)


def _merge_runs(parts: Sequence[SessionFacts]) -> list[AdvisorRun]:
    """One run per (advisor, app): findings de-duplicated by fingerprint, FAILED over UNKNOWN over PASSED."""
    groups: dict[tuple[str, str | None], list[AdvisorRun]] = {}
    for run in (r for part in parts for r in part.advisor_runs):
        groups.setdefault((run.advisor, run.app), []).append(run)
    return [_merge_group(advisor, app, runs) for (advisor, app), runs in groups.items()]


def _exceptions_lost(parts: Sequence[SessionFacts]) -> list[str]:
    lost: list[str] = []
    for part in parts:
        entry = next((s for s in part.sources if s["name"] == "exceptions"), None)
        if part.tests and entry is not None and (not part.exceptions_source_ok or not entry["attached"]):
            lost.append((entry or {}).get("reason") or "the exceptions source did not attach")
    return lost


def _flat_findings(tests: Sequence[TestFacts], runs: Sequence[AdvisorRun]) -> dict[str, dict[str, Any]]:
    """The report's one flat list: the deciding attempts' gate findings, then the advisors', by fingerprint."""
    findings: dict[str, dict[str, Any]] = {}
    for test in deciding(tests):
        for dto in test.findings:
            findings.setdefault(dto["fingerprint"], dto)
    for run in runs:
        for finding in run.findings:
            findings.setdefault(finding.fingerprint, finding.to_dto())
    return findings


def merge(parts: Sequence[SessionFacts], missing_workers: Sequence[str]) -> MergedFacts:
    tests = [t for p in parts for t in p.tests]
    untraced = {d for p in parts for d in p.untraced_drivers}
    engines = {d for p in parts for d in p.engine_drivers}
    top: Counter[str] = Counter()
    for part in parts:
        top.update(part.top_unattributed)
    sources = _combine_sources(parts, untraced, engines)
    runs = _merge_runs(parts)
    unattached = [
        (s["name"], p.worker) for p in parts for s in p.sources if not s["attached"] and s["name"] != "exceptions"
    ]
    findings = _flat_findings(tests, runs)
    attributed = attributed_queries(tests)
    unattributed = sum(p.unattributed for p in parts)
    warnings: list[str] = []
    for line in [*(w for p in parts for w in p.warnings), *(x for s in sources for x in s["limitations"])]:
        if line not in warnings:
            warnings.append(line)
    if attributed + unattributed == 0:
        warnings.append(NO_SQL_EXECUTED)
    return MergedFacts(
        tests=tests,
        unattributed=unattributed,
        top_unattributed=[{"sql": s, "count": c} for s, c in sorted(top.items(), key=lambda x: (-x[1], x[0]))][
            :TOP_STATEMENTS
        ],
        unattributed_exceptions=sum(p.unattributed_exceptions for p in parts),
        filtered=sum(p.filtered for p in parts),
        sources=sources,
        workers=[{"id": p.worker, "status": "ok"} for p in parts]
        + [{"id": w, "status": "missing"} for w in missing_workers],
        untraced_drivers=untraced,
        engine_drivers=engines,
        preexisting=sum(p.preexisting for p in parts),
        aliases=list(dict.fromkeys(a for p in parts for a in p.aliases)),
        advisor_runs=runs,
        findings=list(findings.values()),
        warnings=warnings,
        sql_attached=any(s["attached"] and s["name"] in SQL_SOURCES for p in parts for s in p.sources),
        unattached=unattached,
        exceptions_lost=_exceptions_lost(parts),
    )


def _advisor_summary(advisor: str, runs: list[AdvisorRun], *, advisors_enabled: bool) -> dict[str, Any]:
    if not runs:
        reason = NO_APPLICATION if advisors_enabled else ADVISORS_DISABLED
        return {"advisor": advisor, "status": "UNKNOWN", "reason": reason, "apps": [], "findings": []}
    status = _worst(r.status for r in runs)
    reason = next((r.reason for r in runs if r.status == "UNKNOWN"), None) if status == "UNKNOWN" else None
    found: dict[str, dict[str, Any]] = {}
    for finding in (f for run in runs for f in run.findings):
        found.setdefault(finding.fingerprint, finding.to_dto())
    apps = [{"app": r.app, "status": r.status, "reason": r.reason, "evidence": r.evidence} for r in runs]
    return {"advisor": advisor, "status": status, "reason": reason, "apps": apps, "findings": list(found.values())}


def advisor_summaries(merged: MergedFacts, *, advisors_enabled: bool) -> list[dict[str, Any]]:
    """The report's ``advisors``: one entry per advisor with its apps; an app-reading advisor with no app is UNKNOWN."""
    ids = list(dict.fromkeys([*APP_ADVISORS, *(r.advisor for r in merged.advisor_runs)]))
    return [
        _advisor_summary(
            advisor,
            [r for r in merged.advisor_runs if r.advisor == advisor] if advisors_enabled else [],
            advisors_enabled=advisors_enabled,
        )
        for advisor in ids
    ]


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _failing_tests(merged: MergedFacts) -> int:
    return sum(1 for t in deciding(merged.tests) if any(not f["dismissed"] for f in t.findings))


def _fail_reasons(merged: MergedFacts, summaries: list[dict[str, Any]], fail_on: str) -> list[str]:
    reasons: list[str] = []
    if failing := _failing_tests(merged):
        reasons.append(f"{_plural(failing, 'test')} failed sharpit gates")
    gate = severity_rank(fail_on)
    for summary in summaries:
        if summary["status"] == "FAILED":
            count = sum(1 for f in summary["findings"] if not f["dismissed"] and severity_rank(f["severity"]) <= gate)
            reasons.append(f"advisor '{summary['advisor']}' found {_plural(count, 'finding')} at or above {fail_on}")
    return reasons


def _outside_capture(merged: MergedFacts) -> str | None:
    details: list[str] = []
    if merged.preexisting:
        details.append(f"{_plural(merged.preexisting, 'connection')} opened before capture started")
    if merged.aliases:
        details.append(f"early connect alias in {', '.join(merged.aliases)}")
    return "; ".join(details) or None


def _unknown_reasons(
    merged: MergedFacts, summaries: list[dict[str, Any]], max_unattributed: float, advisors_enabled: bool
) -> list[str]:
    reasons: list[str] = []
    attributed = attributed_queries(merged.tests)
    if not merged.sql_attached:
        reasons.append("no SQL source attached")
    if merged.unattributed and attributed == 0:
        reasons.append("no SQL statement was attributed to a test")
    share = unattributed_share(attributed, merged.unattributed)
    if share > max_unattributed:
        reasons.append(f"{share:.1f}% of SQL statements were not attributed to a test (limit {max_unattributed:g}%)")
    reasons += [f"untraced database driver in use: {d}" for d in uncovered_drivers(merged)]
    if attributed == 0 and (detail := _outside_capture(merged)):
        reasons.append(f"SQL may have run outside capture: {detail}")
    if merged.exceptions_lost:
        reasons.append(f"exception capture was lost: {'; '.join(dict.fromkeys(merged.exceptions_lost))}")
    reasons += [f"source '{name}' not attached in worker {worker}" for name, worker in merged.unattached]
    if advisors_enabled:
        reasons += [
            f"advisor '{s['advisor']}' could not assess: {s['reason'] or FALLBACK_REASON}"
            for s in summaries
            if s["status"] == "UNKNOWN"
        ]
    reasons += [f"worker {w['id']} reported no sharpit facts" for w in merged.workers if w["status"] == "missing"]
    return reasons


def session_status(
    merged: MergedFacts,
    *,
    allow_unknown: bool,
    max_unattributed: float,
    advisors_enabled: bool,
    fail_on: str,
) -> tuple[Status, list[str]]:
    """Spec §6.6: ``fail`` lists every fail reason, else ``unknown`` lists every unknown reason, else ``pass``."""
    del allow_unknown  # the status never depends on it; ``exit_fails`` does
    summaries = advisor_summaries(merged, advisors_enabled=advisors_enabled)
    if failed := _fail_reasons(merged, summaries, fail_on):
        return "fail", failed
    if unknown := _unknown_reasons(merged, summaries, max_unattributed, advisors_enabled):
        return "unknown", unknown
    return "pass", []


def exit_fails(status: str, allow_unknown: bool) -> bool:
    """Whether the session exit status turns non-zero (pytest's own non-zero codes are never lowered)."""
    return status == "fail" or (status == "unknown" and not allow_unknown)
