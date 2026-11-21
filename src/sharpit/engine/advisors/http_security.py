"""The HTTP security advisor: explicit response expectations over the exchanges a test run made (T1).

Framework-free. It evaluates only what the host configured (a response header that must be present, the statuses a
route may answer); it infers no policy from route metadata, and it never sees a value, a body or a raw path.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import replace
from typing import Any, NamedTuple, cast

from sharpit.engine.advisors.findings import AdvisorRun, Finding
from sharpit.engine.advisors.rules import Severity
from sharpit.engine.testsession.facts import HttpFacts, TestFacts
from sharpit.engine.testsession.outcome import deciding

MIN_STATUS, MAX_STATUS = 100, 599
_STARLETTE_PARAM = re.compile(r"\{(\w+)(?::[^}]*)?\}")  # {id} and {id:int}
_WERKZEUG_PARAM = re.compile(r"<(?:[^<>:]+:)?(\w+)>")  # <id>, <int:id> and <int(min=1):id>


def normalize_route(template: str) -> str:
    """One route syntax for every adapter: a parameter is ``{name}``, whatever its framework calls it."""
    return _WERKZEUG_PARAM.sub(r"{\1}", _STARLETTE_PARAM.sub(r"{\1}", template))


class HeaderExpectation(NamedTuple):
    method: str
    route: str
    header: str  # lower-cased: header names compare case-insensitively


class StatusExpectation(NamedTuple):
    method: str
    route: str
    statuses: tuple[int, ...]  # sorted; any listed status satisfies the expectation


def _split(line: str, option: str, shape: str) -> tuple[str, str, str]:
    """``METHOD ROUTE=VALUE``: split on the first space and the last ``=``; a route may contain ``=`` or ``,``."""
    method, _, rest = line.strip().partition(" ")
    route, _, value = rest.rpartition("=")
    method, route, value = method.strip().upper(), route.strip(), value.strip()
    if not (method and route and value):
        raise ValueError(f"{option} {line!r}: expected {shape}")
    return method, normalize_route(route), value  # the observers' template form, so a Flask-style route matches


def parse_header_expectations(lines: Iterable[str], option: str) -> tuple[HeaderExpectation, ...]:
    found = (_split(line, option, "METHOD ROUTE=HEADER") for line in lines if line.strip())
    return tuple(dict.fromkeys(HeaderExpectation(m, r, v.lower()) for m, r, v in found))


def _status(text: str, line: str, option: str) -> int:
    shape = "METHOD ROUTE=STATUS[,STATUS...]"
    if not text.isascii() or not text.isdigit() or not MIN_STATUS <= int(text) <= MAX_STATUS:
        raise ValueError(f"{option} {line!r}: expected {shape} with statuses from {MIN_STATUS} to {MAX_STATUS}")
    return int(text)


def parse_status_expectations(lines: Iterable[str], option: str) -> tuple[StatusExpectation, ...]:
    union: dict[tuple[str, str], set[int]] = {}
    for line in (line for line in lines if line.strip()):
        method, route, value = _split(line, option, "METHOD ROUTE=STATUS[,STATUS...]")
        union.setdefault((method, route), set()).update(
            _status(part.strip(), line, option) for part in value.split(",")
        )
    return tuple(StatusExpectation(m, r, tuple(sorted(s))) for (m, r), s in union.items())


ADVISOR = "http-security"
HEADER_RULE, STATUS_RULE = "HTTP-SEC-001", "HTTP-SEC-002"
RULE_IDS = (HEADER_RULE, STATUS_RULE)
NO_EXCHANGE = "no matching exchange"
SELECTION_RUN = "selection run"
EVIDENCE_INCOMPLETE = "evidence incomplete"
MISSING_WORKER = "missing worker"


def _gap(
    method: str, route: str, runs: Sequence[HttpFacts], loose: Sequence[HttpFacts], missing: Sequence[str]
) -> str | None:
    """Why the evidence for one route may be missing something, whatever it shows: never a pass."""
    if missing:
        return MISSING_WORKER
    if any(facts.overflow or (method, route) in facts.incomplete or method in facts.unobservable for facts in runs):
        return EVIDENCE_INCOMPLETE
    unattributed = any(
        facts.overflow or method in facts.unobservable or any(key[:2] == (method, route) for key in facts.exchanges)
        for facts in loose
    )
    return EVIDENCE_INCOMPLETE if unattributed else None


def _violations(runs: Sequence[HttpFacts], method: str, route: str) -> list[tuple[int, tuple[str, ...]]]:
    return [
        (status, present)
        for facts in runs
        for (m, r, status, present), _count in facts.exchanges.items()
        if (m, r) == (method, route)
    ]


def _finding(rule: str, severity: Severity, target: str, message: str, identity: str) -> Finding:
    return Finding(rule, ADVISOR, severity, target, message, identity=identity)


def evaluate(
    headers: Sequence[HeaderExpectation],
    statuses: Sequence[StatusExpectation],
    tests: Iterable[TestFacts],
    *,
    unassociated: Sequence[HttpFacts] = (),
    partial_run: bool = False,
    missing_workers: Sequence[str] = (),
    fail_on: str = "HIGH",
    baseline: Collection[str] | None = None,
) -> AdvisorRun | None:
    """Evaluate every configured expectation against each finished exchange of the deciding attempts.

    One violating exchange is one finding per policy key; an expectation without complete matching evidence is
    UNKNOWN (never PARTIAL), and a definite failure outranks it while keeping its reason.
    """
    if not (headers or statuses):
        return None
    runs = [attempt.http for attempt in deciding(tests)]
    findings: list[Finding] = []
    limitations: list[str] = []

    def judge(label: str, method: str, route: str, violated: bool) -> bool:
        seen = _violations(runs, method, route)
        gap = _gap(method, route, runs, unassociated, missing_workers)
        if gap or not (seen or violated):
            limitations.append(f"{label}: {gap or (SELECTION_RUN if partial_run else NO_EXCHANGE)}")
        return violated

    for expectation in headers:
        method, route, header = expectation
        missing = any(header not in present for _, present in _violations(runs, method, route))
        if judge(f"{method} {route} header {header}", method, route, missing):
            message = f"{method} {route} responded without configured header {header}"
            findings.append(_finding(HEADER_RULE, "HIGH", f"{method} {route}", message, f"{method} {route} {header}"))
    for expectation in statuses:
        method, route, allowed = expectation
        outside = sorted({s for s, _ in _violations(runs, method, route) if s not in allowed})
        if judge(f"{method} {route} status", method, route, bool(outside)):
            expected = ", ".join(map(str, allowed))
            message = f"{method} {route} responded with status {', '.join(map(str, outside))}; expected {expected}"
            findings.append(_finding(STATUS_RULE, "HIGH", f"{method} {route}", message, f"{method} {route}"))
    limitations = list(dict.fromkeys(limitations))
    evidence: dict[str, Any] = {
        "usable": not limitations,
        "coverageComplete": not limitations,
        "limitations": limitations,
        "expectations": len(headers) + len(statuses),
        "exchanges": sum(count for facts in runs for count in facts.exchanges.values()),
    }
    if baseline is not None:  # the existing baseline comparison: a finding already in it does not fail the gate
        findings = [replace(f, baseline_state="existing" if f.fingerprint in baseline else "new") for f in findings]
    return AdvisorRun.of(ADVISOR, findings, evidence, fail_on=cast("Severity", fail_on))
