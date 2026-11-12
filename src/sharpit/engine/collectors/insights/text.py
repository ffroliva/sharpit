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
