"""Fixed response-body normalisers for values that vary between corpus runs."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping
from typing import Any

Matcher = Callable[[str, Any], bool]
Replacement = Any


def _field(pattern: str) -> Matcher:
    compiled = re.compile(pattern, re.IGNORECASE)
    return lambda key, _value: compiled.search(key) is not None


def _timestamp(_key: str, value: Any) -> bool:
    return isinstance(value, (int, float)) and 946_684_800_000 <= value <= 4_102_444_800_000


def _epoch_ms(key: str, value: Any) -> bool:
    named_timestamp = re.search(r"timestamp|created|updated|started|epoch|last.*at", key, re.IGNORECASE)
    return bool(named_timestamp) and _timestamp(key, value)


def _uuid_text(value: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        return value
    return "<UUID>"


def _string(_key: str, value: Any) -> bool:
    return isinstance(value, str)


def _path_text(value: str) -> str:
    return re.sub(
        r"(?:[A-Za-z]:\\(?:Users\\[^\\]+\\AppData\\Local\\Temp|Windows\\Temp)\\[^\s\"']+|/(?:tmp|var/folders)/[^\s\"']+)",
        "<TEMP_PATH>",
        value,
    )


def _port_text(value: str) -> str:
    return re.sub(r"(localhost:|127\.0\.0\.1:)\d+", r"\1<PORT>", value)


NORMALISERS: tuple[tuple[str, Matcher, Replacement, str], ...] = (
    (
        "epoch_ms",
        _epoch_ms,
        "<TIMESTAMP_MS>",
        "wall-clock epoch milliseconds vary between recordings",
    ),
    ("uptime", _field(r"uptime"), "<UPTIME>", "elapsed process uptime grows between recordings"),
    (
        "memory_heap",
        _field(r"memory|heap|allocated|resident"),
        "<MEMORY>",
        "runtime memory figures depend on process state",
    ),
    (
        "duration",
        _field(r"duration|elapsed|latency|time_ns|time_ms"),
        "<DURATION>",
        "measured durations vary between recordings",
    ),
    ("request_id", _field(r"request.?id|correlation.?id"), "<REQUEST_ID>", "request identifiers are newly generated"),
    ("uuid", _string, _uuid_text, "UUIDs are generated per request or process"),
    ("temp_path", _string, _path_text, "temporary directories are unique per test run"),
    ("port", _string, _port_text, "ephemeral localhost ports are allocated per test run"),
)


def normalise(value: Any) -> Any:
    """Return a copy with only named runtime-volatile body values replaced."""
    if isinstance(value, Mapping):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            replacement = next(
                (replacement for _name, matcher, replacement, _reason in NORMALISERS if matcher(key_text, item)),
                None,
            )
            if replacement is not None:
                result[key] = replacement(item) if callable(replacement) else replacement
            else:
                result[key] = normalise(item)
        return result
    if isinstance(value, list):
        return [normalise(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalise(item) for item in value)
    if isinstance(value, str):
        result = value
        for name, matcher, replacement, _reason in NORMALISERS:
            if name in {"uuid", "temp_path", "port"} and matcher("", result):
                result = replacement(result) if callable(replacement) else replacement
        return result
    return value
