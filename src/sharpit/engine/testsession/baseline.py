"""Stable, explicit baseline file format for pytest gate findings."""

from __future__ import annotations

import json
import os
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sharpit.engine.advisors.findings import Finding
from sharpit.engine.testsession.report import clean_text

SCHEMA = "sharpit-baseline/1"


@dataclass(frozen=True)
class Entry:
    fingerprint: str
    rule_id: str
    target: str
    message: str
    observed: int | None


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
        entries[fingerprint] = Entry(fingerprint, row["ruleId"], row["target"], row["message"], observed)
    return Baseline(entries, raw)


def compare(
    findings: Sequence[Finding], baseline: Baseline | None, *, partial: bool, ran: Collection[str] | None = None
) -> Comparison:
    """Annotate current findings and report baseline entries no longer seen."""
    from dataclasses import replace

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
    if carried:  # an advisor that did not run completely saw nothing: its entries are neither fixed nor dropped
        names = ", ".join(sorted({e.fingerprint.split(":", 1)[0] for e in carried}))
        return Comparison(tuple(compared), None, f"advisor did not run: {names}", carried)
    return Comparison(tuple(compared), tuple(e for e in unseen if not e.rule_id.startswith("VULN-")), None)


def write(path: Path, findings: Sequence[Finding], keep: Sequence[Entry] = ()) -> None:
    """Write stable, sorted baseline bytes. Findings arrive masked from the capture sink."""
    rows: dict[str, dict[str, Any]] = {
        e.fingerprint: {
            "fingerprint": e.fingerprint,
            "target": e.target,
            "ruleId": e.rule_id,
            "message": e.message,
            "observed": e.observed,
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
