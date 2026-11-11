"""Runtime Insights for agents (stub: W5c I2 red)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

Row = dict[str, Any]


class UnknownObservation(Exception):  # noqa: N818 - BootUI's refusal, named for what it is
    pass


@dataclass(frozen=True)
class Steps:
    commands: Mapping[str, str]
    advertised: Callable[[str], bool] | None = None


def agent_list(report: Row, query: str | None, limit: int | None, steps: Steps) -> Row:
    keys = (
        "available", "unavailableReason", "query", "requests", "coverage", "checksNotRun", "observations", "omitted",
        "notExercised", "notExercisedOmitted", "limitations", "next",
    )  # fmt: skip
    return dict.fromkeys(keys)


def agent_detail(detail: Row, steps: Steps) -> Row:
    keys = (
        "available", "unavailableReason", "observation", "whatToCheck", "limitations", "columns", "rows", "truncated",
        "next",
    )  # fmt: skip
    return dict.fromkeys(keys)
