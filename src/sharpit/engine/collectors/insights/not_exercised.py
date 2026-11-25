"""Declared routes no completed request reached (BootUI v2.5.0 NotExercisedRoutes)."""

from collections.abc import Collection, Sequence

from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.spi import RouteInfo

UNRECORDED = (
    "The runtime journal does not record the http source (SHARPIT_RUNTIME_JOURNAL_SOURCES), "
    "so the routes no request reached are not listed."
)


def refusal(snapshot: Snapshot) -> str | None:
    if not snapshot.journaled("http"):
        return UNRECORDED
    if "http" in snapshot.hidden:
        return "The http-exchanges panel is disabled, so the routes no request reached are not listed."
    if snapshot.clears:
        return (
            "The recording was cleared during this run, so declared routes absent from the remaining counts "
            "cannot be classified as not exercised."
        )
    if snapshot.dropped("http"):
        return (
            "The http source dropped completion events, so declared routes absent from its counts "
            "cannot be classified as not exercised."
        )
    if snapshot.status["evictedEvents"]:
        return (
            "The journal evicted events during this run, so declared routes cannot be classified as not exercised: "
            "this journal keeps no run-wide route counts."
        )
    return None


def of(declared: Sequence[RouteInfo], exercised: Collection[str]) -> list[str]:
    labels = {label.split(" (", 1)[0] for label in exercised}
    paths = {label.partition(" ")[2] for label in labels}
    missing: set[str] = set()
    for route in declared:
        if (
            not route.path.startswith("/")
            or "*" in route.path
            or ":path}" in route.path
            or route.handler.startswith(("fastapi.", "starlette."))
            or route.handler == "custom route"
            or not route.methods
            and route.path.endswith("/{path}")
        ):
            continue
        for method in route.methods or ("ANY",):
            method = method.strip().upper()
            if method == "WS":
                continue
            if method in {"", "ANY", "*"}:
                if route.path not in paths:
                    missing.add(f"ANY {route.path}")
            elif (label := f"{method} {route.path}") not in labels:
                missing.add(label)
    return sorted(missing)
