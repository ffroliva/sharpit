"""Fixed response-body normalisers for values that vary between corpus runs."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping
from typing import Any

Matcher = Callable[[str, Any], bool]
Replacement = Any
_PROTECTED_TEXT_KEY = re.compile(
    r"(?:^errors?$|error.?message|^message$|exception|masked|secret|token|password|credential)", re.IGNORECASE
)


def _field(pattern: str) -> Matcher:
    compiled = re.compile(pattern, re.IGNORECASE)
    return lambda key, _value: compiled.search(key) is not None


def _timestamp(_key: str, value: Any) -> bool:
    return isinstance(value, (int, float)) and 946_684_800_000 <= value <= 4_102_444_800_000


def _epoch_ms(key: str, value: Any) -> bool:
    named_timestamp = re.search(r"timestamp|captured|created|updated|started|epoch|last.*at", key, re.IGNORECASE)
    return bool(named_timestamp) and _timestamp(key, value)


def _epoch_minute(key: str, value: Any) -> bool:
    return "epochminute" in key.casefold() and isinstance(value, int)


def _ordinal(key: str, value: Any) -> bool:
    return key.casefold() == "ordinal" and isinstance(value, int)


def _process_collection(key: str, _value: Any) -> bool:
    return key.casefold() in {"threads", "tasks", "deadlockedthreadids", "statecounts"}


def _process_count(key: str, value: Any) -> bool:
    return key.casefold() in {
        "totalthreads",
        "daemonthreads",
        "peakthreads",
        "startedthreadcount",
        "taskcount",
    } and isinstance(value, int)


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
        r"(?:[A-Za-z]:\\(?:Users\\[^\\]+\\AppData\\Local\\Temp|Windows\\Temp)\\[^\s\"']+|~/(?:AppData/Local/Temp|tmp)/[^\s\"']+|/(?:tmp|var/folders)/[^\s\"']+)",
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
    (
        "epoch_minute",
        _epoch_minute,
        "<TIMESTAMP_MINUTE>",
        "bucket timestamps are expressed as epoch minutes",
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
    (
        "request_run_or_instance_id",
        _field(r"request.?id|correlation.?id|run.?id|instance.?id"),
        "<REQUEST_ID>",
        "request, process run, and app instance identifiers are newly generated",
    ),
    ("install_ordinal", _ordinal, "<ORDINAL>", "install ordinals increase across fresh app instances"),
    (
        "process_collections",
        _process_collection,
        "<PROCESS_COLLECTION>",
        "live thread and task contents depend on the test process",
    ),
    (
        "process_counts",
        _process_count,
        "<COUNT>",
        "live thread and task counts depend on the test process",
    ),
    ("uuid", _string, _uuid_text, "UUIDs are generated per request or process"),
    ("temp_path", _string, _path_text, "temporary directories are unique per test run"),
    ("port", _string, _port_text, "ephemeral localhost ports are allocated per test run"),
)


def normalise(value: Any) -> Any:
    """Return a copy with only named runtime-volatile body values replaced."""
    if isinstance(value, Mapping) and {"status", "headers", "body"} <= value.keys():
        return {"status": value["status"], "headers": value["headers"], "body": _normalise(value["body"])}
    return _normalise(value)


def _normalise(value: Any, key: str = "") -> Any:
    if isinstance(value, Mapping):
        result: dict[Any, Any] = {}
        process_snapshot = "threads" in value and "capturedAt" in value
        for field, item in value.items():
            key_text = str(field)
            if process_snapshot and key_text.casefold() == "page":
                result[field] = "<PROCESS_PAGE>"
                continue
            if _PROTECTED_TEXT_KEY.search(key_text):
                result[field] = item
                continue
            replacement = next(
                (
                    replacement
                    for name, matcher, replacement, _reason in NORMALISERS
                    if name not in {"uuid", "temp_path", "port"} and matcher(key_text, item)
                ),
                None,
            )
            if replacement is not None:
                result[field] = replacement(item) if callable(replacement) else replacement
            else:
                result[field] = _normalise(item, key_text)
        return result
    if isinstance(value, list):
        return [_normalise(item, key) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalise(item, key) for item in value)
    if isinstance(value, str):
        if _PROTECTED_TEXT_KEY.search(key):
            return value
        result = value
        for name, matcher, replacement, _reason in NORMALISERS:
            if name in {"uuid", "temp_path", "port"} and matcher("", result):
                result = replacement(result) if callable(replacement) else replacement
        return result
    return value
