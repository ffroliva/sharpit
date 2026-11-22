"""Fixed response-body normalisers for values that vary between corpus runs."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any

NormaliserRow = tuple[str, type | tuple[type, ...], str, str]

NORMALISERS: tuple[NormaliserRow, ...] = (
    ("frameworkVersion", str, "<VERSION>", "framework version varies across dependency updates"),
    ("javaVersion", str, "<VERSION>", "Python runtime version varies across supported interpreters"),
    ("jdk", str, "<VERSION>", "Python runtime version and implementation vary across interpreters"),
    ("pythonVersion", str, "<VERSION>", "Python runtime version varies across supported interpreters"),
    ("sharpitVersion", str, "<VERSION>", "package version string varies across releases"),
    ("resource", str, "<SOURCE_REF>", "bean source file path and line vary across OSes and Python versions"),
    ("timestamp", int, "<TIMESTAMP_MS>", "wall-clock epoch milliseconds vary between recordings"),
    ("capturedAt", int, "<TIMESTAMP_MS>", "capture timestamp varies between recordings"),
    ("createdAt", int, "<TIMESTAMP_MS>", "creation timestamp varies between recordings"),
    ("updatedAt", int, "<TIMESTAMP_MS>", "update timestamp varies between recordings"),
    ("startedAt", int, "<TIMESTAMP_MS>", "process start timestamp varies between recordings"),
    ("epochTime", int, "<TIMESTAMP_MS>", "event epoch timestamp varies between recordings"),
    ("lastAt", int, "<TIMESTAMP_MS>", "most-recent observation timestamp varies between recordings"),
    ("epochMinute", int, "<TIMESTAMP_MINUTE>", "minute-bucket timestamp varies between recordings"),
    ("startupTimeMillis", int, "<STARTUP_TIME>", "measured startup duration varies between recordings"),
    ("duration", (int, float), "<DURATION>", "measured duration varies between recordings"),
    ("durationMs", (int, float), "<DURATION>", "measured duration in milliseconds varies between recordings"),
    ("durationSeconds", (int, float), "<DURATION>", "measured duration in seconds varies between recordings"),
    ("elapsed", (int, float), "<DURATION>", "elapsed time varies between recordings"),
    ("elapsedMs", (int, float), "<DURATION>", "elapsed milliseconds vary between recordings"),
    ("latency", (int, float), "<DURATION>", "measured latency varies between recordings"),
    ("latencyMs", (int, float), "<DURATION>", "measured latency in milliseconds varies between recordings"),
    ("timeNs", (int, float), "<DURATION>", "measured nanoseconds vary between recordings"),
    ("timeMs", (int, float), "<DURATION>", "measured milliseconds vary between recordings"),
    ("requestId", str, "<REQUEST_ID>", "request identifier is generated per request"),
    ("correlationId", str, "<REQUEST_ID>", "correlation identifier is generated per request"),
    ("runId", str, "<REQUEST_ID>", "run identifier is generated per install"),
    ("instanceId", str, "<REQUEST_ID>", "instance identifier is generated per process"),
    ("ordinal", int, "<ORDINAL>", "run ordinal increments across app installs"),
)

_LEAF_TABLE: dict[str, tuple[type | tuple[type, ...], str]] = {
    key.casefold(): (expected_type, replacement) for key, expected_type, replacement, _reason in NORMALISERS
}
_PROTECTED_TEXT_KEY = re.compile(
    r"(?:^errors?$|error.?message|^message$|exception|masked|secret|token|password|credential)", re.IGNORECASE
)
_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(localhost:|127\.0\.0\.1:)\d+"), r"\1<PORT>"),
    (re.compile(r"tests[/\\][\w/\\.-]+\.py:\d+"), "<SOURCE_REF>"),
    (re.compile(r"asyncio-portal-[a-f0-9]+"), "asyncio-portal-<ID>"),
    (re.compile(r"(?<=\()[^()]+\.py:\d+(?=\))"), "<SOURCE_REF>"),
)


def normalise(value: Any) -> Any:
    """Return a copy replacing only typed volatile leaves under exact keys."""
    if isinstance(value, Mapping) and {"status", "headers", "body"} <= value.keys():
        return {"status": value["status"], "headers": value["headers"], "body": _walk(value["body"])}
    return _walk(value)


def _walk(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {field: _walk_leaf(str(field), item) for field, item in value.items()}
    if isinstance(value, list):
        return [_walk(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_walk(item) for item in value)
    if isinstance(value, str):
        return _normalise_text(value)
    return value


def _walk_leaf(key: str, value: Any) -> Any:
    if isinstance(value, str) and _PROTECTED_TEXT_KEY.search(key):
        return value
    entry = _LEAF_TABLE.get(key.casefold())
    if entry is not None and not isinstance(value, bool) and isinstance(value, entry[0]):
        return entry[1]
    return _walk(value)


def _normalise_text(value: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        result = value
    else:
        result = "<UUID>"
    for pattern, replacement in _TEXT_PATTERNS:
        result = pattern.sub(replacement, result)
    return result
