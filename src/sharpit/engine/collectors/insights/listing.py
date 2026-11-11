"""Stub (red): the default listing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sharpit.engine.collectors.insights.finding import Finding


class Outcome(Enum):
    PASSED = True
    NOT_VALIDATED = True
    FAILED = False
    UNDER_SAMPLED = False
    NOT_LISTED = False
    NOT_JUDGED = False

    @property
    def listed(self) -> bool:
        return self.value


@dataclass(frozen=True)
class Entry:
    kind: str
    outcome: Outcome
    unlisted_reason: str | None


MEMORY = ""
KINDS: dict[str, Entry] = {}


def of(kind: str) -> Entry:
    return Entry(kind, Outcome.PASSED, None)


def apply(kind: str, finding: Finding) -> Finding:
    del kind
    return finding
