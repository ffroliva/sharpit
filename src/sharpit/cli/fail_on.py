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
from dataclasses import dataclass
from typing import Any

# Plain exit codes: 0 pass, 1 cannot evaluate, 3 threshold met
PASS: int = 0
CANNOT_EVALUATE: int = 1
THRESHOLD_MET: int = 3


class Severity(enum.StrEnum):
    """The severities the gate understands, most severe first. Any other severity in an answer is ignored."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    @property
    def label(self) -> str:
        return self.value.lower()


class Criterion(enum.StrEnum):
    """A severity threshold or an evidence-sufficiency gate."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"
    INSUFFICIENT = "INSUFFICIENT"

    @property
    def label(self) -> str:
        return self.value.lower()


@dataclass(frozen=True)
class Verdict:
    """What the gate decided: exit_code (0 pass, 1 cannot evaluate, 3 threshold met) and message."""

    exit_code: int
    message: str = ""


# Every advisor scan and cached report in sharpit, which share the compact severity summary.
ADVISOR_TOOLS: frozenset[str] = frozenset()
TOOLS = ADVISOR_TOOLS

# Reports with explicit evidence sufficiency states.
INSUFFICIENT_TOOLS: frozenset[str] = frozenset(
    {
        "get_exceptions",
        "get_runtime_insight",
        "get_runtime_insights",
    }
)

# Reads that grade nothing: runtime views have no severities to gate on.
EXCLUDED: frozenset[str] = frozenset(
    {
        "get_postgresql_report",
        "get_mysql_report",
    }
)

_EVALUATED = frozenset({"SCANNED", "PARTIAL"})
_WORD_PATTERN = re.compile(r"^[A-Za-z_]{1,32}$")


def supports(tool_name: str) -> bool:
    """Whether the named tool accepts --fail-on."""
    return tool_name in TOOLS or tool_name in INSUFFICIENT_TOOLS


def supports_severity(tool_name: str) -> bool:
    """Whether the named tool accepts a severity threshold."""
    return tool_name in TOOLS


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
    return "insufficient" if supports_insufficient(tool_name) else accepted_severities()


def parse(tool_name: str, value: str) -> Criterion:
    """Reads a --fail-on value allowed for the selected tool, ignoring case."""
    # Stub: return Criterion.INFO without validating to fail red check on assertion
    return Criterion.INFO


def clean_tool_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Ensure --fail-on option is consumed by the CLI and never sent as a tool argument."""
    return arguments


def effective_query(tool_name: str, query: str | None, criterion: Criterion | None) -> str | None:
    """The query argument to send to the tool.

    An insufficient-evidence gate on get_runtime_insights requests 'all' when none was supplied.
    """
    # Stub: return query unchanged
    return query


def evaluate(payload: Any, criterion: Criterion, tool_name: str) -> Verdict:
    """Decides the verdict (exit_code and message) for a tool answer."""
    # Stub: return invalid exit code 999 to fail red check on assertion
    return Verdict(999, "stub")
