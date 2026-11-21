"""The HTTP security advisor: explicit response expectations over the exchanges a test run made (T1).

Framework-free. It evaluates only what the host configured (a response header that must be present, the statuses a
route may answer); it infers no policy from route metadata, and it never sees a value, a body or a raw path.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple

MIN_STATUS, MAX_STATUS = 100, 599


class HeaderExpectation(NamedTuple):
    method: str
    route: str
    header: str  # lower-cased: header names compare case-insensitively


class StatusExpectation(NamedTuple):
    method: str
    route: str
    statuses: tuple[int, ...]  # sorted; any listed status satisfies the expectation


def _split(line: str, option: str, shape: str) -> tuple[str, str, str]:
    """``METHOD ROUTE=VALUE``: split on the first space and the last ``=``; a route may contain ``=`` or ``,``."""
    method, _, rest = line.strip().partition(" ")
    route, _, value = rest.rpartition("=")
    method, route, value = method.strip().upper(), route.strip(), value.strip()
    if not (method and route and value):
        raise ValueError(f"{option} {line!r}: expected {shape}")
    return method, route, value


def parse_header_expectations(lines: Iterable[str], option: str) -> tuple[HeaderExpectation, ...]:
    found = (_split(line, option, "METHOD ROUTE=HEADER") for line in lines if line.strip())
    return tuple(dict.fromkeys(HeaderExpectation(m, r, v.lower()) for m, r, v in found))


def _status(text: str, line: str, option: str) -> int:
    shape = "METHOD ROUTE=STATUS[,STATUS...]"
    if not text.isascii() or not text.isdigit() or not MIN_STATUS <= int(text) <= MAX_STATUS:
        raise ValueError(f"{option} {line!r}: expected {shape} with statuses from {MIN_STATUS} to {MAX_STATUS}")
    return int(text)


def parse_status_expectations(lines: Iterable[str], option: str) -> tuple[StatusExpectation, ...]:
    union: dict[tuple[str, str], set[int]] = {}
    for line in (line for line in lines if line.strip()):
        method, route, value = _split(line, option, "METHOD ROUTE=STATUS[,STATUS...]")
        union.setdefault((method, route), set()).update(
            _status(part.strip(), line, option) for part in value.split(",")
        )
    return tuple(StatusExpectation(m, r, tuple(sorted(s))) for (m, r), s in union.items())
