"""The HTTP security advisor: explicit response expectations, evaluated per finished exchange (T1, Task 2)."""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any

from sharpit.engine.advisors.findings import AdvisorRun
from sharpit.engine.advisors.http_security import HeaderExpectation, StatusExpectation, evaluate
from sharpit.engine.advisors.registry import advisor_for
from sharpit.engine.testsession.facts import HttpFacts, TestFacts, TestKey
from sharpit.engine.testsession.sink import TestSessionSink

NODE = "tests/test_items.py::test_list"
FRAME = HeaderExpectation("GET", "/items", "x-frame-options")
SNIFF = HeaderExpectation("GET", "/items", "x-content-type-options")
STATUS = StatusExpectation("GET", "/items", (200, 304))
Exchange = tuple[str, str, int, tuple[str, ...]]


def _attempt(*exchanges: Exchange, node: str = NODE, worker: str = "gw0", attempt: int = 1) -> TestFacts:
    facts = TestFacts(TestKey(node, worker, attempt))
    for method, route, status, present in exchanges:
        facts.http.record(method, "matched", route, status, present)
    return facts


def _run(
    headers: tuple[HeaderExpectation, ...] = (),
    statuses: tuple[StatusExpectation, ...] = (),
    tests: TestFacts | tuple[TestFacts, ...] = (),
    **options: Any,
) -> AdvisorRun:
    run = evaluate(headers, statuses, (tests,) if isinstance(tests, TestFacts) else tests, **options)
    assert run is not None
    return run


def _rules(run: AdvisorRun) -> list[str]:
    return sorted(finding.rule_id for finding in run.findings)


def test_http_security_rule_is_registered() -> None:
    spec = advisor_for("HTTP-SEC-001")
    findings = _run(
        (FRAME,),
        tests=(
            _attempt(
                ("GET", "/items", 200, ()),
            )
        ),
        partial_run=False,
    ).findings

    assert len(findings) == 1
    assert spec is not None
    assert spec.id == "http-security"
    assert advisor_for("HTTP-SEC-002") is spec
    assert advisor_for(findings[0].fingerprint) is spec


def test_http_security_no_expectation_is_no_run() -> None:
    assert evaluate((), (), (_attempt(("GET", "/items", 500, ())),)) is None


def test_http_security_missing_configured_response_header_finding() -> None:
    run = _run(
        (FRAME,),
        tests=(
            _attempt(
                ("GET", "/items", 200, ()),
            )
        ),
    )

    assert run.status == "FAILED"
    assert _rules(run) == ["HTTP-SEC-001"]
    assert run.findings[0].severity == "HIGH"
    assert run.findings[0].target == "GET /items"
    assert run.findings[0].test_node_id is None
    assert "x-frame-options" in run.findings[0].message


def test_http_security_present_header_passes() -> None:
    run = _run(
        (FRAME,),
        tests=(
            _attempt(
                ("GET", "/items", 200, ("x-frame-options",)),
            )
        ),
    )

    assert run.status == "PASSED"
    assert run.evidence["exchanges"] == 1
    assert run.findings == ()


def test_http_security_expected_status_suppresses_finding() -> None:
    run = _run(
        statuses=(STATUS,),
        tests=(
            _attempt(
                ("GET", "/items", 304, ()),
            )
        ),
    )

    assert run.status == "PASSED"
    assert run.evidence["exchanges"] == 1
    assert run.findings == ()


def test_http_security_unexpected_status_finding() -> None:
    run = _run(
        statuses=(STATUS,),
        tests=(
            _attempt(
                ("GET", "/items", 500, ()),
            )
        ),
    )

    assert run.status == "FAILED"
    assert _rules(run) == ["HTTP-SEC-002"]
    assert run.findings[0].severity == "HIGH"
    assert "500" in run.findings[0].message
    assert "200, 304" in run.findings[0].message


def test_http_security_observed_500_without_status_expectation_is_not_a_finding() -> None:
    run = _run(
        (FRAME,),
        tests=(
            _attempt(
                ("GET", "/items", 500, ("x-frame-options",)),
            )
        ),
    )

    assert run.status == "PASSED"
    assert run.evidence["exchanges"] == 1
    assert run.findings == ()


def test_http_security_multiple_missing_headers_have_distinct_fingerprints() -> None:
    run = _run(
        (FRAME, SNIFF),
        tests=(
            _attempt(
                ("GET", "/items", 200, ()),
            )
        ),
    )

    assert _rules(run) == ["HTTP-SEC-001", "HTTP-SEC-001"]
    assert len({finding.fingerprint for finding in run.findings}) == 2


def test_http_security_unobserved_expectation_is_unknown() -> None:
    run = _run(
        (FRAME,),
        tests=(
            _attempt(
                ("GET", "/other", 200, ()),
            )
        ),
    )

    assert run.status == "UNKNOWN"
    assert run.reason is not None
    assert "no matching exchange" in run.reason
    assert run.findings == ()


def test_http_security_facts_do_not_accept_values_or_bodies() -> None:
    sink = TestSessionSink("gw0")
    sink.configure_http((FRAME,), ())
    sink.begin_test(NODE)

    sink.on_http("GET", "matched", "/items", 200, ["Authorization", "Set-Cookie", "X-Frame-Options", "x-secret"])
    stored = json.dumps(sink.facts.tests[0].to_json()["http"])

    assert list(inspect.signature(HttpFacts.record).parameters) == [
        "self",
        "method",
        "state",
        "route",
        "status",
        "present",
    ]
    assert "x-frame-options" in stored
    assert "authorization" not in stored.lower()
    assert "cookie" not in stored.lower()
    assert "x-secret" not in stored


def test_http_security_finding_fingerprint_ignores_test_attempt() -> None:
    one = _run((FRAME,), tests=(_attempt(("GET", "/items", 200, ()), node="a.py::one", worker="gw0"),))
    two = _run((FRAME,), tests=(_attempt(("GET", "/items", 200, ()), node="b.py::two", worker="gw3", attempt=4),))

    assert len(one.findings) == len(two.findings) == 1
    assert one.findings[0].fingerprint == two.findings[0].fingerprint


def test_http_security_each_exchange_is_evaluated() -> None:
    tests = (
        _attempt(
            ("GET", "/items", 200, ("x-frame-options",)),
            ("GET", "/items", 200, ()),
            ("GET", "/items", 200, ("x-frame-options",)),
        ),
    )

    run = _run((FRAME,), tests=tests)

    assert run.status == "FAILED"
    assert _rules(run) == ["HTTP-SEC-001"]


def test_http_security_many_violating_exchanges_are_one_finding() -> None:
    tests = tuple(_attempt(("GET", "/items", status, ()), node=f"t.py::{status}") for status in (404, 500, 502))

    run = _run(statuses=(STATUS,), tests=tests)

    assert _rules(run) == ["HTTP-SEC-002"]
    assert all(str(status) in run.findings[0].message for status in (404, 500, 502))


def test_http_security_failed_exchange_precedes_unknown() -> None:
    run = _run(
        (FRAME,),
        (StatusExpectation("GET", "/never", (200,)),),
        (
            _attempt(
                ("GET", "/items", 200, ()),
            )
        ),
    )

    assert run.status == "FAILED"
    assert run.reason is not None
    assert "no matching exchange" in run.reason
    assert _rules(run) == ["HTTP-SEC-001"]


def test_http_security_incomplete_configured_observation_is_unknown() -> None:
    facts = _attempt(("GET", "/items", 200, ("x-frame-options",)))
    facts.http.incomplete.add(("GET", "/items"))

    run = _run((FRAME,), tests=(facts,))

    assert run.status == "UNKNOWN"
    assert run.reason is not None
    assert "evidence incomplete" in run.reason


def test_http_security_retained_violation_still_fails_when_evidence_is_incomplete() -> None:
    facts = _attempt(("GET", "/items", 200, ()))
    facts.http.incomplete.add(("GET", "/items"))

    run = _run((FRAME,), tests=(facts,))

    assert run.status == "FAILED"
    assert run.reason is not None
    assert "evidence incomplete" in run.reason


def test_http_security_route_states_distinguish_not_found_and_unobservable() -> None:
    facts = TestFacts(TestKey(NODE, "gw0", 1))

    facts.http.record("GET", "not_found", "", 404, ())
    facts.http.record("GET", "unobservable", "", 200, ())

    assert facts.http.not_found == {"GET": 1}
    assert facts.http.unobservable == {"GET": 1}
    assert facts.http.exchanges == {}


def test_http_security_not_found_alone_does_not_hide_evidence() -> None:
    facts = _attempt(("GET", "/items", 200, ("x-frame-options",)))
    facts.http.record("GET", "not_found", "", 404, ())

    run = _run((FRAME,), tests=(facts,))

    assert run.status == "PASSED"
    assert run.evidence["exchanges"] == 1


def test_http_security_unobservable_route_never_matches_expectation() -> None:
    facts = TestFacts(TestKey(NODE, "gw0", 1))
    facts.http.record("GET", "unobservable", "/items", 200, ("x-frame-options",))

    run = _run((FRAME,), tests=(facts,))

    assert run.status == "UNKNOWN"
    assert run.reason is not None
    assert "evidence incomplete" in run.reason


def test_http_security_unobservable_route_of_another_method_is_not_a_gap() -> None:
    facts = _attempt(("GET", "/items", 200, ("x-frame-options",)))
    facts.http.record("POST", "unobservable", "", 200, ())

    run = _run((FRAME,), tests=(facts,))

    assert run.status == "PASSED"
    assert run.evidence["exchanges"] == 1


def test_http_security_selection_run_outcomes_follow_table() -> None:
    seen = _attempt(("GET", "/items", 200, ("x-frame-options",)))
    capped = _attempt(("GET", "/items", 200, ("x-frame-options",)))
    capped.http.incomplete.add(("GET", "/items"))

    complete = _run((FRAME,), tests=(_attempt(),))
    selection = _run((FRAME,), tests=(_attempt(),), partial_run=True)
    dropped = _run((FRAME,), tests=(capped,), partial_run=True)
    missing = _run((FRAME,), tests=(seen,), missing_workers=("gw1",))

    statuses = (complete.status, selection.status, dropped.status, missing.status)
    assert statuses == ("UNKNOWN",) * 4
    assert complete.reason is not None
    assert "no matching exchange" in complete.reason
    assert selection.reason is not None
    assert "selection run" in selection.reason
    assert dropped.reason is not None
    assert "evidence incomplete" in dropped.reason
    assert missing.reason is not None
    assert "missing worker" in missing.reason


def test_http_security_selection_clean_observation_passes() -> None:
    run = _run((FRAME,), tests=(_attempt(("GET", "/items", 200, ("x-frame-options",))),), partial_run=True)

    assert run.status == "PASSED"
    assert run.evidence["exchanges"] == 1


def test_http_security_selection_violation_fails() -> None:
    run = _run((FRAME,), tests=(_attempt(("GET", "/items", 200, ())),), partial_run=True)

    assert run.status == "FAILED"


def test_http_security_status_finding_identity_ignores_observed_status() -> None:
    first = _run(statuses=(STATUS,), tests=(_attempt(("GET", "/items", 500, ())),))
    second = _run(statuses=(STATUS,), tests=(_attempt(("GET", "/items", 404, ())),))

    assert len(first.findings) == len(second.findings) == 1
    assert first.findings[0].fingerprint == second.findings[0].fingerprint
    assert first.findings[0].message != second.findings[0].message


def test_http_security_header_finding_identity_names_header() -> None:
    run = _run(
        (FRAME, SNIFF),
        tests=(
            _attempt(
                ("GET", "/items", 200, ()),
            )
        ),
    )

    identities = sorted(str(finding.identity) for finding in run.findings)

    assert identities == ["GET /items x-content-type-options", "GET /items x-frame-options"]


def test_http_security_only_the_deciding_attempt_counts() -> None:
    bad = _attempt(("GET", "/items", 200, ()), attempt=1)
    good = _attempt(("GET", "/items", 200, ("x-frame-options",)), attempt=2)
    later_bad = _attempt(("GET", "/items", 200, ()), attempt=3)

    assert _run((FRAME,), tests=(bad, good)).status == "PASSED"
    assert _run((FRAME,), tests=(good, bad)).status == "PASSED"
    assert _run((FRAME,), tests=(bad, good, later_bad)).status == "FAILED"


def test_http_security_unassociated_exchange_never_satisfies_an_expectation() -> None:
    loose = HttpFacts()
    loose.record("GET", "matched", "/items", 200, ("x-frame-options",))

    run = _run((FRAME,), tests=(_attempt(),), unassociated=(loose,))

    assert run.status == "UNKNOWN"
    assert run.reason is not None
    assert "evidence incomplete" in run.reason


def test_http_security_attempt_key_is_not_derived_from_node_id() -> None:
    sink = TestSessionSink("gw0")
    sink.configure_http((FRAME,), ())
    sink.begin_test(NODE)
    sink.on_http("GET", "matched", "/items", 200, [])

    payload = sink.facts.tests[0].to_json().get("http")
    text = json.dumps(payload)

    assert payload
    assert NODE not in text
    assert hashlib.sha256(NODE.encode()).hexdigest()[:8] not in text
    assert "test_list" not in text


def test_http_security_sink_drops_exchanges_of_unconfigured_routes() -> None:
    sink = TestSessionSink("gw0")
    sink.configure_http((FRAME,), ())
    sink.begin_test(NODE)

    sink.on_http("GET", "matched", "/other", 200, [])
    sink.on_http("GET", "matched", "/items", 200, [])

    assert sorted(key[1] for key in sink.facts.tests[0].http.exchanges) == ["/items"]


def test_http_security_sink_keeps_a_request_outside_a_window_apart() -> None:
    sink = TestSessionSink("gw0")
    sink.configure_http((FRAME,), ())
    sink.begin_test(NODE)
    sink.end_test()

    sink.on_http("GET", "matched", "/items", 200, [])

    assert sink.facts.tests[0].http.exchanges == {}
    assert len(sink.facts.http_unassociated.exchanges) == 1


def test_http_security_facts_survive_a_json_round_trip() -> None:
    sink = TestSessionSink("gw0")
    sink.configure_http((FRAME,), (STATUS,))
    sink.begin_test(NODE)
    sink.on_http("GET", "matched", "/items", 200, ["x-frame-options"])
    sink.on_http("GET", "unobservable", "", 200, [])

    restored = TestFacts.from_json(json.loads(json.dumps(sink.facts.tests[0].to_json())))

    assert restored.http.exchanges
    assert restored.http == sink.facts.tests[0].http
