from __future__ import annotations

from engine.testsession.tsfakes import part
from sharpit.engine.advisors.findings import AdvisorRun, Finding
from sharpit.engine.testsession.facts import SessionFacts
from sharpit.engine.testsession.finish import GateOptions, finish

OPTIONS = GateOptions(None, 5, "HIGH", False, 10.0, True)


def test_finish_passes_clean_facts() -> None:
    data, status, reasons = finish([part()], [], options=OPTIONS, version="0.3.0", now_ms=1, warnings=[])
    assert status == "pass"
    assert reasons == []
    assert data["status"] == "pass"


def test_finish_fails_on_high_advisor_finding() -> None:
    facts = part()
    finding = Finding("rule", "rest-api", "HIGH", "route", "message")
    facts.advisor_runs = [AdvisorRun("rest-api", "FAILED", (finding,), {}, None, "app")]
    data, status, reasons = finish([facts], [], options=OPTIONS, version="0.3.0", now_ms=1, warnings=[])
    assert status == "fail"
    assert reasons == ["advisor 'rest-api' found 1 finding at or above HIGH"]
    assert data["status"] == "fail"


def test_finish_reports_unknown_without_an_application() -> None:
    facts = SessionFacts("master")
    data, status, reasons = finish([facts], [], options=OPTIONS, version="0.3.0", now_ms=1, warnings=[])
    assert status == "unknown"
    assert (
        "advisor 'rest-api' could not assess: no application: pass --sharpit-app or call sharpit.install in the tests"
        in reasons
    )
    assert data["advisors"][0]["apps"] == []
