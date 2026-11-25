"""Declared routes no completed request reached (BootUI v2.5.0 NotExercisedRoutes)."""

from collections.abc import Callable, Collection, Sequence

from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.spi import RouteInfo

UNRECORDED = (
    "The runtime journal does not record the http source (SHARPIT_RUNTIME_JOURNAL_SOURCES), "
    "so the routes no request reached are not listed."
)
INVENTORY_UNAVAILABLE = (
    "The application's declared routes could not be read, so the routes no request reached are not listed: "
    "that does not mean every route was exercised."
)


def list_for(
    snapshot: Snapshot, declared: Callable[[], Sequence[RouteInfo] | None], limitations: list[str]
) -> list[str]:
    if reason := refusal(snapshot):
        limitations.append(reason)
        return []
    try:
        routes = declared()
        if routes is not None:
            unsupported = sum(application_route(r) and not r.exercise_supported for r in routes)
            if unsupported:
                noun = "route is" if unsupported == 1 else "routes are"
                limitations.append(
                    f"{unsupported} declared HTTP {noun} left out because its captured route template is not available."
                )
            exercised = {str(r["route"]) for r in snapshot.records.get("http", ()) if r.get("route")}
            return of(routes, exercised)
    except Exception:  # noqa: BLE001 - an inventory failure must never crash the host
        pass
    limitations.append(INVENTORY_UNAVAILABLE)
    return []


def refusal(snapshot: Snapshot) -> str | None:
    if not snapshot.journaled("http"):
        return UNRECORDED
    if "http" in snapshot.hidden:
        return "The http-exchanges panel is disabled, so the routes no request reached are not listed."
    if snapshot.http_suspended:
        return "HTTP recording was suspended during this run, so declared routes cannot be classified as not exercised."
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
        if not application_route(route) or not route.exercise_supported:
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


def application_route(route: RouteInfo) -> bool:
    return (
        route.path.startswith("/")
        and "*" not in route.path
        and ":path}" not in route.path
        and not route.handler.startswith(("fastapi.", "starlette."))
        and route.handler != "custom route"
        and (bool(route.methods) or not route.path.endswith("/{path}"))
        and route.methods != ("WS",)
    )
