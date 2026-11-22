"""HTTP security findings through the pytest report, xdist and the baseline (T1, Task 6)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from engine.testsession.tsfakes import part
from sharpit.engine.advisors.http_security import HeaderExpectation, StatusExpectation
from sharpit.engine.testsession.facts import TestFacts, TestKey
from sharpit.engine.testsession.finish import GateOptions, finish

FRAME = HeaderExpectation("GET", "/items", "x-frame-options")
HEADER = "--sharpit-required-response-header"
EXPECT = ("--sharpit", "--sharpit-http-security", HEADER, "GET /items=X-Frame-Options", "--sharpit-report=report.json")
APP = """
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()
HEADERS = {}

@app.get("/items")
def items():
    return JSONResponse({"ok": True}, headers=HEADERS)
"""
SECURE_APP = APP.replace("HEADERS = {}", 'HEADERS = {"X-Frame-Options": "DENY"}')
CALLER = """
from fastapi.testclient import TestClient
from app import app

def test_items(sharpit_http_observed):
    assert TestClient(sharpit_http_observed(app)).get("/items").status_code == 200
"""
IDLE = "def test_idle(): pass"


def _http(report: dict[str, Any]) -> dict[str, Any] | None:
    return next((a for a in report["advisors"] if a["advisor"] == "http-security"), None)


def _run(pytester: pytest.Pytester, *args: str) -> tuple[pytest.RunResult, dict[str, Any]]:
    result = pytester.runpytest_subprocess(*args)
    return result, json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))


def _two_files(pytester: pytest.Pytester, app: str = SECURE_APP) -> None:
    pytester.makepyfile(app=app, test_left=CALLER, test_right=IDLE)


def test_http_security_controller_evaluates_only_after_xdist_merge(pytester: pytest.Pytester) -> None:
    _two_files(pytester)

    _result, report = _run(pytester, *EXPECT, "-n", "2", "--dist", "loadfile", "--sharpit-allow-unknown")

    advisor = _http(report)
    assert advisor is not None
    assert advisor["status"] == "PASSED"
    assert len(report["workers"]) == 2
    assert [r for r in report["unknownReasons"] if "http-security" in r] == []
    assert report["status"] != "fail"


def test_http_security_report_merges_xdist_findings_and_baselines(pytester: pytest.Pytester) -> None:
    _two_files(pytester, APP)

    result, report = _run(pytester, *EXPECT, "-n", "2", "--dist", "loadfile", "--sharpit-allow-unknown")

    advisor = _http(report)
    assert advisor is not None
    assert advisor["status"] == "FAILED"
    assert [f["ruleId"] for f in report["findings"] if f["advisor"] == "http-security"] == ["HTTP-SEC-001"]
    assert result.ret == 1


def test_http_security_baseline_accepts_only_stable_fingerprints(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(app=APP, test_left=CALLER)
    args = (*EXPECT, "--sharpit-allow-unknown")
    _run(pytester, *args, "--sharpit-report-only", "--sharpit-write-baseline=base.json")
    baseline = json.loads((pytester.path / "base.json").read_text(encoding="utf-8"))
    fingerprints = [e["fingerprint"] for e in baseline["findings"] if e["fingerprint"].startswith("http-security:")]

    result, report = _run(pytester, *args, "--sharpit-baseline=base.json")

    assert len(fingerprints) == 1
    assert fingerprints[0].startswith("http-security:HTTP-SEC-001:")
    assert [f["baselineState"] for f in report["findings"] if f["advisor"] == "http-security"] == ["existing"]
    assert result.ret == 0


def test_http_security_baseline_does_not_hide_a_different_fingerprint(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(app=APP, test_left=CALLER)
    row = {"fingerprint": "http-security:HTTP-SEC-001:0000000000000000", "ruleId": "HTTP-SEC-001"}
    row |= {"target": "GET /items", "message": "stale", "observed": None}
    baseline = {"schema": "sharpit-baseline/1", "findings": [row]}
    (pytester.path / "base.json").write_text(json.dumps(baseline), encoding="utf-8")

    result, report = _run(pytester, *EXPECT, "--sharpit-baseline=base.json", "--sharpit-allow-unknown")

    assert [f["baselineState"] for f in report["findings"] if f["advisor"] == "http-security"] == ["new"]
    assert result.ret == 1


def test_http_security_malformed_baseline_fails_closed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(app=SECURE_APP, test_left=CALLER)
    bogus = {"schema": "sharpit-baseline/1", "findings": [{"fingerprint": "http-security:HTTP-SEC-001:not-hex"}]}
    (pytester.path / "base.json").write_text(json.dumps(bogus), encoding="utf-8")

    result, report = _run(pytester, *EXPECT, "--sharpit-baseline=base.json")

    assert any("baseline unusable" in reason for reason in report["unknownReasons"])
    assert result.ret != 0


def test_http_security_partial_run_refuses_baseline_write(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(app=SECURE_APP, test_left=CALLER, test_right=IDLE)

    result = pytester.runpytest_subprocess(*EXPECT, "-k", "test_items", "--sharpit-write-baseline=base.json")

    assert result.ret != 0
    assert not (pytester.path / "base.json").exists()
    assert "refusing to write baseline" in result.stderr.str() + result.stdout.str()


def test_http_security_selection_run_expectation_is_unknown(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(app=SECURE_APP, test_left=CALLER, test_right=IDLE)

    result, report = _run(pytester, *EXPECT, "-k", "test_idle")

    advisor = _http(report)
    assert advisor is not None
    assert advisor["status"] == "UNKNOWN"
    assert "selection run" in advisor["reason"]
    assert any("http-security" in r and "selection run" in r for r in report["unknownReasons"])
    assert result.ret != 0


def test_http_security_selection_run_allow_unknown_does_not_fail_on_the_expectation(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(app=SECURE_APP, test_left=CALLER, test_right=IDLE)

    _result, report = _run(pytester, *EXPECT, "-k", "test_idle", "--sharpit-allow-unknown")

    advisor = _http(report)
    assert advisor is not None
    assert advisor["status"] == "UNKNOWN"
    assert report["status"] != "fail"


def _facts(node: str, worker: str, *exchanges: tuple[str, str, int, tuple[str, ...]]) -> Any:
    facts = part(worker=worker)
    test = TestFacts(TestKey(node, worker, 1))
    for method, route, status, present in exchanges:
        test.http.record(method, "matched", route, status, present)
    facts.tests.append(test)
    return facts


def _finish(parts: list[Any], missing: list[str], **options: Any) -> tuple[dict[str, Any], str, list[str]]:
    gate = replace(
        GateOptions(None, 5, "HIGH", False, 10.0, True),
        http_headers=(FRAME,),
        http_statuses=(StatusExpectation("GET", "/gone", (200,)),),
        **options,
    )
    return finish(parts, missing, options=gate, version="0.8.0", now_ms=1, warnings=[])


def test_http_security_missing_worker_makes_expectation_unknown() -> None:
    clean = _facts("a.py::t", "gw0", ("GET", "/items", 200, ("x-frame-options",)), ("GET", "/gone", 200, ()))

    data, status, _reasons = _finish([clean], ["gw1"])

    advisor = _http(data)
    assert advisor is not None
    assert advisor["status"] == "UNKNOWN"
    assert "missing worker" in advisor["reason"]
    assert status == "unknown"


def test_http_security_worker_crash_never_passes_expectation() -> None:
    data, status, _reasons = _finish([_facts("a.py::t", "gw0")], ["gw1"])

    advisor = _http(data)
    assert advisor is not None
    assert advisor["status"] != "PASSED"
    assert status != "pass"


def test_http_security_failed_exchange_precedes_unknown() -> None:
    bad = _facts("a.py::t", "gw0", ("GET", "/items", 200, ()))

    data, status, reasons = _finish([bad], [])

    advisor = _http(data)
    assert advisor is not None
    assert advisor["status"] == "FAILED"
    assert "no matching exchange" in advisor["reason"]
    assert status == "fail"
    assert reasons == ["advisor 'http-security' found 1 finding at or above HIGH"]
    assert any("no matching exchange" in r for r in data["unknownReasons"])


def test_http_security_finding_text_is_masked_before_output() -> None:
    secret = HeaderExpectation("GET", "/login?password=hunter2-canary", "x-frame-options")
    facts = _facts("a.py::t", "gw0", ("GET", "/login?password=hunter2-canary", 200, ()))
    gate = replace(GateOptions(None, 5, "HIGH", False, 10.0, True), http_headers=(secret,))

    data, _status, _reasons = finish([facts], [], options=gate, version="0.8.0", now_ms=1, warnings=[])

    assert [f["ruleId"] for f in data["findings"]] == ["HTTP-SEC-001"]
    assert "hunter2-canary" not in json.dumps(data["findings"])
