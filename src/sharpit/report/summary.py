"""Render a ``sharpit-report/1`` mapping as escaped Markdown (pure: no environment, no network)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

TOP = 20
_SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
_MARKDOWN = re.compile(r"([\`*_\[\]<>|&~])")
_LINE_BREAKS = re.compile(r"\s*[\r\n]+\s*")


def _esc(value: object) -> str:
    """One physical line, every Markdown/HTML metacharacter backslash-escaped (finding text is untrusted)."""
    return _MARKDOWN.sub(lambda m: chr(92) + m.group(1), _LINE_BREAKS.sub(" ", str(value)).strip())


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}  # pyright: ignore[reportUnknownVariableType]


def _items(value: object) -> Sequence[object]:
    return value if isinstance(value, list) else []  # pyright: ignore[reportUnknownVariableType]


def _baseline_line(baseline: Mapping[str, object]) -> str:
    fixed = baseline.get("fixed")
    shown = f"fixed {fixed}" if fixed is not None else f"fixed n/a ({_esc(baseline.get('fixedReason') or 'unknown')})"
    return f"- **Baseline:** {_esc(baseline.get('existing'))} existing, {_esc(baseline.get('new'))} new, {shown}"


def _order(finding: Mapping[str, object]) -> tuple[int, str]:
    return _SEVERITY_RANK.get(str(finding.get("severity")), len(_SEVERITY_RANK)), str(finding.get("fingerprint"))


def render_summary(report: Mapping[str, object]) -> str:
    totals = _mapping(report.get("totals"))
    findings = sorted((_mapping(f) for f in _items(report.get("findings"))), key=_order)
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
    reasons = [_esc(r) for r in _items(report.get("statusReasons"))]
    reasons += [f"unknown: {_esc(r)}" for r in _items(report.get("unknownReasons"))]
    if reasons:
        lines += ["", "### Reasons", "", *(f"- {r}" for r in reasons)]
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
