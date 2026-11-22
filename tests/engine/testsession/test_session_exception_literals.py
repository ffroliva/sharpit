"""Exception messages in the test-session report: scrubbed of binding literals in JSON, JUnit and SARIF.

The sink keeps the masked message of each exception group and every writer reads it back, so the scrub is applied
where the sink stores it (port of BootUI ``ExceptionsService.displayMessage``, which scrubs the exposed message).
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.testsession.tsfakes import NODE, render_parts
from sharpit.engine.masking import MASK
from sharpit.engine.testsession.facts import SessionFacts
from sharpit.engine.testsession.gates import Budget, evaluate_test
from sharpit.engine.testsession.report import write_json, write_junit
from sharpit.engine.testsession.sarif import write_sarif
from sharpit.engine.testsession.sink import TestSessionSink, report_masker

SENTINEL = "ordinary-sentinel-91"


def _facts(*errors: BaseException) -> SessionFacts:
    sink = TestSessionSink("gw0")
    attempt = sink.begin_test(NODE)
    for error in errors:
        sink.on_exception(error, "logging", (NODE, attempt, "call"))
    assert sink.current_test is not None
    sink.current_test.budget = Budget(None, False, 0)
    sink.current_test.findings = [f.to_dto() for f in evaluate_test(sink.current_test, sink.current_test.budget, 5, ())]
    sink.end_test()
    return sink.facts


def test_pytest_exception_fallback_and_exporters_scrub_messages(tmp_path: Path) -> None:
    data = render_parts(
        _facts(
            ValueError(f"invalid literal for int() with base 10: '{SENTINEL}-main'"),
            KeyError(f"time data '{SENTINEL}-key' does not match format '%Y'"),
        )
    )
    write_json(tmp_path / "report.json", data)
    write_junit(tmp_path / "junit.xml", data, allow_unknown=False)
    write_sarif(tmp_path / "report.sarif", data, report_masker())

    json_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    junit_text = (tmp_path / "junit.xml").read_text(encoding="utf-8")
    sarif_text = (tmp_path / "report.sarif").read_text(encoding="utf-8")

    assert "sharpit.exception" in json_text
    for name, text in (("json", json_text), ("junit", junit_text), ("sarif", sarif_text)):
        assert f"{SENTINEL}-main" not in text, name
        assert f"{SENTINEL}-key" not in text, name
    assert f"invalid literal for int() with base 10: '{MASK}'" in json_text
    assert json.loads(sarif_text)["runs"][0]["results"]


def test_arbitrary_runtime_error_message_is_not_claimed_scrubbed() -> None:
    sink = TestSessionSink("gw0")
    attempt = sink.begin_test(NODE)

    sink.on_exception(RuntimeError(f"cannot process '{SENTINEL}-plain' right now"), "logging", (NODE, attempt, "call"))

    assert sink.current_test is not None
    assert SENTINEL in repr(sink.current_test.phases["call"].exception_groups)
