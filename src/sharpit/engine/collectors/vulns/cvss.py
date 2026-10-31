"""CVSS v3.0/v3.1 Base Score and severity buckets (port of BootUI ``CvssV3BaseScore`` and the severity helpers of
``DependencyReports``).

Only the mandatory Base metric group is scored; Temporal and Environmental metrics are validated but ignored. CVSS v4.0
has no closed-form Base equation and v2 vectors carry no ``CVSS:3.x/`` prefix, so both score as ``None`` and callers
fall back to the advisory's ``database_specific.severity`` label.
"""

from __future__ import annotations

import math

_ATTACK_VECTOR = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_ATTACK_COMPLEXITY = {"L": 0.77, "H": 0.44}
_PRIVILEGES_UNCHANGED = {"N": 0.85, "L": 0.62, "H": 0.27}
_PRIVILEGES_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.5}
_USER_INTERACTION = {"N": 0.85, "R": 0.62}
_IMPACT = {"H": 0.56, "L": 0.22, "N": 0.0}
_VALID_METRICS = {
    "AV": "NALP",
    "AC": "LH",
    "PR": "NLH",
    "UI": "NR",
    "S": "UC",
    "C": "HLN",
    "I": "HLN",
    "A": "HLN",
    "E": "XUPFH",
    "RL": "XOTWU",
    "RC": "XURC",
    "CR": "XHML",
    "IR": "XHML",
    "AR": "XHML",
    "MAV": "XNALP",
    "MAC": "XLH",
    "MPR": "XNLH",
    "MUI": "XNR",
    "MS": "XUC",
    "MC": "XHLN",
    "MI": "XHLN",
    "MA": "XHLN",
}
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN", "NONE")


def cvss3_base_score(vector: str | None) -> float | None:
    """The Base Score (0.0-10.0) of a ``CVSS:3.0/`` or ``CVSS:3.1/`` vector, or None when it is not a valid one."""
    metrics = _parse_metrics(vector)
    if metrics is None:
        return None
    scope = metrics.get("S")
    changed = scope == "C"
    if not changed and scope != "U":
        return None
    try:
        av = _ATTACK_VECTOR[metrics["AV"]]
        ac = _ATTACK_COMPLEXITY[metrics["AC"]]
        pr = (_PRIVILEGES_CHANGED if changed else _PRIVILEGES_UNCHANGED)[metrics["PR"]]
        ui = _USER_INTERACTION[metrics["UI"]]
        c, i, a = _IMPACT[metrics["C"]], _IMPACT[metrics["I"]], _IMPACT[metrics["A"]]
    except KeyError:
        return None
    iss = 1 - ((1 - c) * (1 - i) * (1 - a))
    impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if changed else 6.42 * iss
    if impact <= 0:
        return 0.0
    exploitability = 8.22 * av * ac * pr * ui
    combined = 1.08 * (impact + exploitability) if changed else impact + exploitability
    return _round_up(min(combined, 10.0))


def _parse_metrics(vector: str | None) -> dict[str, str] | None:
    if vector is None or not vector.startswith(("CVSS:3.0/", "CVSS:3.1/")):
        return None
    metrics: dict[str, str] = {}
    for segment in vector[len("CVSS:3.x/") :].split("/"):
        metric, sep, value = segment.partition(":")
        allowed = _VALID_METRICS.get(metric)
        if not sep or allowed is None or len(value) != 1 or value not in allowed or metric in metrics:
            return None
        metrics[metric] = value
    return metrics


def _round_up(value: float) -> float:
    """CVSS Appendix A "Roundup" in integer arithmetic; Java's half-up ``Math.round``, not Python's banker's round."""
    scaled = math.floor(value * 100000 + 0.5)
    if scaled % 10000 == 0:
        return scaled / 100000.0
    return (math.floor(scaled / 10000.0) + 1) / 10.0


def parse_score(kind: str | None, value: str | None) -> float | None:
    """Base Score of an OSV ``severity[]`` entry: only ``CVSS_V3`` entries carrying a v3 vector are scored."""
    if kind != "CVSS_V3" or value is None:
        return None
    return cvss3_base_score(value)


def severity_for(score: float | None) -> str:
    """BootUI's score buckets: >=9 CRITICAL, >=7 HIGH, >=4 MEDIUM, >0 LOW, 0 NONE; anything else UNKNOWN."""
    if score is None or not math.isfinite(score) or score < 0.0 or score > 10.0:
        return "UNKNOWN"
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW" if score > 0.0 else "NONE"


def severity_from_text(label: str | None) -> str:
    """A ``database_specific.severity`` label: GHSA's ``MODERATE`` is MEDIUM, unknown labels are UNKNOWN."""
    if label is None or not label.strip():
        return "UNKNOWN"
    normalized = label.strip().upper()
    if normalized == "MODERATE":
        return "MEDIUM"
    return normalized if normalized in SEVERITIES else "UNKNOWN"
