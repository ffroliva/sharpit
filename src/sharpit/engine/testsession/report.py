"""The ``sharpit-report/1`` writers (0.3.0 spec §7): one render, a JSON file and a JUnit file read from it.

Every string in the facts was masked when the sink recorded it; the writers add no app text of their own.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from sharpit.engine.advisors.report import severity_counts
from sharpit.engine.advisors.rules import SEVERITIES
from sharpit.engine.testsession.facts import PHASES, PhaseFacts, TestFacts
from sharpit.engine.testsession.filters import FILTER_RULES
from sharpit.engine.testsession.outcome import (
    MergedFacts,
    advisor_summaries,
    attributed_queries,
    deciding,
    unattributed_share,
)

SCHEMA = "sharpit-report/1"
MAX_N_PLUS_ONE = 10  # per test
MAX_TOP_STATEMENTS = 20
_XML_ILLEGAL = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]")


def _test_entry(test: TestFacts, threshold: int) -> dict[str, Any]:
    call = test.phases.get("call") or PhaseFacts()
    groups = sorted(((n, g) for g, n in call.selects.items() if n >= threshold), key=lambda x: (-x[0], x[1]))
    budget = test.budget
    return {
        "nodeId": test.key.node_id,
        "worker": test.key.worker,
        "attempt": test.key.attempt,
        "outcome": test.outcome,
        "budget": None
        if budget is None
        else {
            "maxQueries": budget.max_queries,
            "allowNPlusOne": budget.allow_n_plus_one,
            "maxExceptions": budget.max_exceptions,
        },
        "phases": {
            name: {
                "queries": phase.queries if (phase := test.phases.get(name)) else 0,
                "filtered": phase.filtered if phase else 0,
                "exceptions": phase.exceptions if phase else 0,
            }
            for name in PHASES
        },
        "nPlusOne": [
            {"sql": call.sql_of.get(group, group), "count": count} for count, group in groups[:MAX_N_PLUS_ONE]
        ],
        "findings": [f["fingerprint"] for f in test.findings],
    }


def render(
    merged: MergedFacts,
    status: str,
    reasons: list[str],
    *,
    gates: dict[str, Any],
    version: str,
    now_ms: int,
    advisors_enabled: bool = True,
) -> dict[str, Any]:
    """The report as a dict: every key of spec §7.1 present, nulls kept, camelCase, epoch ms."""
    attributed = attributed_queries(merged.tests)
    threshold = max(2, int(gates["nPlusOneThreshold"]))
    exceptions = sum(p.exceptions for t in merged.tests for p in t.phases.values()) + merged.unattributed_exceptions
    return {
        "schema": SCHEMA,
        "tool": {"name": "sharpit", "version": version},
        "generatedAt": now_ms,
        "status": status,
        "statusReasons": reasons,
        "warnings": merged.warnings,
        "gates": gates,
        "sources": merged.sources,
        "workers": merged.workers,
        "severityCounts": severity_counts(
            ((f["severity"], 1) for f in merged.findings if not f["dismissed"]), SEVERITIES
        ),
        "totals": {
            "tests": len(deciding(merged.tests)),
            "queries": attributed + merged.unattributed,
            "filtered": merged.filtered,
            "unattributed": merged.unattributed,
            "unattributedShare": unattributed_share(attributed, merged.unattributed),
            "exceptions": exceptions,
        },
        "tests": [_test_entry(t, threshold) for t in merged.tests],
        "unattributed": {"queries": merged.unattributed, "topStatements": merged.top_unattributed[:MAX_TOP_STATEMENTS]},
        "filtered": {"count": merged.filtered, "rules": list(FILTER_RULES)},
        "advisors": advisor_summaries(merged, advisors_enabled=advisors_enabled),
        "findings": merged.findings,
    }


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    """UTF-8, ``indent=2``, atomic (a temporary file, then ``os.replace``); serialised before anything is touched."""
    _write_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _clean(text: str) -> str:
    return _XML_ILLEGAL.sub("�", text)


def write_junit(path: Path, data: dict[str, Any], *, allow_unknown: bool) -> None:
    """Spec §7.2: one testcase per finding plus ``sharpit.status``; reads only ``data``."""
    suite = ET.Element("testsuite", name="sharpit")
    cases = 0
    failures = 0
    for finding in data["findings"]:
        case = ET.SubElement(suite, "testcase", classname=finding["advisor"], name=finding["fingerprint"])
        cases += 1
        if not finding["dismissed"]:
            failure = ET.SubElement(case, "failure", type=finding["ruleId"], message=_clean(finding["message"]))
            failure.text = _clean(finding["target"])
            failures += 1
    status = data["status"]
    case = ET.SubElement(suite, "testcase", classname="sharpit", name="sharpit.status")
    cases += 1
    if status == "fail" or (status == "unknown" and not allow_unknown):
        failure = ET.SubElement(case, "failure", type=status, message=_clean("; ".join(data["statusReasons"])))
        failure.text = _clean("\n".join(data["statusReasons"]))
        failures += 1
    suite.set("tests", str(cases))
    suite.set("failures", str(failures))
    suite.set("errors", "0")
    ET.indent(suite)
    _write_atomic(path, f'<?xml version="1.0" encoding="UTF-8"?>\n{ET.tostring(suite, encoding="unicode")}\n')
