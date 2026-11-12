"""Sentence helpers for insight text. Callers pass journal fields only: masked and literal-free at offer."""

from __future__ import annotations

_FNV_BASIS, _FNV_PRIME, _MASK64 = 0xCBF29CE484222325, 0x100000001B3, (1 << 64) - 1


def stable_hash(value: str | None) -> str:
    """``InsightText.stableHash``: FNV-1a over UTF-16 code units, the first ten hex digits."""
    code = _FNV_BASIS
    data = (value or "").encode("utf-16-le")
    for i in range(0, len(data), 2):
        code = ((code ^ int.from_bytes(data[i : i + 2], "little")) * _FNV_PRIME) & _MASK64
    return f"{code:016x}"[:10]


def counted(count: int, noun: str, plural: str | None = None) -> str:
    """``InsightText.counted``: ``1 request``, ``3 requests``."""
    return f"{count} {noun if count == 1 else plural or noun + 's'}"


# repeated-selects' default floor (RepeatedSelects.java:44-61); the kind's lane shares these literals, not a copy
MIN_REQUESTS, HIGH_REPEAT_KEEP = 3, 10
UNDER_DEFAULT_FLOOR = (
    f"Repeated SELECTs under 50 ms of summed measured time, seen in fewer than {MIN_REQUESTS} requests and fewer than "
    f"{HIGH_REPEAT_KEEP} times in any one, are left out of the default agent list; "
    "ask for them with the query repeated-selects."
)


def unit(route: str | None) -> str:
    """``InsightText.unit``: what one unit of a route's work is called (sharpit's routes are all requests)."""
    del route  # BootUI's "@Scheduled " and "consume " routes come from Java producers no sharpit producer has
    return "request"


def millis(nanos: int) -> str:
    """``InsightText.millis``: milliseconds, one decimal below 10 ms."""
    ms = nanos / 1_000_000
    return f"{ms:.1f}" if ms < 10 else str(int(ms + 0.5))


def median(values: list[int]) -> int:
    """``RouteTimeBreakdown.median``: the lower median, 0 for none."""
    return sorted(values)[(len(values) - 1) // 2] if values else 0
