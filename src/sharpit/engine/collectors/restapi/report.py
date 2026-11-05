"""``RestApiReport`` texts (port of BootUI ``RestApiScanner`` messages); the shape is built by the advisor scan core."""

from __future__ import annotations

from collections.abc import Sequence

ANALYZER = "sharpit rest-api"
DISCLAIMER = (
    "Heuristic, project-agnostic REST API design rules run against the host application's own route handlers only."
    " These checks complement, but do not replace, an API design review or contract testing. Security concerns"
    " (CORS, authentication, authorization) are out of scope."
)
NOT_SCANNED_MESSAGE = (
    "REST API rules have not run yet. Click Run REST API checks to analyse the application's route handlers."
)
NO_ROUTES_MESSAGE = "No route handlers were found in the host application."


def scanned_message(modules: int, handlers: int) -> str:
    return (
        f"REST API rules completed against {modules} module(s) and {handlers} route handler(s) in the host application."
    )


def incomplete_message(limitations: Sequence[str]) -> str:
    return (
        f"REST API analysis is incomplete: {len(limitations)} part(s) of the application could not be inspected."
        " Reliable findings are retained; missing findings do not establish a clean API."
    )
