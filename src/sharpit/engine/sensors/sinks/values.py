"""Request values held for the security-sinks sensor (stub)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from sharpit.engine.capture.correlation import RequestInfo

MIN_LENGTH = 4
MAX_LENGTH = 256
MAX_VALUES = 32
ENTRIES = 128
MAX_CHECKS = 256
MAX_SCAN = 16 * 1024
MAX_COMPARISONS = 4 * 1024 * 1024
HASHES = 32
MATCHED_HASHES = 8
MAX_SPANS = 8
MAX_NAME = 64
DEADLINE_SECONDS = 60
MAX_ARGUMENTS = 32
MAX_QUERY = 8 * 1024
MAX_PAIRS = 64

F_PARTIAL = 1
F_OVERFLOW = 2
F_STOPPED = 4
F_REPEATED = 8
F_BUSY = 16
F_SEEN = 32

FROM_REQUEST_INPUT = "(not kept: it held request input)"
NOT_CHECKED = "(not kept: not checked for request input)"

Kind = Literal["command", "file"]


@dataclass(frozen=True, slots=True, repr=False)
class Match:
    names: tuple[str, ...]
    spans: tuple[tuple[int, int, int], ...]
    flags: int
    redacted: str | None
    numeric: frozenset[str]
    text_hash: int = field(default=0)


class _Entry:
    __slots__ = ("lock",)

    def __init__(self) -> None:
        self.lock = threading.Lock()


def _read_values(scope: Any) -> Any:
    return None


def _scan(scanned: str, values: Any) -> Any:
    return None


def _redact(*args: Any) -> str | None:
    return None


class RequestValues:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[str, _Entry] = {}

    def match(self, info: RequestInfo, text: str, kind: Kind) -> Match:
        self._entries.setdefault(info.id, _Entry())
        return Match((), (), 0, None, frozenset())

    def end(self, request_id: str) -> None:
        return None

    def clear(self) -> None:
        return None

    def held(self) -> int:
        return len(self._entries)

    def mark_seen(self, request_id: str, match: Match) -> None:
        return None


def unchecked(match: Match) -> bool:
    return False


def keyed_hash(text: str) -> int:
    return 0


def valid_name(name: str | None) -> bool:
    return False


def fallback_name(name: str | None) -> str:
    return ""


def number(text: str, start: int, end: int) -> bool:
    return False
