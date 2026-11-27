"""Session report serialization and exit-status calculation."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from typing import Any, cast

import pytest

from sharpit import __version__
from sharpit.engine.advisors.findings import assessed_in_part
from sharpit.engine.testsession import baseline as baseline_io
from sharpit.engine.testsession import gates, outcome, report, sarif
from sharpit.engine.testsession.facts import TestFacts, finding_from
from sharpit.engine.testsession.finish import HOOK_FAILURE_PREFIX, GateOptions, finish


def write_report(state: Any, session: Any, exitstatus: int) -> None:
    from sharpit import pytest_plugin

    plugin = cast(Any, pytest_plugin)
    sink = state.sink
    try:
        facts = plugin._final_facts(state)  # forced app snapshot precedes advisor assessment
        parts = _report_parts(plugin, session, state, facts)
        warnings = list(sink.facts.warnings)
        if (
            state.options.baseline
            and not state.settings.identity_key
            and sink.masker.identity_key is not None
            and any(part.sqlite_seen for part in parts)
        ):
            warnings.append(
                "SQLite baseline fingerprints use a local identity key and may differ across machines; "
                "set SHARPIT_IDENTITY_KEY in CI to a shared key."
            )
        data, _status, _reasons = finish(
            parts,
            state.missing_workers,
            options=GateOptions(
                state.options.max_queries,
                state.settings.activity_n_plus_one_threshold,
                state.options.fail_on,
                state.options.allow_unknown,
                state.options.max_unattributed,
                state.options.advisors,
                report_only=state.options.report_only,
                http_headers=state.options.http_required_headers,
                http_statuses=state.options.http_expected_statuses,
                partial_run=state.partial,
                baseline=None if state.baseline_observed is None else frozenset(state.baseline_observed),
            ),
            version=__version__,
            now_ms=time.time_ns() // 1_000_000,
            warnings=warnings,
        )
        _apply_baseline(state, data, [test for part in parts for test in part.tests])
        refusal = _baseline_refusal(state, data)
        if not refusal:
            _write_baseline(state, data)  # before the report, so a write failure is in it
        _write_sarif(state, data, sink.masker)  # likewise
        report.write_json(state.options.report, data)
        if state.options.junit:
            report.write_junit(state.options.junit, data, allow_unknown=state.options.allow_unknown)
        if refusal:
            raise pytest.UsageError(refusal)
        if exitstatus == 0 and outcome.exit_fails(
            data["status"],
            state.options.allow_unknown,
            report_only=state.options.report_only,
            unknown_reasons=data["unknownReasons"],
        ):
            session.exitstatus = 1
        session._sharpit_report = data
        session.config._sharpit_report = data
    except pytest.UsageError:
        raise
    except Exception as exc:  # noqa: BLE001
        plugin._record_hook_failure(sink, exc)
        if exitstatus == 0:
            session.exitstatus = 1


def _report_parts(plugin: Any, session: Any, state: Any, facts: Any) -> list[Any]:
    if plugin._xdist_controller(session.config, state):
        return state.parts
    plugin._advisors(state)
    return [facts]


def _has_gap(advisor: dict[str, Any]) -> bool:
    return any(app["evidence"].get("coverageComplete") is False for app in advisor["apps"])


def _assessed_in_full(advisor: dict[str, Any]) -> bool:
    """Only an advisor that read the whole app can say a baselined entry is gone, whatever its status."""
    return advisor["status"] in {"PASSED", "FAILED"} and advisor["reason"] is None and not _has_gap(advisor)


def _assessed_only_in_part(advisor: dict[str, Any]) -> bool:
    return advisor["status"] == "PARTIAL" or any(
        assessed_in_part(str(app["status"]), app.get("reason"), app["evidence"]) for app in advisor["apps"]
    )


# the rules fed by SQLAlchemy capture: a driver call outside SQLAlchemy reaches none of them
_SQL_RULES = (gates.MAX_QUERIES, gates.N_PLUS_ONE, gates.UNBOUNDED_READ)


def _limited(data: dict[str, Any], name: str, suffix: str = "") -> bool:
    source = next((s for s in data["sources"] if s["name"] == name), None)
    return source is not None and any(str(x).endswith(suffix) for x in source["limitations"])


def _incomplete_rules(data: dict[str, Any]) -> tuple[str, ...]:
    """The rules whose silence proves nothing: all when capture was lost, the SQL ones when SQL ran untraced."""
    if data["unknownReasons"] or any(w.startswith(HOOK_FAILURE_PREFIX) for w in data["warnings"]):
        return gates.GATE_IDS
    if _limited(data, "sqlalchemy", outcome.OUTSIDE_SQLALCHEMY):
        return _SQL_RULES
    return (gates.UNBOUNDED_READ,) if _limited(data, "unbounded-read") else ()


def _apply_baseline(state: Any, data: dict[str, Any], tests: Sequence[TestFacts] = ()) -> None:
    if state.baseline_data is None:
        return
    ran = {"test-runtime"} | {a["advisor"] for a in data["advisors"] if _assessed_in_full(a)}
    in_part = {a["advisor"] for a in data["advisors"] if _assessed_only_in_part(a)}
    comparison = baseline_io.compare(
        [finding_from(finding) for finding in data["findings"]],
        state.baseline_data,
        partial=state.partial,
        ran=ran,
        in_part=in_part,
        tests=tests,
        incomplete=_incomplete_rules(data),
    )
    state.baseline_carried = comparison.carried
    by_fingerprint = {finding.fingerprint: finding for finding in comparison.findings}
    data["findings"] = [
        {**finding, "baselineState": by_fingerprint[finding["fingerprint"]].baseline_state}
        for finding in data["findings"]
    ]
    for advisor in data["advisors"]:
        advisor["findings"] = [
            {**finding, "baselineState": by_fingerprint[finding["fingerprint"]].baseline_state}
            for finding in advisor["findings"]
        ]
    data["baseline"] = {
        "path": str(state.options.baseline),
        "sha256": hashlib.sha256(state.baseline_data.raw).hexdigest(),
        "existing": sum(f.baseline_state == "existing" for f in comparison.findings),
        "new": sum(f.baseline_state == "new" for f in comparison.findings),
        "fixed": None if comparison.fixed is None else len(comparison.fixed),
        "fixedReason": comparison.fixed_reason,
        "inconclusive": None if state.partial else len(comparison.inconclusive),
        "inconclusiveFindings": None
        if state.partial
        else [{"fingerprint": entry.fingerprint, "reason": reason} for entry, reason in comparison.inconclusive],
    }


def _baseline_refusal(state: Any, data: dict[str, Any]) -> str | None:
    if not state.options.write_baseline:
        return None
    if state.partial:
        return "sharpit: refusing to write baseline: partial run"
    if data["unknownReasons"]:
        return "sharpit: refusing to write baseline: unknown reasons are present"
    return None


def _write_sarif(state: Any, data: dict[str, Any], masker: Any) -> None:
    if not state.options.sarif:
        return
    try:
        sarif.write_sarif(state.options.sarif, data, masker)
    except OSError as exc:
        _unknown(data, f"SARIF write failed: {exc}")


def _unknown(data: dict[str, Any], reason: str) -> None:
    """A write that failed after the gates ran: the run is unknown, and the report and terminal say why."""
    data["unknownReasons"].append(reason)
    data["warnings"].append(reason)  # the terminal summary prints warnings
    if data["status"] == "pass":
        data["status"] = "unknown"
        data["statusReasons"] = list(data["unknownReasons"])


def _write_baseline(state: Any, data: dict[str, Any]) -> None:
    if not state.options.write_baseline:
        return
    try:
        baseline_io.write(
            state.options.write_baseline,
            [finding_from(finding) for finding in data["findings"]],
            state.baseline_carried,
        )
    except (OSError, ValueError) as exc:
        _unknown(data, f"baseline write failed: {exc}")
