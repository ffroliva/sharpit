"""Declared routes no completed request reached (BootUI v2.5.0 NotExercisedRoutes)."""

from collections.abc import Collection, Sequence

from sharpit.engine.spi import RouteInfo


def of(declared: Sequence[RouteInfo], exercised: Collection[str]) -> list[str]:
    labels = {label.split(" (", 1)[0] for label in exercised}
    paths = {label.partition(" ")[2] for label in labels}
    missing: set[str] = set()
    for route in declared:
        if route.handler.startswith(("fastapi.", "starlette.")):
            continue
        for method in route.methods or ("ANY",):
            method = method.strip().upper()
            if method in {"", "ANY", "*"}:
                if route.path not in paths:
                    missing.add(f"ANY {route.path}")
            elif (label := f"{method} {route.path}") not in labels:
                missing.add(label)
    return sorted(missing)
