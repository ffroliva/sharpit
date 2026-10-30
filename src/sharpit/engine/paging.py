"""Shared q/offset/limit paging (port of BootUI ``PagedList`` and ``PageMetadata``)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

MAX_LIMIT = 1000


class BadRequest(Exception):
    """A client error that the web layer renders as ``400 {"error": message}``."""


def parse_int_param(raw: str | None, name: str) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        raise BadRequest(f"Invalid '{name}' parameter") from None


def paged[T](
    items: Sequence[T],
    q: str | None,
    offset: int | None,
    limit: int | None,
    text: Callable[[T], Iterable[str | None]],
) -> tuple[list[T], dict[str, Any]]:
    needle = (q or "").strip().lower()
    matched = [i for i in items if not needle or any(s is not None and needle in s.lower() for s in text(i))]
    start = max(offset or 0, 0)
    effective_limit = len(matched) if limit is None else min(max(limit, 1), MAX_LIMIT)
    page = matched[start : start + effective_limit]
    return page, {
        "total": len(items),
        "matched": len(matched),
        "offset": start,
        "limit": effective_limit,
        "returned": len(page),
        "hasMore": start + len(page) < len(matched),
    }
