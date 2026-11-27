"""Stable, explicit baseline file format for pytest gate findings."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from sharpit.engine.advisors.findings import Finding
from sharpit.engine.testsession import gates
from sharpit.engine.testsession.facts import TestFacts
from sharpit.engine.testsession.outcome import deciding
from sharpit.engine.testsession.report import clean_text

SCHEMA = "sharpit-baseline/1"
TEST_RUNTIME_PREFIX = "test-runtime:"


def owner_of(node_id: str | None) -> str | None:
    """A 16-hex digest of the owning test's node id; the baseline never stores the id itself."""
    if node_id is None:
        return None
    return hashlib.sha256(node_id.encode("utf-8", "surrogatepass")).hexdigest()[:16]


@dataclass(frozen=True)
class Entry:
    fingerprint: str
    rule_id: str
    target: str
    message: str
    observed: int | None
    owner: str | None = None


@dataclass(frozen=True)
class Baseline:
    entries: dict[str, Entry]
    raw: bytes


@dataclass(frozen=True)
class Comparison:
    findings: tuple[Finding, ...]
    fixed: tuple[Entry, ...] | None
    fixed_reason: str | None
    carried: tuple[Entry, ...] = ()
    inconclusive: tuple[tuple[Entry, str], ...] = ()


def _row_owner(row: dict[str, Any], fingerprint: str) -> str | None:
    owner = row.get("owner")
    if owner is not None and not isinstance(owner, str):
        raise ValueError("baseline owner must be a string or null")
    return owner if fingerprint.startswith(TEST_RUNTIME_PREFIX) else None


def read(path: Path) -> Baseline:
    """Read and validate one stable baseline document."""
    raw = path.read_bytes()
    try:
        payload: Any = json.loads(raw)
    except (ValueError, RecursionError) as exc:  # JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise ValueError("baseline is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("baseline must be an object")
    document = cast(dict[str, Any], payload)
    if document.get("schema") != SCHEMA:
        raise ValueError(f"baseline schema must be {SCHEMA}")
    raw_rows = document.get("findings")
    if not isinstance(raw_rows, list):
        raise ValueError("baseline findings must be a list")
    rows = cast(list[Any], raw_rows)
    entries: dict[str, Entry] = {}
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            raise ValueError("baseline finding has invalid fields")
        row = cast(dict[str, Any], raw_row)
        if not all(isinstance(row.get(key), str) for key in ("fingerprint", "ruleId", "target", "message")):
            raise ValueError("baseline finding has invalid fields")
        observed = row.get("observed")
        if observed is not None and (not isinstance(observed, int) or isinstance(observed, bool)):
            raise ValueError("baseline observed must be an integer or null")
        fingerprint = row["fingerprint"]
        if fingerprint in entries:
            raise ValueError(f"duplicate fingerprint in baseline: {fingerprint}")
        owner = _row_owner(row, fingerprint)
        entries[fingerprint] = Entry(fingerprint, row["ruleId"], row["target"], row["message"], observed, owner)
    return Baseline(entries, raw)


_UNRELAXED = gates.Budget(0, False, 0)
_UNPROVED = {
    "no_owner": "recorded without its owner",
    "incomplete": "the run's evidence is incomplete",
    "not_run": "its test did not run",
    "not_completed": "its test did not complete",
    "new_of_rule": "its test has a new finding of the same rule",
    "still_shown": "its test still shows it outside the gate",
}


def _shown(facts: TestFacts) -> list[Finding]:
    """What every phase of one attempt shows under an unrelaxed budget, so no budget or marker hides a finding.

    Every phase counts for every rule, max-queries included, although that gate evaluates only the call phase: queries
    moved into a fixture are not proof of a fix.
    """
    shown: list[Finding] = []
    for phase in facts.phases.values():
        shown.extend(gates.evaluate_test(replace(facts, phases={"call": phase}), _UNRELAXED, 2, ()))
    return shown


def _gate_off(rule_id: str, budget: gates.Budget | None) -> bool:
    if budget is None:  # no budget recorded: assume the gate could have hidden it
        return True
    return {
        gates.MAX_QUERIES: budget.max_queries is None,
        gates.N_PLUS_ONE: budget.allow_n_plus_one,
        gates.SWALLOWED: budget.allow_swallowed,
        gates.UNBOUNDED_READ: budget.allow_unbounded_read,
    }.get(rule_id, False)


def _still_shown(entry: Entry, facts: TestFacts) -> bool:
    gate_off = _gate_off(entry.rule_id, facts.budget)
    return any(
        f.fingerprint == entry.fingerprint
        and (gate_off or f.observed is None or entry.observed is None or f.observed >= entry.observed)
        for f in _shown(facts)
    )


def unproved(
    entry: Entry,
    by_owner: Mapping[str | None, Sequence[TestFacts]],
    incomplete: Collection[str],
    new_of_rule: Collection[tuple[str | None, str]],
) -> str | None:
    """Why an unseen entry is not proven fixed, or None when it is (advisor entries keep the current rule).

    ``by_owner`` holds the run's tests by owner digest and ``new_of_rule`` the (owner, rule) pairs of its new findings.
    """
    if not entry.fingerprint.startswith(TEST_RUNTIME_PREFIX):
        return None
    if entry.owner is None:
        return _UNPROVED["no_owner"]
    if entry.rule_id in incomplete:
        return _UNPROVED["incomplete"]
    mine = by_owner.get(entry.owner, ())
    if not mine:
        return _UNPROVED["not_run"]
    if any(t.completed is not True for t in deciding(mine)):
        return _UNPROVED["not_completed"]
    if (entry.owner, entry.rule_id) in new_of_rule:
        return _UNPROVED["new_of_rule"]
    if any(_still_shown(entry, t) for t in mine):
        return _UNPROVED["still_shown"]
    return None


def compare(
    findings: Sequence[Finding],
    baseline: Baseline | None,
    *,
    partial: bool,
    ran: Collection[str] | None = None,
    in_part: Collection[str] = (),
    tests: Sequence[TestFacts],
    incomplete: Collection[str],
) -> Comparison:
    """Annotate current findings and report baseline entries no longer seen."""
    if baseline is None:
        return Comparison(tuple(findings), None, None)
    entries = baseline.entries
    seen: set[str] = set()
    compared: list[Finding] = []
    for finding in findings:
        if finding.advisor.lower() in {"vulnerability", "vulns"} or finding.rule_id.startswith("VULN-"):
            compared.append(finding)
            continue
        entry = entries.get(finding.fingerprint)
        seen.add(finding.fingerprint)
        existing = entry is not None and not (
            finding.observed is not None and entry.observed is not None and finding.observed > entry.observed
        )
        compared.append(replace(finding, baseline_state="existing" if existing else "new"))
    unseen = [entry for fingerprint, entry in entries.items() if fingerprint not in seen]
    carried = tuple(e for e in unseen if ran is not None and e.fingerprint.split(":", 1)[0] not in ran)
    if partial:
        return Comparison(tuple(compared), None, "partial run", carried)
    by_owner: dict[str | None, list[TestFacts]] = {}
    for test in tests:  # digest each node once: per entry it was quadratic on a large suite
        by_owner.setdefault(owner_of(test.key.node_id), []).append(test)
    new_of_rule = {(owner_of(f.test_node_id), f.rule_id) for f in compared if f.baseline_state == "new"}
    reasons = {e.fingerprint: reason for e in unseen if (reason := unproved(e, by_owner, incomplete, new_of_rule))}
    inconclusive = tuple(
        (e, reasons[e.fingerprint]) for e in sorted(unseen, key=lambda e: e.fingerprint) if e.fingerprint in reasons
    )
    kept = tuple(e for e, _ in inconclusive)
    if carried:  # an advisor that did not read the whole app cannot say an entry is gone: neither fixed nor dropped
        names = {e.fingerprint.split(":", 1)[0] for e in carried}
        why = [
            f"{text}: {', '.join(sorted(group))}"
            for text, group in (
                ("advisor did not run", names - set(in_part)),
                ("advisor assessed part of the app", names & set(in_part)),
            )
            if group
        ]
        return Comparison(tuple(compared), None, "; ".join(why), carried + kept, inconclusive)
    fixed = tuple(e for e in unseen if not e.rule_id.startswith("VULN-") and e.fingerprint not in reasons)
    return Comparison(tuple(compared), fixed, None, kept, inconclusive)


def write(path: Path, findings: Sequence[Finding], keep: Sequence[Entry] = ()) -> None:
    """Write stable, sorted baseline bytes. Findings arrive masked from the capture sink."""
    rows: dict[str, dict[str, Any]] = {
        e.fingerprint: {
            "fingerprint": e.fingerprint,
            "target": e.target,
            "ruleId": e.rule_id,
            "message": e.message,
            "observed": e.observed,
            "owner": e.owner,
        }
        for e in keep
    }
    for finding in findings:
        if finding.dismissed or finding.advisor.lower() in {"vulnerability", "vulns"}:
            continue
        if finding.rule_id.startswith("VULN-"):
            continue
        rows[finding.fingerprint] = {
            "fingerprint": finding.fingerprint,
            "target": finding.target,
            "ruleId": finding.rule_id,
            "message": finding.message,
            "observed": finding.observed,
            "owner": owner_of(finding.test_node_id),
        }
    payload = {"schema": SCHEMA, "findings": [rows[key] for key in sorted(rows)]}
    text = clean_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")  # same cleaning as the report
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")  # stable bytes on every OS
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
