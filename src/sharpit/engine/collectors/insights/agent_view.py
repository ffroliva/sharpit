"""Runtime Insights for agents (BootUI ``RuntimeInsightsAgentView.java``): the report and one observation, compacted.

Short, stable facts an agent can diff and refuse to act on. Every answer names the calls to make next, restricted to
the tools this application advertises. Callers pass the report as ``InsightsService`` built it: already masked.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sharpit.engine.collectors.insights.service import UNKNOWN_PREFIX, UNKNOWN_SUFFIX
from sharpit.engine.collectors.insights.snapshot import LEFT_OUT_BEFORE_LOSS
from sharpit.engine.collectors.insights.text import HIGH_REPEAT_KEEP, MIN_REQUESTS, UNDER_DEFAULT_FLOOR

Row = dict[str, Any]
Matcher = Callable[[Row], bool]

ALL = "all"  # the query that lists every observation, the default list's left-outs included
DEFAULT_LIMIT, MAX_LIMIT, MAX_NOT_EXERCISED, MAX_STEPS = 8, 50, 8, 3  # RuntimeInsightsAgentReportDto / AgentView
LATENCY_KINDS = frozenset({"route-time-breakdown", "gc-inflated-latency"})  # only describe latency
SECURITY_KINDS = frozenset({"anonymous-data-reach", "anonymous-success-on-restricted-route"})
NEW_MARK = "not observed in the previous run"
JOURNAL_SETTINGS = "SHARPIT_RUNTIME_JOURNAL"
NON_HTTP_PREFIX = "Retained non-HTTP executions, which requests does not count:"
_JUDGED = (
    re.compile(  # JudgedWithoutFinding.SENTENCES: judged and not reported, as opposed to what a check could not see
        r"(?:Examined \d+ collections that reclaimed old-generation space; their retained occupancy did not meet this "
        r"check's growth threshold\."
        r"|\d+ transactional methods? kept a transaction open only across calls under [\d.]+ ms, so "
        r"(?:it is|they are) not reported\."
        r"|\d+ statements? that SQL after the handler returned reports on the same route, from the same call site, "
        r"(?:is|are) left to it, which names the cause\.)"
    )
)
_BARE = re.compile(r"<[A-Za-z]+>|[A-Za-z0-9._/:-]+")


class UnknownObservation(Exception):  # noqa: N818 - BootUI's tool error (404) for an id this run does not have
    pass


@dataclass(frozen=True)
class Steps:
    """The calls a next step may name: ``commands`` maps a tool to its CLI path; ``advertised`` says which are on."""

    commands: Mapping[str, str]
    advertised: Callable[[str], bool] | None = None


def _quote(value: str) -> str:
    return value if _BARE.fullmatch(value) else "'" + value.replace("'", "'\\''") + "'"


def _command(path: str, arguments: Mapping[str, object]) -> str:
    """``CliCommandPaths.command``: the id positional first, then ``--query`` and ``--limit``, quoted for a shell."""
    line = f"sharpit {path}"
    given = arguments.get("id")
    dashed = given is not None and str(given).startswith("-")
    if given is not None and not dashed:
        line += f" {_quote(str(given))}"
    for name, flag in (("query", "--query"), ("limit", "--limit")):
        if name in arguments:
            line += f" {flag} {_quote(str(arguments[name]))}"
    return f"{line} -- {_quote(str(given))}" if dashed else line


class _Next:
    """``NextSteps``: at most ``maximum`` distinct calls, each only if the application advertises the tool."""

    def __init__(self, steps: Steps, maximum: int = MAX_STEPS) -> None:
        self.steps = steps
        self.maximum = max(0, min(MAX_STEPS, maximum))
        self.rows: list[Row] = []

    def add(self, tool: str, why: str, arguments: Mapping[str, object] | None = None) -> _Next:
        path = self.steps.commands.get(tool)
        if (
            len(self.rows) >= self.maximum
            or path is None
            or (self.steps.advertised and not self.steps.advertised(tool))
        ):
            return self
        given = dict(arguments or {})
        command = _command(path, given)
        if all(row["command"] != command for row in self.rows):
            self.rows.append({"command": command, "tool": tool, "arguments": given, "why": why})
        return self

    def ask(self, tool: str, argument: str, value: object, why: str) -> _Next:
        return self if value is None or value == "" else self.add(tool, why, {argument: value})

    def then(self, others: _Next) -> list[Row]:
        merged = list(self.rows)
        for row in others.rows:
            if len(merged) < MAX_STEPS and all(row["command"] != named["command"] for named in merged):
                merged.append(row)
        return merged


def _compact(observation: Row) -> Row:
    checks, exemplars = observation["whatToCheck"], observation["exemplarRequestIds"]
    return {
        "id": observation["id"], "kind": observation["kind"], "status": observation["status"],
        "subject": observation["subject"], "sentence": observation["sentence"], "eligible": observation["eligible"],
        "affected": observation["affected"], "tier": observation["minimumTier"],
        "exemplarRequestId": exemplars[0] if exemplars else None, "verify": checks[0] if checks else None,
        "listed": observation["listed"],
    }  # fmt: skip


def _under_floor(observation: Row) -> bool:
    return observation["kind"] == "repeated-selects" and UNDER_DEFAULT_FLOOR in observation["limitations"]


def _has(text: object, needle: str) -> bool:
    return isinstance(text, str) and needle in text.lower()


def _matches(observation: Row, query: str) -> bool:
    kind, needle = observation["kind"], query.lower()
    if needle == "":
        return bool(observation["listed"]) and not _under_floor(observation)
    if needle == ALL:
        return True
    if needle == "latency":
        return kind in LATENCY_KINDS
    if needle == "security":
        return kind in SECURITY_KINDS
    if needle in {"new", "diff"}:
        return NEW_MARK in str(observation["sentence"] or "")
    return kind.lower() == needle or _has(observation["subject"], needle) or _has(observation["sentence"], needle)


def _breadth_first(rows: Sequence[Row], limit: int, exact: Matcher) -> list[Row]:
    """Listed rows first, and every kind's most affected one before any kind's second, so no kind hides the others."""

    def leading(i: int) -> tuple[bool, bool]:
        return not exact(rows[i]), not rows[i]["listed"]

    order = list(range(len(rows)))
    if len(rows) > limit:
        seen: Counter[tuple[object, ...]] = Counter()
        rank: list[int] = []
        for row in rows:
            seen[key := (row["kind"], row["listed"], exact(row))] += 1
            rank.append(seen[key])
        order.sort(key=lambda i: (*leading(i), rows[i]["status"] == "INSUFFICIENT", rank[i], i))
        order = order[:limit]
    order.sort(key=lambda i: (*leading(i), i))
    return [rows[i] for i in order]


def _counts(observations: Sequence[Row]) -> str:
    return ", ".join(f"{kind} {count}" for kind, count in Counter(o["kind"] for o in observations).items())


def _left_out(matching: Sequence[Row], listed: Sequence[Row]) -> str | None:
    if len(matching) == len(listed):
        return None
    omitted = Counter(o["kind"] for o in matching) - Counter(o["kind"] for o in listed)
    return f"Left out by limit: {', '.join(f'{kind} {count}' for kind, count in omitted.items())}."


def _requests_zero(report: Row) -> str:
    observations, limitations = report["observations"], report["limitations"]
    window = report["window"]
    if any(o["exemplarRequestIds"] for o in observations):
        return (
            "requests counts completed HTTP exchanges only. Observations here can come from scheduled jobs, messages, "
            "or other non-HTTP executions, so requests 0 is not proof nothing ran."
        )
    if any(LEFT_OUT_BEFORE_LOSS in t for t in limitations):
        return (
            f"Requests that {LEFT_OUT_BEFORE_LOSS} (Clear recording, or the journal's bounds) are left out, so "
            "requests 0 is not proof the run was idle: call again once new requests have completed."
        )
    if window and window["evictedEvents"] > 0:
        return "The journal evicted older events, so requests 0 is not proof the run was idle."
    if any(t.startswith(NON_HTTP_PREFIX) for t in limitations):
        return (
            f'requests counts completed HTTP exchanges only. See the limitation that starts with "{NON_HTTP_PREFIX}".'
        )
    if not observations:
        return (
            "No HTTP request completed in this run's retained events, so request-level checks had nothing to judge: "
            "an empty list here means not exercised, not healthy. Run the application's tests or send it traffic, "
            "then call again."
        )
    return (
        "No HTTP request completed in this run's retained events, and no observation names a request or execution, "
        "so request-level checks had nothing to judge: not exercised, not healthy. Run the application's tests or "
        "send it traffic, then call again."
    )


def _floor_dropped(dropped: int) -> str:
    return (
        f"Left out {dropped} repeated-selects {'row' if dropped == 1 else 'rows'} under 50 ms of summed measured time, "
        f"seen in fewer than {MIN_REQUESTS} requests and fewer than {HIGH_REPEAT_KEEP} times in any one."
    )


def _unlisted(observations: Sequence[Row]) -> str | None:
    hidden = [o for o in observations if not o["listed"]]
    if not hidden:
        return None
    return (
        f"Not listed by default: {_counts(hidden)}. Pass the query all, a kind, or a route to list them; "
        "get_runtime_insight on one says why it is left out."
    )


def _checks_not_run(checks: Sequence[Row]) -> list[str]:
    rows: list[str] = []
    for check in checks:
        reason = check["reason"]
        if check["status"] != "EVALUATED":
            rows.append(f"{check['kind']}: {check['status']}" + (f", {reason}" if reason is not None else ""))
        elif reason is not None and (gaps := re.sub(r"\s{2,}", " ", _JUDGED.sub("", reason)).strip()):
            rows.append(f"{check['kind']}: EVALUATED, partly: {gaps}")
    return rows


def _route_path(subject: str | None) -> str | None:
    return None if subject is None else subject.partition(" ")[2] or subject


def _follow(next_steps: _Next, observation: Row, from_list: bool) -> None:
    """The one kind-specific source of its cause, then (in a list answer) its evidence and one request showing it."""
    kind, subject = observation["kind"], observation["subject"]
    exemplars = observation["exemplarRequestIds"]
    if kind in SECURITY_KINDS:
        next_steps.add("get_fastapi_security", f"the security rules that let anonymous requests reach {subject}")
        next_steps.ask("get_mappings", "query", _route_path(subject), f"the handler mapped to {subject}")
    elif kind in {"exception-hotspots", "errors-behind-2xx"}:
        next_steps.add("get_exceptions", "the exception group ids, for get_exception_detail")
    elif kind == "changed-code-not-executed":
        next_steps.ask("get_code_inventory", "query", "changed", "each changed method and whether it ran")
    elif kind == "route-time-breakdown":
        next_steps.ask("get_code_paths", "query", subject, f"the application methods {subject} spends its time in")
    if from_list:
        next_steps.ask(
            "get_runtime_insight",
            "id",
            observation["id"],
            f"the evidence rows behind this {kind} observation, call sites included",
        )
    next_steps.ask(
        "get_request_profile",
        "id",
        exemplars[0] if exemplars else None,
        "one request or execution that shows it, step by step",
    )


def _window_requests(report: Row) -> int:
    window: Row = report["window"] or {}
    return int(window.get("requests", 0))


def _asks(
    asked: str, maximum: int, matching: Sequence[Row], listed: Sequence[Row], report: Row, steps: Steps
) -> tuple[_Next, list[str]]:
    """The ways to ask for more, and the limitations that say why; they come first, so follow-ups never crowd them."""
    asks, limitations = _Next(steps), list[str]()
    if asked.lower() == "diff":
        asks.add(
            "get_runtime_run_comparison", "what changed since the previous run: statements, calls, routes, and edges",
            {"id": "previous"},
        )  # fmt: skip
    dropped = unlisted = None
    if not asked:
        dropped = sum(1 for o in report["observations"] if o["listed"] and _under_floor(o))
        unlisted = _unlisted(report["observations"])
        limitations += [_floor_dropped(dropped)] if dropped else []
        limitations += [unlisted] if unlisted else []
    if left := _left_out(matching, listed):
        limitations.append(left)
        first = next(o["kind"] for o in matching if o not in listed)
        if not asked:
            asks.ask("get_runtime_insights", "query", first, f"the {first} observations this limit left out")
        elif maximum < MAX_LIMIT:
            asks.add("get_runtime_insights", f"every match, up to {MAX_LIMIT}", {"query": asked, "limit": MAX_LIMIT})
    if dropped:
        asks.ask(
            "get_runtime_insights",
            "query",
            "repeated-selects",
            "the cheap repeated-selects rows the default list leaves out",
        )
    if unlisted:
        asks.ask("get_runtime_insights", "query", ALL, "every row, including those the default list leaves out")
    if not listed and not report["observations"] and not _window_requests(report):
        asks.add("get_runtime_insights", "again after running the application's tests or sending it traffic")
    return asks, limitations


def agent_list(report: Row, query: str | None, limit: int | None, steps: Steps) -> Row:
    """The report's observations matching ``query``, at most ``limit`` (``RuntimeInsightsAgentView.list``)."""
    asked = (query or "").strip()
    maximum = min(MAX_LIMIT, limit if limit and limit > 0 else DEFAULT_LIMIT)
    if not report["available"]:
        unavailable = _Next(steps).ask(
            "get_config", "query", JOURNAL_SETTINGS, "whether the runtime journal is enabled"
        )
        return _list(False, report["unavailableReason"], asked, 0, [], [], [], 0, [], 0, [], unavailable.rows)
    matching = [o for o in report["observations"] if _matches(o, asked)]

    def exact(row: Row) -> bool:  # a subject named exactly lists first, and its lead row is the one followed up
        return bool(asked) and row["subject"] is not None and row["subject"].lower() == asked.lower()

    listed = _breadth_first(matching, maximum, exact)
    requests = _window_requests(report)
    asks, notes = _asks(asked, maximum, matching, listed, report, steps)
    limitations = [*([_requests_zero(report)] if requests == 0 else []), *report["limitations"], *notes]
    leads = [o for o in listed if exact(o)] or listed
    lead = next((o for o in leads if o["status"] != "INSUFFICIENT"), leads[0] if leads else None)
    follow = _Next(steps, max(1, MAX_STEPS - len(asks.rows)))
    if lead is not None:
        _follow(follow, lead, True)
    shown = min(MAX_NOT_EXERCISED, len(report["notExercised"]))
    steps_out = asks.then(follow) if asked.lower() == "diff" else follow.then(asks)
    return _list(
        True, None, asked, requests, report["coverage"], _checks_not_run(report["checks"]),
        [_compact(o) for o in listed], len(matching) - len(listed), report["notExercised"][:shown],
        len(report["notExercised"]) - shown + report["notExercisedOmitted"], limitations, steps_out,
    )  # fmt: skip


def _list(
    available: bool, reason: object, query: str, requests: int, coverage: list[Row], not_run: list[str],
    observations: list[Row], omitted: int, not_exercised: list[str], not_exercised_omitted: int,
    limitations: list[str], next_steps: list[Row],
) -> Row:  # fmt: skip
    return {
        "available": available, "unavailableReason": reason, "query": query, "requests": requests,
        "coverage": coverage, "checksNotRun": not_run, "observations": observations, "omitted": omitted,
        "notExercised": not_exercised, "notExercisedOmitted": not_exercised_omitted, "limitations": limitations,
        "next": next_steps,
    }  # fmt: skip


def unknown_observation(detail: Row) -> bool:
    """Whether ``detail`` answers an id this run does not have, as opposed to Runtime Insights being unavailable."""
    reason = detail["unavailableReason"]
    return (
        not detail["available"]
        and detail["observation"] is None
        and isinstance(reason, str)
        and reason.startswith(UNKNOWN_PREFIX)
        and reason.endswith(UNKNOWN_SUFFIX)
    )


def agent_detail(detail: Row, steps: Steps) -> Row:
    """One observation with its evidence; an unknown id is a tool error (404) naming the call that lists the ids."""
    if unknown_observation(detail):
        raise UnknownObservation(
            f"{detail['unavailableReason']} List the current observation ids with get_runtime_insights."
        )
    next_steps, observation = _Next(steps), detail["observation"]
    if not detail["available"] or observation is None:
        next_steps.add("get_runtime_insights", "the current observation ids, since ids change as the run goes on")
        return _detail(False, detail["unavailableReason"], None, [], [], [], [], 0, next_steps.rows)
    _follow(next_steps, observation, False)
    why = observation["unlistedReason"]
    limitations = [
        *([f"Not listed by default: {why}"] if not observation["listed"] and why else []),
        *observation["limitations"],
    ]
    return _detail(
        True, None, _compact(observation), observation["whatToCheck"], limitations, detail["columns"], detail["rows"],
        detail["truncated"], next_steps.rows,
    )  # fmt: skip


def _detail(
    available: bool, reason: object, observation: Row | None, what_to_check: list[str], limitations: list[str],
    columns: list[str], rows: list[Row], truncated: object, next_steps: list[Row],
) -> Row:  # fmt: skip
    return {
        "available": available, "unavailableReason": reason, "observation": observation, "whatToCheck": what_to_check,
        "limitations": limitations, "columns": columns, "rows": rows, "truncated": truncated, "next": next_steps,
    }  # fmt: skip
