from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from engine.testsession.tsfakes import NODE, busy_part, call_test, event, part, passed_run, render_parts, source
from sharpit.engine.advisors.findings import AdvisorRun, Finding
from sharpit.engine.collectors.restapi.service import assess
from sharpit.engine.spi import ApiModel, ApiRouteInfo
from sharpit.engine.testsession.facts import PhaseFacts, TestFacts, TestKey
from sharpit.engine.testsession.gates import Budget, evaluate_test
from sharpit.engine.testsession.report import write_json, write_junit
from sharpit.engine.testsession.sink import TestSessionSink, report_masker, report_masker_warnings
from test_masking_corpus import AWS_KEY, GITHUB_TOKEN, JWT, SENTINEL, STRIPE_KEY

KEYS = {
    "": [
        "advisors",
        "filtered",
        "findings",
        "gates",
        "generatedAt",
        "schema",
        "severityCounts",
        "sources",
        "status",
        "statusReasons",
        "tests",
        "tool",
        "totals",
        "unattributed",
        "warnings",
        "workers",
    ],
    "tool": ["name", "version"],
    "gates": ["allowUnknown", "failOnSeverity", "maxQueriesPerTest", "maxUnattributedPercent", "nPlusOneThreshold"],
    "totals": ["exceptions", "filtered", "queries", "tests", "unattributed", "unattributedShare"],
    "unattributed": ["queries", "topStatements"],
    "filtered": ["count", "rules"],
    "sources[]": ["attached", "limitations", "name", "reason"],
    "workers[]": ["id", "status"],
    "severityCounts[]": ["count", "severity"],
    "tests[]": ["attempt", "budget", "findings", "nPlusOne", "nodeId", "outcome", "phases", "worker"],
    "tests[].budget": ["allowNPlusOne", "maxExceptions", "maxQueries"],
    "tests[].phases": ["call", "setup", "teardown"],
    "tests[].phases.call": ["exceptions", "filtered", "queries"],
    "advisors[]": ["advisor", "apps", "findings", "reason", "status"],
    "advisors[].apps[]": ["app", "evidence", "reason", "status"],
    "unattributed.topStatements[]": ["count", "sql"],
    "advisors[].findings[]": [
        "advisor",
        "dismissed",
        "fingerprint",
        "message",
        "ruleId",
        "severity",
        "target",
        "testNodeId",
    ],
    "advisors[].apps[].evidence": ["coverageComplete", "limitations", "usable"],
    "findings[]": [
        "advisor",
        "dismissed",
        "fingerprint",
        "message",
        "ruleId",
        "severity",
        "target",
        "testNodeId",
    ],
}


def _keys(value: Any) -> list[str]:
    return sorted(value)


def test_render_has_every_key() -> None:
    data = render_parts(busy_part())
    first_test = data["tests"][0]
    assert _keys(data) == KEYS[""]
    assert _keys(data["tool"]) == KEYS["tool"]
    assert _keys(data["gates"]) == KEYS["gates"]
    assert _keys(data["totals"]) == KEYS["totals"]
    assert _keys(data["unattributed"]) == KEYS["unattributed"]
    assert _keys(data["filtered"]) == KEYS["filtered"]
    assert _keys(data["sources"][0]) == KEYS["sources[]"]
    assert _keys(data["workers"][0]) == KEYS["workers[]"]
    assert _keys(data["severityCounts"][0]) == KEYS["severityCounts[]"]
    assert _keys(first_test) == KEYS["tests[]"]
    assert _keys(first_test["budget"]) == KEYS["tests[].budget"]
    assert _keys(first_test["phases"]) == KEYS["tests[].phases"]
    assert _keys(first_test["phases"]["call"]) == KEYS["tests[].phases.call"]
    assert _keys(data["advisors"][0]) == KEYS["advisors[]"]
    assert _keys(data["advisors"][0]["apps"][0]) == KEYS["advisors[].apps[]"]
    assert _keys(data["findings"][0]) == KEYS["findings[]"]


def test_render_nested_keys_of_statements_advisor_findings_and_evidence() -> None:
    finding = Finding("RAPI-MAP-001", "rest-api", "HIGH", "GET /x", "m")
    evidence = {"usable": True, "coverageComplete": True, "limitations": []}
    run = AdvisorRun.of("rest-api", [finding], evidence, app="App#00000001")
    data = render_parts(busy_part(), part("gw1", advisor_runs=[run]))
    advisor = next(a for a in data["advisors"] if a["findings"])
    assert _keys(data["unattributed"]["topStatements"][0]) == KEYS["unattributed.topStatements[]"]
    assert _keys(advisor["findings"][0]) == KEYS["advisors[].findings[]"]
    assert _keys(advisor["apps"][0]["evidence"]) == KEYS["advisors[].apps[].evidence"]


def test_render_header_and_totals() -> None:
    data = render_parts(busy_part())
    assert data["schema"] == "sharpit-report/1"
    assert data["tool"] == {"name": "sharpit", "version": "0.3.0"}
    assert data["generatedAt"] == 1_761_955_200_000
    assert data["status"] == "fail"
    assert data["statusReasons"] == ["1 test failed sharpit gates"]
    assert data["totals"] == {
        "tests": 2,
        "queries": 11,
        "filtered": 1,
        "unattributed": 1,
        "unattributedShare": 9.1,
        "exceptions": 1,
    }
    assert data["filtered"] == {
        "count": 1,
        "rules": ["PRAGMA", "sqlite_schema", "migration tables", "transaction control"],
    }


def test_render_keeps_nulls() -> None:
    bare = TestFacts(TestKey(NODE, "gw0", 1), phases={"call": PhaseFacts(queries=1)})
    data = render_parts(part(tests=[bare]))
    entry = data["tests"][0]
    assert entry["outcome"] is None
    assert entry["budget"] is None
    assert entry["phases"]["setup"] == {"queries": 0, "filtered": 0, "exceptions": 0}
    assert data["gates"]["maxQueriesPerTest"] is None
    assert data["sources"][0]["reason"] is None


def test_render_test_entry_and_findings() -> None:
    data = render_parts(busy_part())
    entry = next(t for t in data["tests"] if t["nodeId"] == NODE)
    assert entry["budget"] == {"maxQueries": 5, "allowNPlusOne": False, "maxExceptions": 0}
    assert entry["phases"]["setup"] == {"queries": 1, "filtered": 1, "exceptions": 0}
    assert entry["phases"]["call"] == {"queries": 8, "filtered": 0, "exceptions": 1}
    assert entry["nPlusOne"] == [{"sql": "SELECT * FROM pets WHERE owner_id = ?", "count": 8}]
    assert sorted(entry["findings"]) == sorted(f["fingerprint"] for f in data["findings"])
    assert [f["ruleId"] for f in data["findings"]] == ["sharpit.max-queries", "sharpit.n-plus-one", "sharpit.exception"]


def test_severity_counts_five_in_order() -> None:
    data = render_parts(busy_part())
    assert data["severityCounts"] == [
        {"severity": "CRITICAL", "count": 0},
        {"severity": "HIGH", "count": 3},
        {"severity": "MEDIUM", "count": 0},
        {"severity": "LOW", "count": 0},
        {"severity": "INFO", "count": 0},
    ]


def test_severity_counts_exclude_dismissed() -> None:
    facts = busy_part()
    facts.tests[0].findings[0]["dismissed"] = True
    data = render_parts(facts)
    assert data["severityCounts"][1] == {"severity": "HIGH", "count": 2}
    assert data["status"] == "fail"


def test_tests_complete_not_capped() -> None:
    many = [call_test(f"tests/test_x.py::test_{i}") for i in range(150)]
    assert len(render_parts(part(tests=many))["tests"]) == 150


def test_sql_caps() -> None:
    sink = TestSessionSink("gw0")
    attempt = sink.begin_test(NODE)
    for table in range(15):
        for _ in range(6):
            sink.on_sql(event(f"SELECT * FROM t{table} WHERE id = 1"), (NODE, attempt, "call"))
    for table in range(30):
        sink.on_sql(event(f"SELECT * FROM u{table}"), None)
    facts = sink.facts
    facts.sources = [source()]
    facts.advisor_runs = [passed_run()]
    data = render_parts(facts)
    assert len(data["tests"][0]["nPlusOne"]) == 10
    assert len(data["unattributed"]["topStatements"]) == 20
    assert data["unattributed"]["queries"] == 30


def test_advisors_disabled_are_listed_unknown() -> None:
    data = render_parts(part(advisor_runs=[]), advisors_enabled=False)
    assert data["advisors"] == [
        {"advisor": "rest-api", "status": "UNKNOWN", "reason": "advisors disabled", "apps": [], "findings": []}
    ]
    assert data["status"] == "pass"


def test_unknown_report_carries_reasons_and_workers() -> None:
    data = render_parts(part(sources=[]), missing=("gw1",))
    assert data["status"] == "unknown"
    assert "worker gw1 reported no sharpit facts" in data["statusReasons"]
    assert data["workers"] == [{"id": "gw0", "status": "ok"}, {"id": "gw1", "status": "missing"}]


def _junit(tmp_path: Path, data: dict[str, Any], *, allow_unknown: bool = False) -> ET.Element:
    target = tmp_path / "out" / "junit.xml"
    write_junit(target, data, allow_unknown=allow_unknown)
    return ET.fromstring(target.read_bytes())


def test_junit_parses(tmp_path: Path) -> None:
    root = _junit(tmp_path, render_parts(busy_part()))
    assert root.tag == "testsuite"
    assert root.get("name") == "sharpit"


def test_junit_one_case_per_finding_and_status(tmp_path: Path) -> None:
    data = render_parts(busy_part())
    root = _junit(tmp_path, data)
    cases = root.findall("testcase")
    assert len(cases) == len(data["findings"]) + 1
    first = cases[0]
    assert first.get("classname") == "test-runtime"
    assert first.get("name") == data["findings"][0]["fingerprint"]
    failure = first.find("failure")
    assert failure is not None
    assert failure.get("type") == "sharpit.max-queries"
    assert failure.get("message") == data["findings"][0]["message"]
    status = cases[-1]
    assert status.get("name") == "sharpit.status"
    assert status.find("failure") is not None
    assert root.get("tests") == str(len(cases))
    assert root.get("failures") == str(len(cases))


def test_junit_status_case_unknown_allowed(tmp_path: Path) -> None:
    data = render_parts(part(sources=[]))
    refused = _junit(tmp_path, data).findall("testcase")[-1]
    allowed = _junit(tmp_path, data, allow_unknown=True).findall("testcase")[-1]
    assert refused.find("failure") is not None
    assert allowed.find("failure") is None


def test_junit_pass_has_only_a_clean_status_case(tmp_path: Path) -> None:
    cases = _junit(tmp_path, render_parts(part())).findall("testcase")
    assert [c.get("name") for c in cases] == ["sharpit.status"]
    assert cases[0].find("failure") is None


def test_junit_dismissed_has_no_failure(tmp_path: Path) -> None:
    data = render_parts(busy_part())
    data["findings"][0]["dismissed"] = True
    cases = _junit(tmp_path, data).findall("testcase")
    assert cases[0].find("failure") is None
    assert cases[1].find("failure") is not None


def test_junit_failures_match_the_gate(tmp_path: Path) -> None:
    data = render_parts(part())
    medium = Finding("RAPI-MAP-001", "rest-api", "MEDIUM", "GET /medium", "medium")
    high = Finding("RAPI-MAP-002", "rest-api", "HIGH", "GET /high", "high")
    data["findings"] = [medium.to_dto(), high.to_dto()]
    data["gates"]["failOnSeverity"] = "HIGH"

    high_gate_cases = _junit(tmp_path, data).findall("testcase")
    assert sum(case.find("failure") is not None for case in high_gate_cases) == 1
    medium_case = next(case for case in high_gate_cases if case.get("name") == medium.fingerprint)
    assert medium_case.find("properties/property[@name='severity']").get("value") == "MEDIUM"

    data["gates"]["failOnSeverity"] = "MEDIUM"
    medium_gate_cases = _junit(tmp_path, data).findall("testcase")
    assert sum(case.find("failure") is not None for case in medium_gate_cases) == 2


def test_junit_survives_control_characters(tmp_path: Path) -> None:
    data = render_parts(busy_part())
    data["findings"][0]["message"] = "bad \x00 byte \x1b[0m"
    assert _junit(tmp_path, data).findall("testcase")


def test_write_json_atomic(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "report.json"
    write_json(target, {"schema": "sharpit-report/1", "name": "ü"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"schema": "sharpit-report/1", "name": "ü"}
    assert target.read_text(encoding="utf-8").startswith('{\n  "schema"')
    write_json(target, {"schema": "second"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"schema": "second"}
    assert [p.name for p in target.parent.iterdir()] == ["report.json"]


def test_write_json_survives_lone_surrogate(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    write_json(target, {"message": "bad\ud800text"})
    assert json.loads(target.read_text(encoding="utf-8"))["message"] == "bad�text"
    assert [p.name for p in target.parent.iterdir()] == ["report.json"]


def test_write_json_replace_failure_keeps_the_old_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "report.json"
    write_json(target, {"ok": True})

    def boom(src: object, dst: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="replace failed"):
        write_json(target, {"ok": False})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
    assert [p.name for p in tmp_path.iterdir()] == ["report.json"]


def test_write_json_failure_keeps_the_old_file(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    write_json(target, {"ok": True})
    with pytest.raises(TypeError):
        write_json(target, {"bad": object()})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
    assert [p.name for p in tmp_path.iterdir()] == ["report.json"]


SECRETS = (SENTINEL, JWT, STRIPE_KEY, AWS_KEY, GITHUB_TOKEN)
SHAPED = (JWT, STRIPE_KEY, AWS_KEY, GITHUB_TOKEN)  # recognisable by shape alone, as a bare path segment


def _corpus_facts() -> Any:
    """Every corpus secret planted as a bound parameter, an SQL literal, an exception message and a route path."""
    sink = TestSessionSink("gw0")
    attempt = sink.begin_test(NODE)
    tag = (NODE, attempt, "call")
    for secret in SECRETS:
        sink.on_sql(event("INSERT INTO t (v) VALUES (?)", parameters=(secret,)), tag)
        sink.on_sql(event("INSERT INTO t (v) VALUES (?)", parameters=[(secret,)], batch=1), None)
        sink.on_sql(event(f"SELECT * FROM t WHERE v = '{secret}'"), tag)
        sink.on_sql(event(f"SELECT * FROM t WHERE v = '{secret}'"), None)
        sink.on_exception(ValueError(f"login failed password={secret} token={secret}"), "logging", tag)
        sink.on_exception(ConnectionError(f"cannot reach postgres://u:{secret}@h/db"), "logging", tag)
    for secret in SHAPED:
        sink.on_exception(RuntimeError(f"bad credential {secret}"), "logging", tag)
    assert sink.current_test is not None
    sink.current_test.budget = Budget(None, False, 0)
    sink.current_test.findings = [f.to_dto() for f in evaluate_test(sink.current_test, sink.current_test.budget, 5, ())]
    sink.end_test()
    paths = [f"/reset/{secret}" for secret in SHAPED] + [f"/conn/Server=db;Password={SENTINEL}"]
    routes = tuple(ApiRouteInfo(("GET",), path, "app:handler") for path in paths)
    run = assess(ApiModel(routes, (), ()), report_masker(), app="Corpus API#00000000")
    facts = sink.facts
    facts.sources = [source(), source("exceptions")]
    facts.advisor_runs = [run]
    facts.warnings = report_masker_warnings(os.environ)
    return facts


def _corpus_report(tmp_path: Path) -> str:
    data = render_parts(_corpus_facts())
    write_json(tmp_path / "report.json", data)
    write_junit(tmp_path / "junit.xml", data, allow_unknown=False)
    text = (tmp_path / "report.json").read_text(encoding="utf-8") + (tmp_path / "junit.xml").read_text(encoding="utf-8")
    assert "GET /reset/" in text  # the planted routes did reach the report: the scan below is not vacuous
    assert "sharpit.exception" in text
    return text


def _assert_clean(text: str) -> None:
    assert [s for s in SECRETS if s in text] == []


def test_report_corpus_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B4, Review Focus 1: no corpus secret in either file under the default settings."""
    monkeypatch.delenv("SHARPIT_EXPOSE_VALUES", raising=False)
    monkeypatch.delenv("SHARPIT_MASK_SECRETS", raising=False)
    _assert_clean(_corpus_report(tmp_path))


def test_report_corpus_full_exposure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B4: ``SHARPIT_EXPOSE_VALUES=FULL`` never reaches a report, and the report says it ignored it."""
    monkeypatch.setenv("SHARPIT_EXPOSE_VALUES", "FULL")
    text = _corpus_report(tmp_path)
    _assert_clean(text)
    assert "report ignores SHARPIT_EXPOSE_VALUES=FULL" in text


def test_report_corpus_masking_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B4: ``SHARPIT_MASK_SECRETS=false`` never reaches a report, and the report says it ignored it."""
    monkeypatch.setenv("SHARPIT_MASK_SECRETS", "false")
    text = _corpus_report(tmp_path)
    _assert_clean(text)
    assert "report ignores SHARPIT_MASK_SECRETS=false" in text
