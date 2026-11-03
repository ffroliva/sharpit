"""Application rules over app source and the app object's own attributes: lifecycle, error handling, settings."""

from __future__ import annotations

from collections.abc import Sequence

from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.appsource import SourceIndex
from sharpit.engine.collectors.fastapi_advisor.handlers import Handler, Hit

ON_EVENT = RuleDefinition(
    "FASTAPI-EVT-001",
    "Deprecated on_event startup and shutdown handlers",
    "Configuration",
    "LOW",
    "on_event / add_event_handler startup and shutdown hooks are deprecated in favour of a lifespan context.",
    "Move startup and shutdown work into a lifespan async context manager passed to FastAPI(lifespan=...).",
    "https://fastapi.tiangolo.com/advanced/events/",
)
BROAD_EXCEPT = RuleDefinition(
    "FASTAPI-EXC-001",
    "Broad except swallows errors in an endpoint",
    "Web and HTTP",
    "MEDIUM",
    "An endpoint catches Exception (or everything) and neither logs, re-raises nor returns an error: the client "
    "sees success and the failure leaves no trace.",
    "Catch the specific exceptions you expect, log the rest, or raise HTTPException.",
    "https://fastapi.tiangolo.com/tutorial/handling-errors/",
)
DEBUG = RuleDefinition(
    "SPRING-WEB-004",
    "Review configured fallback error details",
    "Web and HTTP",
    "MEDIUM",
    "FastAPI(debug=True) returns tracebacks to the client on an unhandled error.",
    "Leave debug off outside local development.",
    "https://www.starlette.io/applications/",
)
DEFAULT_TITLE = RuleDefinition(
    "SPRING-CONFIG-004",
    "Consider a stable application name",
    "Configuration",
    "INFO",
    "The application keeps FastAPI's default title, so its OpenAPI document and docs page name no service.",
    "Pass title= to FastAPI().",
    "https://fastapi.tiangolo.com/tutorial/metadata/",
)
RULES = (ON_EVENT, BROAD_EXCEPT, DEBUG, DEFAULT_TITLE)


def on_event(index: SourceIndex) -> list[Hit]:
    return []


def broad_except(handlers: Sequence[Handler]) -> list[Hit]:
    return []


def debug(app: object) -> list[Hit]:
    return []


def default_title(app: object) -> list[Hit]:
    return []
