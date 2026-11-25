"""Declared routes no completed request reached (BootUI v2.5.0 NotExercisedRoutes)."""

from collections.abc import Collection, Sequence

from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.spi import RouteInfo

UNRECORDED = (
    "The runtime journal does not record the http source (SHARPIT_RUNTIME_JOURNAL_SOURCES), "
    "so the routes no request reached are not listed."
)


def refusal(snapshot: Snapshot) -> str | None:
    return UNRECORDED if not snapshot.journaled("http") else None


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
