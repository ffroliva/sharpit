"""The database advisor's report (port of BootUI ``DatabaseAdvisorScanner.doScan``, 2.2.0) on F5a's advisor scan core.

``run_scan`` holds the scan's single-flight while it reads every engine (``catalog.read_sources``), then hands the facts
to the core, which evaluates the rules, masks every string (datasource messages and diagnostics included) and caches
the report with its retained details. A rule that could judge no datasource is ``SKIPPED`` with its reason as an
``INFO`` diagnostic, never a fabricated pass.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from sharpit.engine import sqla
from sharpit.engine.advisors.findings import Finding
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.scan import AdvisorScan, Evaluation, ScanSpec, Scope
from sharpit.engine.collectors.database_advisor import RULES, rules_orm, rules_runtime
from sharpit.engine.collectors.database_advisor.catalog import LABELS, Source, read_sources
from sharpit.engine.singleflight import ActionBusy, Flight, SingleFlight

if TYPE_CHECKING:
    from sharpit.engine.advisors.dismissals import DismissalStore
    from sharpit.engine.context import SharpitContext
    from sharpit.engine.masking import Masker

ADVISOR = "database-advisor"
OPERATION = f"{ADVISOR}-scan"
ANALYZER = "sharpit Database Advisor"
DISCLAIMER = (
    "Read-only schema introspection (tables, columns, primary/foreign keys, indexes) through the SQLAlchemy "
    "inspector, with PostgreSQL and MySQL/MariaDB server limits, plus checks of each engine's pool and driver "
    "configuration. These checks are review prompts, not verdicts."
)
NOT_SCANNED_MESSAGE = (  # BootUI's text with BootUI -> sharpit (AGENTS.md)
    "Database Advisor has not run yet. Run Database checks in the panel, or call database_advisor_scan (sharpit db "
    "scan), to inspect the physical schema."
)
NO_ENGINES = "No SQLAlchemy engines were found to inspect."
NO_SCHEMA = "No physical schema could be read. See diagnostics for datasource discovery and read failures."
TRUNCATED = "A scan bound was reached, so some tables, columns or indexes were not read."
SPEC = ScanSpec(ADVISOR, ANALYZER, DISCLAIMER, NOT_SCANNED_MESSAGE)


@dataclass(frozen=True)
class Detail:
    """The scan's own facts, for the scope and extra-section hooks."""

    sources: tuple[Source, ...] = ()
    skipped: int = 0
    errored: int = 0
    diagnostics: tuple[dict[str, Any], ...] = ()


def _diagnostic(source: str, level: str, message: str) -> dict[str, Any]:
    return {"source": source, "level": level, "message": message}  # DatabaseAdvisorDiagnosticDto


def _source_diagnostics(sources: Sequence[Source]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in sources:
        if s.status == "FAILED":
            out.append(_diagnostic(s.name, "ERROR", s.message or "The datasource could not be read."))
        out += [_diagnostic(s.name, d["level"], d["message"]) for d in s.catalog.get("diagnostics", [])]
        if s.catalog.get("truncated"):
            out.append(_diagnostic(s.name, "WARNING", TRUNCATED))
    return out


def _message(tables: int, readable: int, failed: int, truncated: bool, complete: bool, errored: int) -> str:
    """BootUI ``DatabaseAdvisorScanner``'s completion message."""
    text = (
        f"Database Advisor completed against {tables} {'table' if tables == 1 else 'tables'} across {readable} "
        f"{'datasource' if readable == 1 else 'datasources'}."
    )
    if failed:
        text += f" {failed} datasource(s) could not be read."
    if truncated:
        text += " A scan bound was reached, so some findings may be missing."
    elif not complete:
        text += " Some schema or catalog metadata could not be read; see the diagnostics."
    if errored:
        text += f" {errored} rule(s) failed to evaluate."
    return text


def evaluate(request: Sequence[Source] | str) -> Evaluation:
    """The rules over the facts; ``request`` is the sources read, or why nothing was read (``DISABLED``)."""
    if isinstance(request, str):
        return Evaluation("DISABLED", request, (), (), evidence(False, False, [request]), Detail())
    sources = tuple(request)
    if not sources:
        unverified = ["No datasource was found, so no rule could run."]
        return Evaluation("DISABLED", NO_ENGINES, (), (), evidence(False, False, unverified), Detail())
    diagnostics = _source_diagnostics(sources)
    readable = [s for s in sources if s.status != "FAILED"]
    if not readable:
        unverified = ["No physical schema could be read, so no rule could run."]
        detail = Detail(sources, 0, 0, tuple(diagnostics))
        return Evaluation("ERROR", NO_SCHEMA, (), (), evidence(False, False, unverified), detail)
    evaluated: list[str] = []
    findings: list[Finding] = []
    skipped = errored = 0
    for rule in RULES:
        rule_id = rule.definition.id
        try:
            outcomes = [rule.check(s) for s in readable]
        except Exception as exc:  # noqa: BLE001 - one failing rule is an analysis error; never a failed scan
            errored += 1
            diagnostics.append(_diagnostic(rule_id, "ERROR", f"The rule failed to evaluate ({type(exc).__name__})."))
            continue
        reasons = [o for o in outcomes if isinstance(o, str)]
        if len(reasons) == len(outcomes):
            skipped += 1
            diagnostics.append(_diagnostic(rule_id, "INFO", f"Skipped: {reasons[0]}"))
            continue
        evaluated.append(rule_id)
        severity = rule.definition.severity
        hits = (hit for o in outcomes if not isinstance(o, str) for hit in o)
        findings += [Finding(rule_id, ADVISOR, severity, target, text, identity=key) for target, text, key in hits]
    truncated = any(s.catalog.get("truncated") for s in readable)
    catalogs_complete = all(s.catalog.get("complete") for s in readable)
    problems = [f"{d['source']}: {d['message']}" for d in diagnostics if d["level"] in ("WARNING", "ERROR")]
    complete = not problems and catalogs_complete and not truncated
    tables = sum(len(s.tables) for s in readable)
    message = _message(tables, len(readable), len(sources) - len(readable), truncated, catalogs_complete, errored)
    return Evaluation(
        "SCANNED" if complete else "PARTIAL",
        message,
        tuple(evaluated),
        tuple(findings),
        evidence(True, complete, problems),
        Detail(sources, skipped, errored, tuple(diagnostics)),
    )


def _detail(done: Evaluation | None) -> Detail:
    return done.detail if done is not None and isinstance(done.detail, Detail) else Detail()


def _data_source(s: Source) -> dict[str, Any]:
    return {  # DatabaseAdvisorDataSourceDto
        "name": s.name,
        "product": LABELS.get(s.dialect, s.dialect or None),
        "dialect": s.dialect or None,
        "identifierCase": None,  # nullable.json: the inspector does not report identifier folding
        "status": s.status,
        "message": s.message,
        "tablesAnalyzed": len(s.tables),
        "truncated": bool(s.catalog.get("truncated")),
    }


def _scope(done: Evaluation | None) -> Scope:
    sources = _detail(done).sources
    return Scope(
        {"dataSourceNames": sorted({s.name for s in sources}), "dataSources": [_data_source(s) for s in sources]},
        {"tablesAnalyzed": sum(len(s.tables) for s in sources)},
    )


def _extra(done: Evaluation | None) -> dict[str, Any]:
    detail = _detail(done)
    return {
        "rulesSkipped": detail.skipped,
        "rulesErrored": detail.errored,
        "truncated": any(s.catalog.get("truncated") for s in detail.sources),
        "diagnostics": list(detail.diagnostics),
        "suppression": {"suppressedFindings": 0, "incompleteRules": [], "findings": [], "omitted": 0},
    }


class DatabaseAdvisorService(AdvisorScan):
    """The database advisor on the shared scan core; ``run_scan`` owns the outer single-flight and the reads."""

    def __init__(self, dismissals: DismissalStore, masker: Masker, *, max_retained: int) -> None:
        super().__init__(
            SPEC,
            [r.definition for r in RULES],
            evaluate,
            scope=_scope,
            extra_sections=_extra,
            dismissals=dismissals,
            masker=masker,
            single_flight=SingleFlight(),  # uncontended: run_scan already holds the scan's own flight
            max_retained=max_retained,
        )


def _with_app_facts(ctx: SharpitContext, sources: list[Source]) -> list[Source]:
    """Each source with the declared models (ORM rules); the first with the SQL Trace window (DB-RUNTIME-001)."""
    if not sources:
        return sources
    declared = rules_orm.facts(ctx.models)
    trace = ctx.capture.sql_trace
    window = rules_runtime.facts(trace.rows() if trace is not None else [])
    first, *rest = sources
    return [replace(first, catalog={**first.catalog, "orm": declared, "runtime": window})] + [
        replace(s, catalog={**s.catalog, "orm": declared}) for s in rest
    ]


async def run_scan(ctx: SharpitContext, service: DatabaseAdvisorService) -> dict[str, Any]:
    """Read every registered engine and scan (``ActionBusy`` while a scan, or a worker it left running, is live)."""
    if (reason := sqla.unavailable_reason()) is not None:
        return service.scan(reason)
    single = ctx.lazy(f"singleflight:{OPERATION}", SingleFlight)
    release = single.try_acquire(OPERATION)
    if release is None:
        raise ActionBusy(OPERATION, single.active)
    flight = Flight(release)
    try:
        return service.scan(_with_app_facts(ctx, await read_sources(ctx, flight)))
    finally:
        flight.done()
