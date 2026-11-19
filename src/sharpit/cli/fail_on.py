"""The CLI-side finding-severity and evidence-sufficiency gates behind --fail-on.

The option is consumed here and never reaches the tool arguments: the gate reads the advisor answer
the tool already returned. A gate that cannot be evaluated is an error (exit code 1), never a pass --
a NOT_SCANNED report carries zero counts too, and exiting 0 on it would let an unscanned build through.

PARTIAL is evaluated, not refused: it means some evidence was unavailable, which is the normal state
of an advisor on a real application. The retained findings still gate, and the note says the absence
of a finding is not proof of its absence.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeGuard

from sharpit.cli.exit_codes import ExitCodes
from sharpit.cli.manifest import ManifestTool

GET_RUNTIME_INSIGHTS: str = "get_runtime_insights"

_OPTION_TO_WIRE: Mapping[str, str] = {
    "scan_id": "scanId",
    "scanId": "scanId",
    "query": "query",
    "limit": "limit",
    "id": "id",
    "offset": "offset",
}


def effective_query(tool_name: str, query: str | None, criterion: Criterion | None) -> str | None:
    """The query argument to send to the tool.

    An insufficient-evidence gate on get_runtime_insights requests 'all' when none was supplied.
    """
    if criterion == Criterion.INSUFFICIENT and tool_name == GET_RUNTIME_INSIGHTS and query is None:
        return "all"
    return query


def build_tool_arguments(
    tool: ManifestTool,
    options: Mapping[str, object],
    criterion: Criterion | None = None,
) -> dict[str, object]:
    """Build tool arguments from declared tool arguments only (an allowlist).

    Maps CLI option names to wire names (scan_id -> scanId, query, limit, id, offset)
    and applies effective_query when query is handled.
    CLI options like fail_on, json, url, token, api_path never reach the call.
    Task 7 wires this helper into the command runner.
    """
    allowed = set(tool.arguments)
    return {k: v for k, v in options.items() if k in allowed and v is not None}



class _Labeled(enum.StrEnum):
    @property
    def label(self) -> str:
        return self.value.lower()


class Severity(_Labeled):
    """The severities the gate understands, most severe first. Any other severity in an answer is ignored."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    @property
    def rank(self) -> int:
        return list(Severity).index(self)

    def at_or_above(self, threshold: Severity) -> bool:
        return self.rank <= threshold.rank


class Criterion(_Labeled):
    """A severity threshold or an evidence-sufficiency gate."""

    CRITICAL = Severity.CRITICAL.value
    HIGH = Severity.HIGH.value
    MEDIUM = Severity.MEDIUM.value
    LOW = Severity.LOW.value
    INFO = Severity.INFO.value
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class Verdict:
    """What the gate decided: exit_code and message."""

    exit_code: int
    message: str


# Every advisor scan and cached report in sharpit, which share the compact severity summary.
ADVISOR_TOOLS: frozenset[str] = frozenset(
    {
        "architecture_scan",
        "get_architecture_report",
        "database_advisor_scan",
        "get_database_advisor_report",
        "fastapi_scan",
        "get_fastapi_report",
        "rest_api_scan",
        "get_rest_api_report",
        "security_scan",
        "get_security_report",
        "vulnerabilities_scan",
        "get_vulnerabilities_report",
    }
)

# Reports with explicit evidence sufficiency states.
INSUFFICIENT_TOOLS: frozenset[str] = frozenset(
    {
        "get_runtime_insight",
        GET_RUNTIME_INSIGHTS,
    }
)

# Reads that grade nothing: runtime views and a heap-dump inventory have no severities to gate on,
# or lack evidence sensors.
EXCLUDED: Mapping[str, str] = {}

_EVALUATED = frozenset({"SCANNED", "PARTIAL"})
_WORD_PATTERN = re.compile(r"[A-Za-z_]{1,32}")


def _trim_java(s: str) -> str:
    """Strip characters <= U+0020 from both ends, matching Java's String.trim()."""
    start = 0
    end = len(s)
    while start < end and ord(s[start]) <= 0x20:
        start += 1
    while end > start and ord(s[end - 1]) <= 0x20:
        end -= 1
    return s[start:end]


def _parse_severity(text: str) -> Severity | None:
    norm = _trim_java(text).upper()
    try:
        return Severity(norm)
    except ValueError:
        return None


def supports_severity(tool_name: str) -> bool:
    """Whether the named tool accepts a severity threshold."""
    return tool_name in ADVISOR_TOOLS


def supports_insufficient(tool_name: str) -> bool:
    """Whether the named tool accepts --fail-on insufficient."""
    return tool_name in INSUFFICIENT_TOOLS


def accepted_severities() -> str:
    """The accepted severity values as shown in usage errors."""
    return ", ".join(s.label for s in Severity)


def accepted(tool_name: str) -> str:
    """Accepted criteria for the tool."""
    if supports_severity(tool_name) and supports_insufficient(tool_name):
        return f"{accepted_severities()}, insufficient"
    if supports_insufficient(tool_name):
        return "insufficient"
    if supports_severity(tool_name):
        return accepted_severities()
    return f"'{tool_name}' takes no --fail-on"


def parse(tool_name: str, value: str) -> Criterion:
    """Reads a --fail-on value allowed for the selected tool, ignoring case."""
    if tool_name == "get_exceptions":
        raise ValueError("sharpit records no caught-in-code evidence, so this gate cannot be evaluated")
    if not supports_severity(tool_name) and not supports_insufficient(tool_name):
        raise ValueError(f"'{tool_name}' takes no --fail-on.")
    normalized = _trim_java(value).upper()
    if normalized == "INSUFFICIENT" and supports_insufficient(tool_name):
        return Criterion.INSUFFICIENT
    if supports_severity(tool_name):
        sev = _parse_severity(normalized)
        if sev is not None:
            return Criterion[sev.name]
    raise ValueError(f"'{value}' is not accepted here; use one of {accepted(tool_name)}.")


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _is_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_word(text: str) -> bool:
    return bool(_WORD_PATTERN.fullmatch(text))


def _non_negative_integer(val: object) -> TypeGuard[int]:
    return isinstance(val, int) and not isinstance(val, bool) and val >= 0


def _unevaluable(reason: str) -> Verdict:
    return Verdict(ExitCodes.ERROR, f"cannot evaluate --fail-on: {reason}.")


def _record_count(
    severity: str,
    count: int,
    threshold: Severity,
    met: dict[str, str],
    ignored: dict[str, str],
) -> None:
    text = str(count)
    sev = _parse_severity(severity)
    if sev is None:
        key = severity if _is_word(severity) else "?"
        ignored[key] = f"{ignored[key]}+{text}" if key in ignored else text
    elif sev.at_or_above(threshold):
        norm_key = sev.value
        met[norm_key] = f"{met[norm_key]}+{text}" if norm_key in met else text


def _tally_counts(counts: Sequence[object], threshold: Severity) -> tuple[dict[str, str], dict[str, str]] | Verdict:
    met: dict[str, str] = {}
    ignored: dict[str, str] = {}
    for entry in counts:
        if not _is_mapping(entry):
            return _unevaluable("a severityCounts entry has no string severity")
        severity = entry.get("severity")
        count = entry.get("count")
        if not isinstance(severity, str):
            return _unevaluable("a severityCounts entry has no string severity")
        if not _non_negative_integer(count):
            return _unevaluable("a count in severityCounts is not a non-negative integer")
        if count == 0:
            continue
        _record_count(severity, count, threshold, met, ignored)
    return met, ignored


def _scan_status(payload: Mapping[str, object]) -> str | Verdict:
    scan = payload.get("scan")
    if not _is_mapping(scan):
        return _unevaluable("the answer has no scan status")
    status = scan.get("status")
    if not isinstance(status, str):
        return _unevaluable("the answer has no scan status")
    if status not in _EVALUATED:
        display = status if _is_word(status) else "not recognised"
        return _unevaluable(f"the scan status is {display}, so its counts are not evidence")
    return status


def _format_severity_notes(
    met: Mapping[str, str],
    ignored: Mapping[str, str],
    status: str,
    threshold: Severity,
) -> str:
    notes: list[str] = []
    if met:
        met_str = ", ".join(f"{k}={v}" for k, v in met.items())
        notes.append(f"--fail-on {threshold.label}: found {met_str}.")
    if ignored:
        ignored_str = ", ".join(f"{k}={v}" for k, v in ignored.items())
        notes.append(f"note: --fail-on does not count {ignored_str}.")
    if status == "PARTIAL" and not met:
        notes.append(
            f"note: the scan is PARTIAL, so having no finding at or above {threshold.name} "
            "is not proof there is none; see the evidence in the output."
        )
    return "\n".join(notes)


def _evaluate_severity(payload: object, threshold: Severity) -> Verdict:
    if not _is_mapping(payload):
        return _unevaluable("the answer has no severityCounts entries")
    counts = payload.get("severityCounts")
    if not _is_list(counts) or len(counts) == 0:
        return _unevaluable("the answer has no severityCounts entries")

    tallied = _tally_counts(counts, threshold)
    if isinstance(tallied, Verdict):
        return tallied
    met, ignored = tallied

    status = _scan_status(payload)
    if isinstance(status, Verdict):
        return status

    evidence = payload.get("evidence")
    usable = evidence.get("usable") if _is_mapping(evidence) else None
    if len(met) == 0 and isinstance(usable, bool) and not usable:
        return _unevaluable("the scan found no usable evidence, so zero findings is not an assessment")

    notes = _format_severity_notes(met, ignored, status, threshold)
    exit_code = ExitCodes.THRESHOLD if met else ExitCodes.SUCCESS
    return Verdict(exit_code, notes)


def _evaluate_runtime_insight(payload: Mapping[str, object]) -> Verdict:
    observation = payload.get("observation")
    if not _is_mapping(observation):
        return _unevaluable("the observation has no status")
    obs_status = observation.get("status")
    if not isinstance(obs_status, str):
        return _unevaluable("the observation has no status")
    if obs_status in ("OBSERVED", "FINDING"):
        return Verdict(ExitCodes.SUCCESS, "")
    if obs_status in ("INSUFFICIENT", "PARTIAL"):
        return Verdict(ExitCodes.THRESHOLD, f"--fail-on insufficient: observation status is {obs_status}.")
    if obs_status in ("UNAVAILABLE", "NOT_APPLICABLE"):
        return _unevaluable(f"the observation status is {obs_status}")
    return _unevaluable("the observation status is not recognised")


def _tally_observations(observations: Sequence[object]) -> tuple[int, int] | Verdict:
    listed_insufficient = 0
    listed_partial = 0
    for observation in observations:
        if not _is_mapping(observation):
            return _unevaluable("a listed observation has no status")
        obs_status = observation.get("status")
        if not isinstance(obs_status, str):
            return _unevaluable("a listed observation has no status")
        if obs_status not in ("OBSERVED", "INSUFFICIENT", "PARTIAL"):
            return _unevaluable("an observation status is not recognised")
        if obs_status == "INSUFFICIENT":
            listed_insufficient += 1
        elif obs_status == "PARTIAL":
            listed_partial += 1
    return listed_insufficient, listed_partial


def _verify_empty_runtime_insights(payload: Mapping[str, object]) -> Verdict | None:
    query = payload.get("query")
    requests = payload.get("requests")
    if (
        not isinstance(query, str)
        or _trim_java(query).lower() != "all"
        or not _non_negative_integer(requests)
        or requests == 0
    ):
        return _unevaluable("an empty result requires query=all and request activity")
    return None


def _evaluate_runtime_insights(payload: Mapping[str, object]) -> Verdict:
    insufficient = payload.get("insufficient")
    partial = payload.get("partial")
    observations = payload.get("observations")
    omitted = payload.get("omitted")
    if not _is_list(observations) or not _non_negative_integer(omitted):
        return _unevaluable("the runtime-insights list is incomplete or misshapen")

    tallied = _tally_observations(observations)
    if isinstance(tallied, Verdict):
        return tallied
    listed_insufficient, listed_partial = tallied

    if not _non_negative_integer(insufficient) or not _non_negative_integer(partial):
        return _unevaluable("the answer has no valid insufficient and partial counts")

    if insufficient < listed_insufficient or partial < listed_partial:
        return _unevaluable("the runtime-insights aggregate counts do not match the listed results")
    hidden_insufficient = insufficient - listed_insufficient
    hidden_partial = partial - listed_partial
    if hidden_insufficient > omitted or hidden_partial > (omitted - hidden_insufficient):
        return _unevaluable("the runtime-insights aggregate counts do not match the listed results")

    if insufficient == 0 and partial == 0 and len(observations) == 0 and omitted == 0:
        empty_err = _verify_empty_runtime_insights(payload)
        if empty_err is not None:
            return empty_err

    if insufficient > 0 or partial > 0:
        return Verdict(
            ExitCodes.THRESHOLD,
            f"--fail-on insufficient: found {insufficient} insufficient and {partial} partial evidence rows.",
        )
    return Verdict(ExitCodes.SUCCESS, "")


def _evaluate_insufficient(payload: object, tool_name: str) -> Verdict:
    if not _is_mapping(payload) or payload.get("available") is not True:
        return _unevaluable("the answer is unavailable")
    if tool_name == "get_runtime_insight":
        return _evaluate_runtime_insight(payload)
    if tool_name == GET_RUNTIME_INSIGHTS:
        return _evaluate_runtime_insights(payload)
    return _unevaluable("the selected tool does not report evidence sufficiency")


def evaluate(payload: object, criterion: Criterion, tool_name: str) -> Verdict:
    """Decides the verdict (exit_code and message) for a tool answer."""
    if criterion == Criterion.INSUFFICIENT:
        return _evaluate_insufficient(payload, tool_name)
    return _evaluate_severity(payload, Severity[criterion.name])
