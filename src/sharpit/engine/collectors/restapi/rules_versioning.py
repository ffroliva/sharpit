"""REST API versioning rule checks."""

from __future__ import annotations

from collections.abc import Sequence

from sharpit.engine.collectors.restapi.rules_common import (
    APPLICATION,
    NON_API_SEGMENTS,
    VERSION,
    Check,
    Violation,
    shared_describe,
    shared_segments,
)
from sharpit.engine.spi import ApiRouteInfo


def _ver001(routes: Sequence[ApiRouteInfo], _handlers: Sequence[str]) -> list[Violation]:
    api = [r for r in routes if shared_segments(r.path) and shared_segments(r.path)[0].lower() not in NON_API_SEGMENTS]
    unversioned = [r for r in api if not any(VERSION.fullmatch(s) for s in shared_segments(r.path))]
    if not unversioned:
        return []
    if len(unversioned) == len(api):
        return [
            Violation(
                APPLICATION,
                "No API version signal (no /vN path, version header/param, or versioned media type) was detected"
                f" across {len(api)} handler(s).",
            )
        ]
    examples = ", ".join(shared_describe(r) for r in unversioned[:5])
    return [
        Violation(
            APPLICATION,
            f"Versioning is applied inconsistently: {len(unversioned)} of {len(api)} API handler(s) have no version"
            f" signal while others do. Unversioned example(s): {examples}",
        )
    ]


CHECKS: dict[str, Check] = {
    "RAPI-VER-001": _ver001,
}
