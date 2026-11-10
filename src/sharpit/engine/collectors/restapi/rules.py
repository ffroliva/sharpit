"""The REST API rule metadata and stable public evaluation API."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from sharpit.engine.advisors.rules import RuleDefinition, RuleResult
from sharpit.engine.collectors.restapi import (
    rules_dto,
    rules_errors_docs,
    rules_mapping,
    rules_naming,
    rules_pagination,
    rules_responses,
    rules_versioning,
)
from sharpit.engine.collectors.restapi.rules_common import Violation, shared_is_framework
from sharpit.engine.spi import ApiRouteInfo
from sharpit.engine.testsession.swallowed import swallowing_lines

ROUTING = "Routing & HTTP method mapping"
NAMING = "Naming & resource design"
RESPONSES = "Status codes & responses"
DTO = "DTO & payload contracts"
PAGINATION = "Pagination & collections"
VERSIONING = "Versioning & content negotiation"
ERRORS_DOCS = "Error handling & documentation"

REST_GUIDELINES = "https://www.rfc-editor.org/rfc/rfc9110.html"
CREATED_DOCS = "https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.2"
PROBLEM_DETAIL_DOCS = "https://www.rfc-editor.org/rfc/rfc9457.html"
_FASTAPI = "https://fastapi.tiangolo.com/tutorial/"

RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        "RAPI-MAP-001",
        "Use HTTP-method-specific mappings",
        ROUTING,
        "MEDIUM",
        "One route serves GET together with a state-changing method. The declaration does not establish whether a"
        " given call changes state.",
        "Split the route into one handler per HTTP method (@app.get, @app.post...).",
        _FASTAPI + "first-steps/",
    ),
    RuleDefinition(
        "RAPI-MAP-002",
        "No duplicate route mappings",
        ROUTING,
        "HIGH",
        "Two handlers declare the same HTTP method and complete path; only the first one registered is reachable."
        " This exact-path check is not a complete ambiguity analysis.",
        "Ensure each (HTTP method, path) combination is handled by exactly one function.",
        _FASTAPI + "path-params/",
    ),
    RuleDefinition(
        "RAPI-MAP-003",
        "Review mutation-like names on GET handlers",
        ROUTING,
        "LOW",
        "GET must be safe, but a create/update/delete/save-style function name is only a review signal, not proof of"
        " mutation. Crawlers and prefetchers may invoke GET automatically.",
        "Verify GET safety; if the operation requests a state change, use POST/PUT/PATCH/DELETE.",
        REST_GUIDELINES,
    ),
    RuleDefinition(
        "RAPI-MAP-005",
        "Review trailing and doubled slashes",
        ROUTING,
        "INFO",
        "Trailing or doubled slashes may differ from a project's URL convention. This is optional style; FastAPI"
        " redirects between trailing-slash variants by default.",
        "Review literal slash conventions without rewriting intentional paths.",
        _FASTAPI + "path-params/",
    ),
    RuleDefinition(
        "RAPI-MAP-007",
        "Review request entities on GET/HEAD/DELETE",
        ROUTING,
        "MEDIUM",
        "GET, HEAD and DELETE request content has no generally defined semantics in RFC 9110. Private agreements are"
        " possible, but intermediary and client interoperability needs review.",
        "Prefer query/path parameters or POST/PUT/PATCH unless a private request-content agreement is intentional.",
        REST_GUIDELINES,
    ),
    RuleDefinition(
        "RAPI-MAP-010",
        "Review catch-all REST mappings",
        ROUTING,
        "INFO",
        "A {name:path} catch-all parameter broadens the declared routing surface. It does not prove shadowing or a"
        " 200 response.",
        "Review catch-all intent and unmatched-path handling; generic forwarding may legitimately need it.",
        _FASTAPI + "path-params/#path-parameters-containing-paths",
    ),
    RuleDefinition(
        "RAPI-MAP-011",
        "Review deeply nested resource paths",
        ROUTING,
        "INFO",
        "More than 3 collection/{id} pairs exceeds this advisor's optional readability threshold, not an HTTP or URI"
        " limit.",
        "Flatten deep nesting by exposing a top-level resource or reducing to at most 3 collection/{id} pairs in one"
        " path.",
        REST_GUIDELINES,
    ),
    RuleDefinition(
        "RAPI-NAME-001",
        "Consider noun-oriented resource paths",
        NAMING,
        "INFO",
        "Verb-like paths may duplicate the HTTP method under a noun-oriented URL convention. This is optional design"
        " guidance; action endpoints can be legitimate.",
        "Consider resource nouns (/users, /orders) where they fit the API's design.",
        REST_GUIDELINES,
    ),
    RuleDefinition(
        "RAPI-NAME-002",
        "Consider plural collection names",
        NAMING,
        "INFO",
        "An English-language spelling heuristic suggests a singular path for a collection return declaration. It does"
        " not establish runtime resource cardinality or an HTTP requirement.",
        "Consider plural collection names if that matches the project's language and naming convention.",
        REST_GUIDELINES,
    ),
    RuleDefinition(
        "RAPI-NAME-003",
        "Consider lowercase kebab-case paths",
        NAMING,
        "INFO",
        "camelCase, snake_case or uppercase segments differ from an optional lowercase kebab-case convention."
        " Case-sensitive URI paths are valid.",
        "Consider lowercase kebab-case (/order-items) when choosing a consistent project convention.",
        REST_GUIDELINES,
    ),
    RuleDefinition(
        "RAPI-RESP-001",
        "Review the default status of creation-like POST handlers",
        RESPONSES,
        "LOW",
        "A creation-like POST name with no declared status suggests reviewing the success status. The name does not"
        " prove creation, and runtime response behavior is not observed.",
        "For completed creation consider status_code=201; asynchronous acceptance may use 202. A 201 identifies the"
        " resource through Location when present, otherwise through the target URI.",
        CREATED_DOCS,
    ),
    RuleDefinition(
        "RAPI-RESP-002",
        "Review default empty DELETE responses",
        RESPONSES,
        "LOW",
        "A DELETE with no response body and no declared status uses the default 200. Review whether 204 more precisely"
        " describes completed deletion; declared statuses are preserved.",
        "Declare status_code=204 on DELETE handlers that return no body.",
        _FASTAPI + "response-status-code/",
    ),
    RuleDefinition(
        "RAPI-RESP-006",
        "204 declarations must not promise content",
        RESPONSES,
        "HIGH",
        "204 forbids response content. A content-capable return annotation alongside status_code=204 deserves review,"
        " but does not prove that content is transmitted.",
        "Annotate 204 handlers with -> None (or return a Response), or use 200 OK when a body is required.",
        REST_GUIDELINES,
    ),
    RuleDefinition(  # BootUI 2.2.0
        "RAPI-RESP-011",
        "Map an empty Optional read to an explicit status",
        RESPONSES,
        "LOW",
        "A GET handler whose declared response is Optional (X | None) with the default status serializes a missing"
        " resource as 200 with a null body instead of a not-found status.",
        "Raise HTTPException(status_code=404) when the resource is absent and declare the non-Optional type.",
        _FASTAPI + "handling-errors/",
    ),
    RuleDefinition(
        "RAPI-DTO-001",
        "Avoid persistence entities in responses",
        DTO,
        "HIGH",
        "Returning a mapped database class (an SQLAlchemy model or SQLModel table) couples the API to the persistence"
        " model and can leak internal fields or trigger lazy loads during serialization.",
        "Return a separate response model and map from the database class in the handler or service.",
        _FASTAPI + "response-model/",
    ),
    RuleDefinition(
        "RAPI-DTO-002",
        "Prefer informative response body types",
        DTO,
        "LOW",
        "A missing return type, Any, object or dict limits schema inference from the signature. Dynamic objects are"
        " valid and can be documented through explicit schemas.",
        "Prefer a typed response model for inference, or explicitly document the dynamic response schema.",
        _FASTAPI + "response-model/",
    ),
    RuleDefinition(
        "RAPI-PAGE-001",
        "Review collection reads without visible pagination",
        PAGINATION,
        "LOW",
        "A collection return without visible pagination input warrants a bounded-result review. The signature does"
        " not establish database load, response size or internal limits.",
        "Consider limit/offset, page or cursor query parameters, or document a fixed bound.",
        _FASTAPI + "query-params/",
    ),
    RuleDefinition(
        "RAPI-VER-001",
        "Review absent or uneven version signals",
        VERSIONING,
        "INFO",
        "No /vN path segment was found, or only some handlers are versioned, which makes breaking changes hard to roll"
        " out consistently.",
        "Review the API's compatibility policy; versioning is optional. If needed, choose a documented path, header,"
        " query or media-type strategy.",
        _FASTAPI + "bigger-applications/",
    ),
    RuleDefinition(
        "RAPI-ERR-001",
        "Review application-wide exception handling declarations",
        ERRORS_DOCS,
        "INFO",
        "No application exception handler is registered beyond FastAPI's defaults. Framework defaults and local"
        " handling may already provide an intentional error policy.",
        "Review the existing error policy before adding an application-wide @app.exception_handler.",
        PROBLEM_DETAIL_DOCS,
    ),
    RuleDefinition(
        "RAPI-DOC-001",
        "Consider explicit operation documentation",
        ERRORS_DOCS,
        "INFO",
        "Some handlers have no summary, description or docstring. Generated or static documentation may already"
        " describe them.",
        "Consider a summary or docstring where it adds useful information beyond the generated documentation.",
        _FASTAPI + "path-operation-configuration/",
    ),
    RuleDefinition(
        "RAPI-DOC-002",
        "Consider explicit operation grouping",
        ERRORS_DOCS,
        "INFO",
        "Some handlers have no tags, so the generated OpenAPI document groups them under 'default'.",
        "Consider tags on the route or its APIRouter when they improve the OpenAPI grouping.",
        _FASTAPI + "path-operation-configuration/#tags",
    ),
)

_SPRING = "Reads Spring or JAX-RS annotation metadata that FastAPI routes do not have."
_DEEP = "Needs body, schema or error-contract analysis beyond declared route metadata; not ported to sharpit."
SKIPPED_RULES: Mapping[str, str] = {
    "RAPI-MAP-004": "FastAPI has no class-level base path; APIRouter prefixes are already applied to each path.",
    "RAPI-MAP-006": _SPRING,
    "RAPI-MAP-008": _DEEP,
    "RAPI-MAP-009": "FastAPI refuses duplicate path parameter names when the route is built.",
    "RAPI-NAME-004": _DEEP,
    "RAPI-RESP-003": _SPRING,
    "RAPI-RESP-004": _DEEP,
    "RAPI-RESP-005": _DEEP,
    "RAPI-RESP-007": _SPRING,
    "RAPI-RESP-008": _DEEP,
    "RAPI-RESP-009": "Starlette serves HEAD from the GET handler; there are no dedicated HEAD handlers to review.",
    "RAPI-VALID-001": "Pydantic validates nested request models by default.",
    "RAPI-VALID-002": _DEEP,
    "RAPI-VALID-003": _SPRING,
    "RAPI-VALID-004": _DEEP,
    "RAPI-VALID-005": _DEEP,
    "RAPI-DTO-004": _DEEP,
    "RAPI-DTO-005": "A Java type rule (java.time); not applicable to Python.",
    "RAPI-PAGE-002": _SPRING,
    "RAPI-PAGE-003": _DEEP,
    "RAPI-VER-002": _SPRING,
    "RAPI-VER-003": _SPRING,
    "RAPI-VER-004": _DEEP,
    "RAPI-VER-005": _SPRING,
    "RAPI-VER-006": _DEEP,
    "RAPI-ERR-002": "A Java throws-declaration rule; Python has no checked exceptions.",
    "RAPI-ERR-003": _SPRING,
    "RAPI-ERR-004": _DEEP,
    "RAPI-ERR-005": _DEEP,
    "RAPI-ERR-006": _SPRING,
    "RAPI-ERR-007": _DEEP,
    "RAPI-ERR-008": _DEEP,
    "RAPI-ERR-009": _DEEP,
    "RAPI-ERR-010": _DEEP,
    "RAPI-ERR-011": "Needs exception-handler bodies; sharpit never calls or decompiles handlers.",
    "RAPI-DOC-003": _DEEP,
    # BootUI 2.2.0
    "RAPI-RESP-010": "Spring's @ResponseStatus reason discards the body; FastAPI has no such attribute.",
    "RAPI-VALID-006": "FastAPI embeds several body parameters in one JSON object; a second body binds normally.",
    "RAPI-VER-007": "FastAPI routes declare no consumes condition, so a bodyless route never answers 415 for a missing"
    " Content-Type (a body on GET/HEAD/DELETE is RAPI-MAP-007).",
}
RULE_IDS = frozenset(r.id for r in RULES)

# --- heuristics (RestApiRules constants) ----------------------------------------------------------------------------


_CHECKS = {
    **rules_mapping.CHECKS,
    **rules_naming.CHECKS,
    **rules_responses.CHECKS,
    **rules_dto.CHECKS,
    **rules_pagination.CHECKS,
    **rules_versioning.CHECKS,
    **rules_errors_docs.CHECKS,
}


def application_routes(routes: Sequence[ApiRouteInfo]) -> list[ApiRouteInfo]:
    """The host's own handlers: FastAPI's docs, Starlette apps and sharpit's routes are not reviewed."""
    return [route for route in routes if not shared_is_framework(route)]


def evaluate(
    routes: Sequence[ApiRouteInfo], exception_handlers: Sequence[str]
) -> tuple[dict[str, list[Violation]], set[str]]:
    """Every ported rule's violations, in ``RULES`` order, and ids of rules that raised."""
    own = application_routes(routes)
    found: dict[str, list[Violation]] = {}
    errored: set[str] = set()
    for rule in RULES:
        try:
            found[rule.id] = _CHECKS[rule.id](own, exception_handlers)
        except Exception:  # a broken model fails its rule, never the scan
            found[rule.id] = []
            errored.add(rule.id)
    return found, errored


def violations(routes: Sequence[ApiRouteInfo], exception_handlers: Sequence[str]) -> dict[str, list[str]]:
    """Every ported rule's violations in ``RULES`` order."""
    return {rule_id: [v.message for v in items] for rule_id, items in evaluate(routes, exception_handlers)[0].items()}


def scan(routes: Sequence[ApiRouteInfo], exception_handlers: Sequence[str]) -> list[RuleResult]:
    found = violations(routes, exception_handlers)
    return [RuleResult.evaluate(rule, found[rule.id]) for rule in RULES]


FASTAPI_ERR_001 = RuleDefinition(
    "FASTAPI-ERR-001",
    "Do not swallow exceptions in route handler modules",
    ERRORS_DOCS,
    "MEDIUM",
    "An except clause that catches Exception, BaseException or everything, and neither re-raises nor logs, hides"
    " programming errors (a misspelt attribute becomes a wrong value served with HTTP 200).",
    "Catch the specific exceptions you expect, or log/re-raise in the broad handler.",
    "https://docs.python.org/3/tutorial/errors.html#handling-exceptions",
)


def swallowed_handler_violations(routes: Sequence[ApiRouteInfo]) -> list[Violation]:
    """Broad swallowing handlers in the modules that define the application's route handlers: files are read and
    parsed, never imported or called."""
    found: list[Violation] = []
    modules = dict.fromkeys(r.handler.partition(":")[0] for r in application_routes(routes))
    for name in modules:
        filename = getattr(sys.modules.get(name), "__file__", None)
        if not isinstance(filename, str) or not filename.endswith(".py"):
            continue
        try:
            lines = swallowing_lines(Path(filename).read_text("utf-8"))
        except (OSError, SyntaxError, ValueError):  # unreadable or not parseable: nothing to say about it
            continue
        found.extend(
            Violation(f"{name}:{line}", f"{name}:{line} catches broadly and neither re-raises nor logs")
            for line in lines
        )
    return found
