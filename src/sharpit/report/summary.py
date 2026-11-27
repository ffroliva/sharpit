"""Render a ``sharpit-report/1`` mapping as escaped Markdown (pure: no environment, no network)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from sharpit.engine.advisors.findings import assessed_in_part, fails, partial_notes
from sharpit.engine.advisors.rules import severity_rank

TOP = 20
_MARKDOWN = re.compile(r"([\\`*_\[\]<>|&~])")
_WHITESPACE_RUN = re.compile(r"\s+")
_AUTOLINK = re.compile(r"(?i)\b(?:https:|http:)(?=//)|\bwww(?=\.)")


def _one_line(text: str) -> str:
    """Each whitespace run holding a line break becomes one space; one linear pass (a regex spanning the run's
    edges re-scans long space runs from every start, quadratic on untrusted text)."""
    return _WHITESPACE_RUN.sub(lambda m: " " if "\n" in m.group() or "\r" in m.group() else m.group(), text)


def _esc(value: object) -> str:
    """One physical line, every Markdown/HTML metacharacter backslash-escaped (finding text is untrusted)."""
    escaped = _MARKDOWN.sub(lambda m: chr(92) + m.group(1), _one_line(str(value)).strip())
    return _AUTOLINK.sub(lambda m: m.group(0) + "​", escaped)  # a zero-width space stops GFM autolinking


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}  # pyright: ignore[reportUnknownVariableType]


def _items(value: object) -> Sequence[object]:
    return value if isinstance(value, list) else []  # pyright: ignore[reportUnknownVariableType]


def _baseline_line(baseline: Mapping[str, object]) -> str:
    fixed = baseline.get("fixed")
    shown = (
        f"fixed {_esc(fixed)}" if fixed is not None else f"fixed n/a ({_esc(baseline.get('fixedReason') or 'unknown')})"
    )
    inconclusive = baseline.get("inconclusive")
    if isinstance(inconclusive, int):
        shown += f", inconclusive {inconclusive}"
    return f"- **Baseline:** {_esc(baseline.get('existing'))} existing, {_esc(baseline.get('new'))} new, {shown}"


def _order(finding: Mapping[str, object]) -> tuple[bool, int, str]:
    failing = fails({"dismissed": False, "severity": None, **finding})  # tolerate a finding missing keys
    return not failing, severity_rank(str(finding.get("severity"))), str(finding.get("fingerprint"))


def _partial_notes(report: Mapping[str, object]) -> list[str]:
    """One line per app an advisor assessed in part: a clean partial assessment passes, but it is not proof."""
    gate = str(_mapping(report.get("gates")).get("failOnSeverity") or "the gate severity")
    assessments: list[tuple[str, str | None, list[str], str]] = []
    for advisor in map(_mapping, _items(report.get("advisors"))):
        for app in map(_mapping, _items(advisor.get("apps"))):
            evidence = _mapping(app.get("evidence"))
            reason = app.get("reason")
            if assessed_in_part(str(app.get("status")), None if reason is None else str(reason), evidence):
                name = app.get("app")
                assessments.append(
                    (
                        str(advisor.get("advisor")),
                        None if name is None else str(name),
                        [str(x) for x in _items(evidence.get("limitations"))],
                        gate,
                    )
                )
    return [_esc(note) for note in partial_notes(assessments)]


def render_summary(report: Mapping[str, object]) -> str:
    totals = _mapping(report.get("totals"))
    every = (_mapping(f) for f in _items(report.get("findings")))
    findings = sorted((f for f in every if not f.get("dismissed")), key=_order)  # dismissed: as severityCounts
    lines = [
        "## sharpit report",
        "",
        f"- **Status:** {_esc(report.get('status'))}",
        f"- **Mode:** {_esc(report.get('mode') or 'gate')}",
        f"- **Tests:** {_esc(totals.get('tests'))}",
        f"- **Queries:** {_esc(totals.get('queries'))}",
        f"- **Findings:** {len(findings)}",
    ]
    baseline = _mapping(report.get("baseline"))
    if baseline:
        lines.append(_baseline_line(baseline))
    status_reasons = _items(report.get("statusReasons"))
    reasons = [_esc(r) for r in status_reasons]
    # an unknown run repeats its unknown reasons as status reasons: print each once
    reasons += [f"unknown: {_esc(r)}" for r in _items(report.get("unknownReasons")) if r not in status_reasons]
    if reasons:
        lines += ["", "### Reasons", "", *(f"- {r}" for r in reasons)]
    partial = _partial_notes(report)
    if partial:
        lines += ["", "### Partial assessments", "", *(f"- {n}" for n in partial)]
    shown = findings[:TOP]
    lines += ["", f"### Findings (showing {len(shown)} of {len(findings)})", ""]
    if shown:
        lines += ["| Severity | Rule | Target | Message | Baseline |", "| --- | --- | --- | --- | --- |"]
        lines += [
            "| "
            + " | ".join(_esc(f.get(k) or "-") for k in ("severity", "ruleId", "target", "message", "baselineState"))
            + " |"
            for f in shown
        ]
    else:
        lines.append("No findings.")
    return "\n".join(lines) + "\n"
