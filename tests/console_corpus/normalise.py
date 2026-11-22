"""Fixed response-body normalisers for values that vary between corpus runs."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any

_VERSION_KEYS = {"frameworkversion", "pythonversion", "sharpitversion"}
_EPOCH_KEYS = {"timestamp", "capturedat", "createdat", "updatedat", "startedat", "epochtime", "lastat"}
_DURATION_KEYS = {"duration", "durationseconds", "elapsed", "elapsedms", "latency", "latencyms", "timens", "timems"}
_ID_KEYS = {"requestid", "correlationid", "runid", "instanceid"}
_PROCESS_COUNTS = {"totalthreads", "daemonthreads", "peakthreads", "startedthreadcount", "taskcount"}
_PROTECTED_TEXT_KEY = re.compile(
    r"(?:^errors?$|error.?message|^message$|exception|masked|secret|token|password|credential)", re.IGNORECASE
)


def normalise(value: Any) -> Any:
    """Return a copy replacing only typed volatile leaves under exact keys."""
    if isinstance(value, Mapping) and {"status", "headers", "body"} <= value.keys():
        return {"status": value["status"], "headers": value["headers"], "body": _walk(value["body"])}
    return _walk(value)


def _walk(value: Any, key: str = "", process_snapshot: bool = False) -> Any:
    if isinstance(value, Mapping):
        snapshot = "threads" in value and "capturedAt" in value
        return {field: _walk_leaf(str(field), item, snapshot) for field, item in value.items()}
    if isinstance(value, list):
        return [_walk(item, key, process_snapshot) for item in value]
    if isinstance(value, tuple):
        return tuple(_walk(item, key, process_snapshot) for item in value)
    if isinstance(value, str):
        return _normalise_text(value, key)
    return value


def _walk_leaf(key: str, value: Any, process_snapshot: bool) -> Any:
    folded = key.casefold()
    replacement = _normalise_scalar(folded, key, value)
    if replacement is not None:
        return replacement
    return _walk(value, key, process_snapshot)


def _normalise_scalar(folded: str, key: str, value: Any) -> Any:
    if _PROTECTED_TEXT_KEY.search(key):
        return value
    for normaliser in (_version, _time, _identifier, _thread_leaf):
        replacement = normaliser(folded, value)
        if replacement is not None:
            return replacement
    return None


def _version(folded: str, value: Any) -> Any:
    if folded in _VERSION_KEYS and isinstance(value, str):
        return "<VERSION>"


def _time(folded: str, value: Any) -> Any:
    if (
        folded in _EPOCH_KEYS
        and isinstance(value, int)
        and not isinstance(value, bool)
        and 946_684_800_000 <= value <= 4_102_444_800_000
    ):
        return "<TIMESTAMP_MS>"
    if folded == "epochminute" and isinstance(value, int):
        return "<TIMESTAMP_MINUTE>"
    if folded in _DURATION_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
        return "<DURATION>"


def _identifier(folded: str, value: Any) -> Any:
    if folded in _ID_KEYS and isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,}", value):
        return "<REQUEST_ID>"
    if folded == "ordinal" and isinstance(value, int) and not isinstance(value, bool):
        return "<ORDINAL>"


def _thread_leaf(folded: str, value: Any) -> Any:
    if folded == "startupTimeMillis".casefold() and isinstance(value, int) and not isinstance(value, bool):
        return "<STARTUP_TIME>"
    if folded == "id" and isinstance(value, int) and not isinstance(value, bool):
        return "<THREAD_ID>"
    if folded == "count" and isinstance(value, int) and not isinstance(value, bool):
        return "<COUNT>"
    if folded == "state" and isinstance(value, str):
        return "<THREAD_STATE>"
    if folded in _PROCESS_COUNTS and isinstance(value, int) and not isinstance(value, bool):
        return "<COUNT>"


def _normalise_text(value: str, key: str) -> str:
    result = value
    try:
        uuid.UUID(value)
    except ValueError:
        pass
    else:
        result = "<UUID>"
    result = re.sub(r"(?:[A-Za-z]:\\[^\s\"']+|/(?:tmp|var/folders)/[^\s\"']+)", "<TEMP_PATH>", result)
    result = re.sub(r"(localhost:|127\.0\.0\.1:)\d+", r"\1<PORT>", result)
    result = re.sub(r"tests[/\\][\w/\\.-]+\.py:\d+", "<SOURCE_REF>", result)
    result = re.sub(r"asyncio-portal-[a-f0-9]+", "asyncio-portal-<ID>", result)
    result = re.sub(r"(?<=\()[^()]+\.py:\d+(?=\))", "<SOURCE_REF>", result)
    return result


NORMALISERS = (
    (
        "versions",
        "frameworkVersion, pythonVersion, sharpitVersion",
        "exact version-key strings vary across supported runtimes",
    ),
    (
        "timestamps",
        "exact epoch keys with integer millisecond values",
        "wall-clock epoch milliseconds vary between recordings",
    ),
    ("durations", "exact duration keys with numeric values", "measured durations vary between recordings"),
    (
        "identifiers",
        "exact ID keys with matching string values",
        "request and process identifiers are generated per run",
    ),
    ("source_refs", "test file and line references in strings", "source locations shift as tests evolve"),
)
