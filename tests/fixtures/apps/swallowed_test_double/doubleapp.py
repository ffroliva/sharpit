"""Two swallowing handlers: one a test double breaks, one a real defect breaks (issue 68)."""

from __future__ import annotations

import asyncio
from typing import Any


async def _fetch(client: Any) -> str:
    try:
        return await client.fetch()  # a ``MagicMock`` result cannot be awaited
    except Exception:
        return "unknown"


def label(client: Any) -> str:
    return asyncio.run(_fetch(client))


def title(client: Any) -> str:
    try:
        return client.title.upper()  # the planted defect: a real client with no ``title``
    except Exception:
        return ""
