from __future__ import annotations

from dataclasses import replace

from engine.testsession.tsfakes import part, source
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


HOOK = "a sharpit session hook failed (RuntimeError); some facts may be missing"


def _failed_part(worker: str) -> SessionFacts:
    """A part whose own sink recorded a hook failure, as the sink does."""
    plugin = source("pytest-plugin", attached=False, reason=HOOK)
    return part(worker, sources=[source(), source("exceptions"), plugin], warnings=[HOOK])


def _unknown_reasons(parts: list[SessionFacts], warnings: list[str]) -> list[str]:
    data, _status, _reasons = finish(parts, [], options=OPTIONS, version="0.3.0", now_ms=1, warnings=warnings)
    return data["unknownReasons"]


def test_a_serial_hook_failure_gives_one_reason() -> None:
    """In a serial run the controller is the only part: its failure is named once, for its own worker."""
    data, _status, _reasons = finish(
        [_failed_part("master")], [], options=OPTIONS, version="0.3.0", now_ms=1, warnings=[HOOK]
    )
    assert data["unknownReasons"] == ["source 'pytest-plugin' not attached in worker master"]
    assert [source["name"] for source in data["sources"]].count("pytest-plugin") == 1


def test_a_controller_hook_failure_makes_an_xdist_run_unknown() -> None:
    """The xdist controller is no part: its own failure is added by name."""
    assert _unknown_reasons([part("gw0")], [HOOK]) == ["source 'pytest-plugin' not attached in worker controller"]


def test_a_controller_hook_failure_is_named_beside_a_worker_failure() -> None:
    assert _unknown_reasons([_failed_part("gw0")], [HOOK]) == [
        "source 'pytest-plugin' not attached in worker gw0",
        "source 'pytest-plugin' not attached in worker controller",
    ]


def test_a_controller_warning_that_is_no_hook_failure_leaves_the_run_known() -> None:
    assert _unknown_reasons([part("gw0")], ["report ignores SHARPIT_EXPOSE_VALUES=FULL"]) == []


def test_finish_reports_unknown_without_an_application() -> None:
    facts = SessionFacts("master")
    data, status, reasons = finish([facts], [], options=OPTIONS, version="0.3.0", now_ms=1, warnings=[])
    assert status == "unknown"
    assert (
        "advisor 'rest-api' could not assess: no application: pass --sharpit-app or call sharpit.install in the tests"
        in reasons
    )
    assert data["advisors"][0]["apps"] == []


def test_finish_names_the_threshold_in_the_partial_note() -> None:
    limits = {"usable": True, "coverageComplete": False, "limitations": ["a mount has no routes"]}
    facts = part(advisor_runs=[AdvisorRun.of("rest-api", [], limits, app="app")])
    data, status, reasons = finish(
        [facts], [], options=replace(OPTIONS, fail_on="MEDIUM"), version="0.3.0", now_ms=1, warnings=[]
    )
    assert (status, reasons) == ("pass", [])
    assert data["advisors"][0]["status"] == "PARTIAL"
    assert data["warnings"] == [
        "advisor 'rest-api' assessed part of app: a mount has no routes; "
        "having no finding at or above MEDIUM is not proof there is none"
    ]
