"""Declared routes no completed request reached (BootUI v2.5.0 NotExercisedRoutes)."""

import functools
import re
from collections.abc import Callable, Collection, Sequence

from sharpit.engine.capture.journal import FAILED, REENTRANT
from sharpit.engine.capture.securitylogs import CAPTURE_UNAVAILABLE_REASON
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
    snapshot: Snapshot,
    declared: Callable[[], Sequence[RouteInfo] | None],
    limitations: list[str],
    *,
    metadata_only: bool = False,
) -> list[str]:
    if reason := refusal(snapshot):
        limitations.append(reason)
        return []
    if snapshot.ids_withheld or metadata_only:
        limitations.append(
            "Request ids are withheld at METADATA_ONLY exposure, so declared routes cannot be classified as "
            "not exercised (SHARPIT_EXPOSE_VALUES)."
        )
        return []
    try:
        routes = declared()
    except Exception:  # noqa: BLE001 - an inventory failure must never crash the host
        routes = None
    if routes is None:
        limitations.append(INVENTORY_UNAVAILABLE)
        return []
    unsupported = sum(application_route(r) and not r.exercise_supported for r in routes)
    if unsupported:
        noun = "route is" if unsupported == 1 else "routes are"
        limitations.append(
            f"{unsupported} declared HTTP {noun} left out because its captured route template is not available."
        )
    if any(_unmatched_declared(r, routes) for r in snapshot.records.get("http", ())):
        limitations.append(
            "Some completed HTTP requests have no captured route template, so declared routes "
            "cannot be classified as not exercised."
        )
        return []
    # a template-less label is the request path, not a declaration (``/a/`` redirected is labelled ``/a``)
    exercised = {str(r["route"]) for r in snapshot.records.get("http", ()) if r.get("route") and _templated(r)}
    if any("******" in label for label in exercised):
        limitations.append(
            "Some captured route labels were masked and could not be matched to declarations, so "
            "routes listed as not exercised may have been reached."
        )
    return of(routes, exercised)


def refusal(snapshot: Snapshot) -> str | None:
    if "http" in snapshot.unarmed:  # enabled, but a too-late install added no capture middleware
        return f"{CAPTURE_UNAVAILABLE_REASON}, so the routes no request reached are not listed."
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
    if key := next((k for k in (FAILED, REENTRANT) if snapshot.dropped(k)), None):
        return (
            f"The journal dropped events of an unknown source ({key}), so declared routes "
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


def _templated(record: dict[str, object]) -> bool:
    if "routeTemplate" in record:
        return record["routeTemplate"] is not None
    return record.get("status") != 404


def _unmatched_declared(record: dict[str, object], declared: Sequence[RouteInfo]) -> bool:
    """A completed request with no captured template whose path a listed route could have answered (an included
    router's prefix lost at capture). A masked path cannot be matched, so it counts; other traffic (a CORS preflight,
    a static file, a redirect, a plain Starlette route) is ignored, as an unmatched 404 is."""
    if "routeTemplate" not in record or record["routeTemplate"] is not None or record.get("status") == 404:
        return False
    path, method = record.get("path"), str(record.get("method") or "").upper()
    if not isinstance(path, str) or "******" in path:
        return True
    return any(
        application_route(r)
        and r.exercise_supported
        and _answers(r, method)
        and _template_regex(r.path).fullmatch(path)
        for r in declared
    )


def _answers(route: RouteInfo, method: str) -> bool:
    methods = {m.strip().upper() for m in route.methods} or {"ANY"}
    return method in methods or not methods.isdisjoint({"ANY", "*", ""})


@functools.lru_cache(maxsize=1024)  # templates come from the host's code, never from a request
def _template_regex(template: str) -> re.Pattern[str]:
    # a parameter matches any one segment, looser than its converter: a doubtful match refuses, never lists
    parts = re.split(r"\{[^}]*\}", template)
    return re.compile("[^/]+".join(re.escape(p) for p in parts))


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
