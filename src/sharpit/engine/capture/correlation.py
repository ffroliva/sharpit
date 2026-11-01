"""Request correlation (spec §9): the current request, as the capture middleware set it, and sharpit's own marker."""

from __future__ import annotations

import secrets
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class RequestInfo:
    id: str
    context_id: str  # the installed sharpit context whose middleware created it (spec §6.2)
    method: str
    path: str  # masked
    endpoint: str | None
    started_ns: int
    finished_ns: int | None


REQUEST: ContextVar[RequestInfo | None] = ContextVar("sharpit_request", default=None)
# the running test as the pytest plugin tags it: (nodeid, attempt, phase); None outside a test (spec 0.3.0 §6.4)
TEST: ContextVar[tuple[str, int, str] | None] = ContextVar("sharpit_test", default=None)
INTERNAL: ContextVar[bool] = ContextVar("sharpit_internal", default=False)


def new_request_id() -> str:
    return secrets.token_hex(8)


@contextmanager
def internal() -> Generator[None]:
    """Mark sharpit's own work (health checks, migration reads) so the SQL listener skips it."""
    token = INTERNAL.set(True)
    try:
        yield
    finally:
        INTERNAL.reset(token)
