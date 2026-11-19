"""Runtime Insights I2: the agent view of the report and of one observation (BootUI ``RuntimeInsightsAgentView``)."""

from __future__ import annotations

from typing import Any

import pytest

from sharpit.engine.collectors.insights.agent_view import Steps, UnknownObservation, agent_detail, agent_list
from sharpit.engine.tools import COMMANDS

STEPS = Steps(COMMANDS)
EVENT_LOOP = "Spring MVC serves requests on worker threads."


def _observation(i: int, kind: str, subject: str, sentence: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": f"{kind}:{i}", "kind": kind, "subject": subject, "status": "OBSERVED", "sentence": sentence,
        "eligible": 10, "affected": 3, "minimumTier": "REQUEST_ID", "whatToCheck": ["Check the call site.", "Then."],
        "exemplarRequestIds": [f"r-{i}", "r-x"], "evidenceRows": 1, "limitations": [], "listed": True,
        "unlistedReason": None, **extra,
    }  # fmt: skip


def _report(
    observations: list[dict[str, Any]], *, requests: int = 12, evicted: int = 0, **extra: Any
) -> dict[str, Any]:
    window = {
        "runId": "run-1", "firstEventAt": 1, "lastEventAt": 2, "retainedEvents": 100, "requests": requests,
        "evictedEvents": evicted, "droppedEvents": 0,
    }  # fmt: skip
    return {
        "available": True, "unavailableReason": None, "window": window, "coverage": [], "checks": [],
        "observations": observations, "limitations": [], "notExercised": [], "notExercisedOmitted": 0, **extra,
    }  # fmt: skip


def _busy() -> dict[str, Any]:
    rows = [_observation(i, "repeated-selects", f"GET /api/orders/{i}", "repeated a SELECT") for i in range(8)]
    rows += [
        _observation(8, "route-time-breakdown", "GET /api/slow", "warm median 120 ms"),
        _observation(9, "anonymous-data-reach", "POST /api/debug", "an anonymous write"),
        _observation(10, "exception-hotspots", "GET /api/boom", "recorded `X`, not observed in the previous run"),
    ]
    checks = [
        {"kind": "repeated-selects", "title": "Repeated SELECTs", "status": "EVALUATED", "eligibleRequests": 9,
         "findings": 8, "reason": None},
        {"kind": "event-loop-blocking", "title": "Blocking on event loops", "status": "NOT_APPLICABLE",
         "eligibleRequests": 0, "findings": 0, "reason": EVENT_LOOP},
    ]  # fmt: skip
    return _report(rows, checks=checks, notExercised=[f"GET /api/unused/{i}" for i in range(10)], notExercisedOmitted=5)


# ported: RuntimeInsightsAgentViewTests.theDefaultListPutsCoverageAndUnrunChecksFirstAndNeverMentionsValidation
def test_the_default_list_puts_coverage_and_unrun_checks_first_and_never_mentions_validation() -> None:
    listed = agent_list(_busy(), None, None, STEPS)
    assert listed["available"] is True
    assert listed["checksNotRun"] == [f"event-loop-blocking: NOT_APPLICABLE, {EVENT_LOOP}"]
    kinds = [o["kind"] for o in listed["observations"]]
    assert "route-time-breakdown" in kinds
    assert len(kinds) == 8
    assert listed["omitted"] == 3
    assert listed["observations"][0]["exemplarRequestId"] == "r-0"
    assert listed["observations"][0]["verify"] == "Check the call site."
    assert not [t for t in listed["limitations"] if "validat" in t.lower()]
    assert listed["requests"] == 12
    assert len(listed["notExercised"]) == 8
    assert listed["notExercised"][0] == "GET /api/unused/0"
    assert listed["notExercisedOmitted"] == 2 + 5


# ported: RuntimeInsightsAgentViewTests.aProlificKindCannotHideTheOthersAndWhatIsLeftOutSaysHowToListIt
def test_a_prolific_kind_cannot_hide_the_others_and_what_is_left_out_says_how_to_list_it() -> None:
    listed = agent_list(_busy(), None, None, STEPS)
    kinds = [o["kind"] for o in listed["observations"]]
    assert "anonymous-data-reach" in kinds
    assert "exception-hotspots" in kinds
    assert kinds.count("repeated-selects") == 5
    assert "Left out by limit: repeated-selects 3." in listed["limitations"]
    assert "sharpit insights list --query repeated-selects" in [step["command"] for step in listed["next"]]
    asked = agent_list(_busy(), "Repeated-Selects", 20, STEPS)
    assert {o["kind"] for o in asked["observations"]} == {"repeated-selects"}
    assert len(asked["observations"]) == 8


# ported: RuntimeInsightsAgentViewTests.aRunWithoutRequestsSaysItsEmptyListMeansNotExercised
def test_a_run_without_requests_says_its_empty_list_means_not_exercised() -> None:
    listed = agent_list(_report([], requests=0), None, None, STEPS)
    assert listed["requests"] == 0
    assert listed["observations"] == []
    assert "not exercised, not healthy" in listed["limitations"][0]


def test_the_list_and_detail_carry_every_key_of_bootui_agent_dtos() -> None:
    listed = agent_list(_busy(), None, None, STEPS)
    assert list(listed) == [
        "available", "unavailableReason", "query", "requests", "coverage", "checksNotRun", "observations", "omitted",
        "notExercised", "notExercisedOmitted", "limitations", "next", "insufficient", "partial",
    ]  # fmt: skip
    assert list(listed["observations"][0]) == [
        "id", "kind", "status", "subject", "sentence", "eligible", "affected", "tier", "exemplarRequestId", "verify",
        "listed",
    ]  # fmt: skip
    assert list(listed["next"][0]) == ["command", "tool", "arguments", "why"]


# derived: RuntimeInsightsAgentViewTests (incomplete evidence counters cover all matching rows past limit)
def test_agent_list_incomplete_evidence_counters_cover_all_matching_rows_past_limit() -> None:
    obs = [
        _observation(0, "repeated-selects", "GET /api/orders", "sentence 0", status="INSUFFICIENT"),
        _observation(1, "repeated-selects", "GET /api/orders", "sentence 1", status="PARTIAL"),
        _observation(2, "repeated-selects", "GET /api/orders", "sentence 2", status="OBSERVED"),
        _observation(3, "repeated-selects", "GET /api/other", "sentence 3", status="INSUFFICIENT"),
    ]
    report = _report(obs)

    # limit=1 cuts matching rows from 3 to 1, but counters must count all 3 matching rows
    thin = agent_list(report, "GET /api/orders", 1, STEPS)
    assert thin.get("insufficient") == 1
    assert thin.get("partial") == 1
    assert thin.get("omitted") == 2
    assert len(thin["observations"]) == 1

    # query matching other route
    other = agent_list(report, "GET /api/other", 1, STEPS)
    assert other.get("insufficient") == 1
    assert other.get("partial") == 0
    assert other.get("omitted") == 0

    # default query matching all
    all_rows = agent_list(report, None, 2, STEPS)
    assert all_rows.get("insufficient") == 2
    assert all_rows.get("partial") == 1
    assert all_rows.get("omitted") == 2


# derived: RuntimeInsightsAgentViewTests.anUnavailableReportOrObservationSaysWhyInsteadOfReturningAnEmptySuccess
# (unavailable report emits zero counters)
def test_agent_list_unavailable_emits_zero_counters() -> None:
    off = _report([], available=False, unavailableReason="journal off", window=None)
    listed = agent_list(off, None, None, STEPS)
    assert listed["available"] is False
    assert listed.get("insufficient") == 0
    assert listed.get("partial") == 0


# ported: RuntimeInsightsAgentViewTests.aRouteQueryListsThatRoutesRowsFirstAndFollowsOneOfThemUp
def test_a_route_query_lists_that_routes_rows_first_and_follows_one_of_them_up() -> None:
    observations = [
        _observation(1, "repeated-selects", "GET /api/orders/{id}", "repeated a SELECT"),
        _observation(2, "route-time-breakdown", "GET /api/orders/joined", "warm median 120 ms"),
        _observation(3, "repeated-selects", "GET /api/orders", "repeated a SELECT 20 times"),
        _observation(4, "exception-hotspots", "POST /api/orders", "recorded `X`"),
    ]
    report = _report(observations)

    listed = agent_list(report, "get /api/orders", 20, STEPS)
    assert [o["subject"] for o in listed["observations"]] == [
        "GET /api/orders",
        "GET /api/orders/{id}",
        "GET /api/orders/joined",
    ]
    insight_steps = [s for s in listed["next"] if s["tool"] == "get_runtime_insight"]
    assert len(insight_steps) == 1
    assert insight_steps[0]["arguments"] == {"id": "repeated-selects:3"}
    profile_steps = [s for s in listed["next"] if s["tool"] == "get_request_profile"]
    assert len(profile_steps) == 1
    assert profile_steps[0]["arguments"] == {"id": "r-3"}

    insufficient_obs = list(observations)
    exact = dict(observations[2])
    exact["status"] = "INSUFFICIENT"
    insufficient_obs[2] = exact
    thin = _report(insufficient_obs)
    thin_list = agent_list(thin, "GET /api/orders", 1, STEPS)
    assert thin_list["insufficient"] == 1
    assert thin_list["partial"] == 0
    assert thin_list["omitted"] == 2
    thin_insight = [s for s in thin_list["next"] if s["tool"] == "get_runtime_insight"]
    assert len(thin_insight) == 1
    assert thin_insight[0]["arguments"] == {"id": "repeated-selects:3"}

    partial_obs = list(insufficient_obs)
    exact_partial = dict(exact)
    exact_partial["status"] = "PARTIAL"
    partial_obs[2] = exact_partial
    partial_report = _report(partial_obs)
    partial_list = agent_list(partial_report, None, 1, STEPS)
    assert partial_list["partial"] == 1
    assert partial_list["insufficient"] == 0

    orders_only = agent_list(report, "GET /api/orders", 1, STEPS)["observations"]
    assert [o["subject"] for o in orders_only] == ["GET /api/orders"]


def test_an_unlisted_row_is_left_out_of_the_default_list_and_the_list_says_how_to_ask_for_it() -> None:
    hidden = _observation(1, "gc-inflated-latency", "GET /x", "slow", listed=False, unlistedReason="In Memory.")
    listed = agent_list(_report([hidden]), None, None, STEPS)
    assert listed["observations"] == []
    assert any(t.startswith("Not listed by default: gc-inflated-latency 1.") for t in listed["limitations"])
    assert [o["id"] for o in agent_list(_report([hidden]), "all", None, STEPS)["observations"]] == [hidden["id"]]


def test_unavailable_report_names_the_journal_setting() -> None:
    off = _report([], available=False, unavailableReason="journal off", window=None)
    listed = agent_list(off, None, None, STEPS)
    assert (listed["available"], listed["unavailableReason"]) == (False, "journal off")
    assert [step["command"] for step in listed["next"]] == ["sharpit config --query SHARPIT_RUNTIME_JOURNAL"]


def test_next_steps_name_only_tools_the_application_advertises() -> None:
    listed = agent_list(_busy(), None, None, Steps(COMMANDS, lambda tool: tool != "get_runtime_insights"))
    assert "get_runtime_insights" not in [step["tool"] for step in listed["next"]]


def test_detail_of_an_unknown_id_is_a_tool_error_naming_the_list_call() -> None:
    reason = "No observation x:1 in this run's retained events: it may have been evicted or cleared."
    unknown = {"available": False, "unavailableReason": reason, "observation": None, "columns": [], "rows": []}
    with pytest.raises(UnknownObservation) as raised:
        agent_detail(unknown, STEPS)
    assert str(raised.value).endswith("List the current observation ids with get_runtime_insights.")


def test_detail_of_an_unlisted_observation_says_why_first_among_its_limitations() -> None:
    observation = _observation(1, "gc-inflated-latency", "GET /x", "slow", listed=False, unlistedReason="In Memory.")
    observation["limitations"] = ["Own limit."]
    rows = [{"cells": ["1"]}]
    detail = {"available": True, "unavailableReason": None, "observation": observation, "columns": ["a"], "rows": rows}
    detail["truncated"] = 4
    shown = agent_detail(detail, STEPS)
    assert list(shown) == [
        "available", "unavailableReason", "observation", "whatToCheck", "limitations", "columns", "rows", "truncated",
        "next",
    ]  # fmt: skip
    assert shown["limitations"] == ["Not listed by default: In Memory.", "Own limit."]
    assert shown["whatToCheck"] == ["Check the call site.", "Then."]
    assert shown["truncated"] == 4
    assert shown["observation"]["exemplarRequestId"] == "r-1"


def test_an_empty_subject_omits_the_query_argument_of_the_next_steps() -> None:
    row = _observation(1, "anonymous-data-reach", "", "")
    steps = agent_list(_report([row]), None, None, STEPS)["next"]
    assert [s for s in steps if s["arguments"].get("query") == ""] == []
