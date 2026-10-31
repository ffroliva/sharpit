"""The 20 ported REST API rules (port of BootUI ``RestApiRules`` heuristics and ``docs/REST-API-CHECKS.md`` names).

Rules read ``ApiRouteInfo`` metadata only. Spring/JAX-RS wording is rewritten for FastAPI; severities and categories
keep BootUI's calibration. sharpit adaptations: a "controller" is the endpoint's module, a handler is described as
``module:qualname [METHODS path]``, MAP-001 flags one route that serves GET together with a mutating method (FastAPI
has no method-less mapping), and name heuristics also split snake_case and kebab-case words.
"""

from __future__ import annotations

import collections.abc as abc
import re
import types
import typing
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from sharpit.engine.advisors.rules import RuleDefinition, RuleResult
from sharpit.engine.spi import ApiRouteInfo

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
}
RULE_IDS = frozenset(r.id for r in RULES)

# --- heuristics (RestApiRules constants) ----------------------------------------------------------------------------

_FRAMEWORK_MODULES = frozenset({"fastapi", "starlette", "sharpit"})
_MUTATING = ("POST", "PUT", "PATCH", "DELETE")
_VERBS = frozenset(
    [
        "get",
        "create",
        "update",
        "delete",
        "remove",
        "save",
        "add",
        "fetch",
        "insert",
        "modify",
        "post",
        "put",
        "patch",
        "read",
    ]
)
_VERB_STANDALONE = frozenset(
    ["get", "create", "update", "delete", "remove", "save", "add", "fetch", "insert", "modify"]
)
_CREATION_PREFIXES = frozenset(["create", "add", "save", "insert", "register", "new"])
_STATE_CHANGING_PREFIXES = frozenset(
    [
        "create",
        "update",
        "delete",
        "remove",
        "save",
        "add",
        "insert",
        "modify",
        "patch",
        "put",
        "post",
        "register",
        "edit",
    ]
)
_NON_MUTATING_PREFIXES = ("postprocess", "putaside", "patchversion")
_IRREGULAR_PLURALS = frozenset(
    [
        "people",
        "children",
        "men",
        "women",
        "media",
        "data",
        "criteria",
        "indices",
        "vertices",
        "feet",
        "teeth",
        "geese",
        "mice",
        "series",
        "species",
    ]
)
_UNCOUNTABLE = frozenset(
    [
        "history",
        "inventory",
        "staff",
        "info",
        "information",
        "search",
        "news",
        "status",
        "metadata",
        "feedback",
        "content",
        "equipment",
        "software",
        "hardware",
        "analytics",
        "reporting",
        "billing",
        "processing",
        "shipping",
        "access",
    ]
)
_NON_API_SEGMENTS = frozenset(
    [
        "health",
        "info",
        "ready",
        "readiness",
        "live",
        "liveness",
        "metrics",
        "prometheus",
        "error",
        "login",
        "logout",
        "oauth",
        "oauth2",
        "token",
        "docs",
        "redoc",
        "openapi.json",
        "swagger-ui",
        "swagger",
        "api-docs",
        "favicon.ico",
        "static",
    ]
)
_VERSION = re.compile(r"v\d+", re.IGNORECASE)
_DOUBLE_SLASH = re.compile(r"//")
_CATCH_ALL = re.compile(r"\{[^}]*:path\}")
_WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+")
_PAGING_PARAMS = frozenset({"limit", "offset", "page", "cursor", "size"})
_COLLECTIONS: tuple[object, ...] = (
    list,
    tuple,
    set,
    frozenset,
    abc.Sequence,
    abc.MutableSequence,
    abc.Set,
    abc.MutableSet,
    abc.Collection,
    abc.Iterable,
    abc.Iterator,
)
_UNTYPED: tuple[object, ...] = (Any, object, dict, abc.Mapping, abc.MutableMapping)
_NONE = type(None)
_MAX_TYPE_DEPTH = 8


def _is_framework(route: ApiRouteInfo) -> bool:
    return route.handler.partition(":")[0].partition(".")[0] in _FRAMEWORK_MODULES


def _describe(route: ApiRouteInfo, suffix: str | None = None) -> str:
    base = f"{route.handler} [{' '.join(route.methods)} {route.path}]"
    return f"{base} — {suffix}" if suffix else base


def _function(route: ApiRouteInfo) -> str:
    return route.handler.rpartition(":")[2].rpartition(".")[2]


def _words(name: str) -> list[str]:
    return [w.lower() for w in _WORDS.findall(name)]


def _first_word(name: str) -> str | None:
    words = _words(name)
    return words[0] if words else None


def _segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _is_variable(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _static(path: str) -> list[str]:
    return [s for s in _segments(path) if not _is_variable(s)]


def _unwrap(tp: object) -> object:
    """``Optional[X]``, ``X | None`` and ``Annotated[X, ...]`` -> ``X``."""
    for _ in range(_MAX_TYPE_DEPTH):
        origin = typing.get_origin(tp)
        if origin is typing.Annotated:
            tp = typing.get_args(tp)[0]
        elif origin is typing.Union or origin is types.UnionType:
            args = [a for a in typing.get_args(tp) if a is not _NONE]
            if len(args) != 1:
                return tp
            tp = args[0]
        else:
            return tp
    return tp


def _origin(tp: object) -> object:
    tp = _unwrap(tp)
    return typing.get_origin(tp) or tp


def _response_type(route: ApiRouteInfo) -> object | None:
    return route.response_model if route.response_model is not None else route.return_annotation


def _is_collection(route: ApiRouteInfo) -> bool:
    tp = _response_type(route)
    return tp is not None and any(_origin(tp) is c for c in _COLLECTIONS)


def _all_types(tp: object, depth: int = 0) -> Iterator[object]:
    yield tp
    if depth < _MAX_TYPE_DEPTH:
        for arg in typing.get_args(tp):
            yield from _all_types(arg, depth + 1)


def _persistence_class(route: ApiRouteInfo) -> type | None:
    for root in (route.response_model, route.return_annotation):
        for tp in _all_types(root):
            if isinstance(tp, type) and (hasattr(tp, "__table__") or hasattr(tp, "__mapper__")):
                return tp
    return None


def _has_body_type(route: ApiRouteInfo) -> bool:
    return route.response_model is not None or route.return_annotation not in (None, _NONE)


# --- rules (RestApiRules doEvaluate) --------------------------------------------------------------------------------

Check = Callable[[Sequence[ApiRouteInfo], Sequence[str]], list[str]]


def _each(predicate: Callable[[ApiRouteInfo], str | None]) -> Check:
    """One violation per route for which ``predicate`` returns a suffix (BootUI ``handlersMatching``)."""

    def check(routes: Sequence[ApiRouteInfo], _handlers: Sequence[str]) -> list[str]:
        out: list[str] = []
        for route in routes:
            suffix = predicate(route)
            if suffix is not None:
                out.append(_describe(route, suffix))
        return out

    return check


def _map001(route: ApiRouteInfo) -> str | None:
    mutating = [m for m in route.methods if m in _MUTATING]
    return f"GET combined with {', '.join(mutating)}" if "GET" in route.methods and mutating else None


def _map002(routes: Sequence[ApiRouteInfo], _handlers: Sequence[str]) -> list[str]:
    by_route: dict[tuple[str, str], list[str]] = {}
    for route in routes:
        for method in route.methods:
            by_route.setdefault((method, route.path), []).append(route.handler)
    return [
        f"{method} {path} with matching dispatch conditions handled by {', '.join(handlers)}"
        for (method, path), handlers in by_route.items()
        if len(handlers) > 1
    ]


def _map003(route: ApiRouteInfo) -> str | None:
    name = _function(route)
    if "GET" not in route.methods or name.replace("_", "").lower().startswith(_NON_MUTATING_PREFIXES):
        return None
    return "mutation-like name on GET" if _first_word(name) in _STATE_CHANGING_PREFIXES else None


def _map005(route: ApiRouteInfo) -> str | None:
    outside = re.sub(r"\{[^}]*\}", "", route.path)
    if _DOUBLE_SLASH.search(outside):
        return "doubled slash"
    return "trailing slash" if len(route.path) > 1 and route.path.endswith("/") else None


def _map007(route: ApiRouteInfo) -> str | None:
    methods = [m for m in route.methods if m in ("GET", "HEAD", "DELETE")]
    return f"request body on {', '.join(methods)}" if route.has_body and methods else None


def _map010(route: ApiRouteInfo) -> str | None:
    return "catch-all path parameter" if _CATCH_ALL.search(route.path) else None


def _map011(route: ApiRouteInfo) -> str | None:
    segments = _segments(route.path)
    depth = sum(1 for a, b in zip(segments, segments[1:], strict=False) if not _is_variable(a) and _is_variable(b))
    return f"{depth} levels of collection/{{id}} nesting" if depth > 3 else None


def _name001(route: ApiRouteInfo) -> str | None:
    for segment in _static(route.path):
        words = _words(segment)
        if segment.lower() in _VERB_STANDALONE or (len(words) > 1 and words[0] in _VERBS):
            return "verb in path"
    return None


def _name002(route: ApiRouteInfo) -> str | None:
    if "GET" not in route.methods or not _is_collection(route):
        return None
    static = [s for s in _static(route.path) if not _VERSION.fullmatch(s)]
    if not static:
        return None
    words = _words(static[-1])
    noun = words[-1] if words else ""
    if not noun.isalpha() or noun.endswith("s") or noun in _IRREGULAR_PLURALS or noun in _UNCOUNTABLE:
        return None
    return f"singular collection name '{static[-1]}'"


def _name003(route: ApiRouteInfo) -> str | None:
    for segment in _static(route.path):
        if segment != segment.lower() or "_" in segment:
            return f"segment '{segment}' is not lowercase kebab-case"
    return None


def _resp001(route: ApiRouteInfo) -> str | None:
    if "POST" not in route.methods or route.status_code is not None or route.dynamic_response:
        return None
    return (
        "creation-like POST with the default 200 status"
        if _first_word(_function(route)) in _CREATION_PREFIXES
        else None
    )


def _resp002(route: ApiRouteInfo) -> str | None:
    if "DELETE" not in route.methods or route.status_code is not None or route.dynamic_response:
        return None
    return None if _has_body_type(route) else "DELETE with the default 200 status and no response body"


def _resp006(route: ApiRouteInfo) -> str | None:
    if route.status_code != 204 or route.dynamic_response:
        return None
    return "204 declared with a content-capable return type" if _has_body_type(route) else None


def _dto001(route: ApiRouteInfo) -> str | None:
    cls = _persistence_class(route)
    return f"returns persistence class {cls.__name__}" if cls is not None else None


def _dto002(route: ApiRouteInfo) -> str | None:
    if route.dynamic_response or route.status_code in (204, 304):
        return None
    tp = _response_type(route)
    if tp is None:
        return "no response model or return annotation"
    return "untyped response body" if any(_origin(tp) is u for u in _UNTYPED) else None


def _page001(route: ApiRouteInfo) -> str | None:
    if "GET" not in route.methods or not _is_collection(route):
        return None
    if _PAGING_PARAMS & {p.lower() for p in route.query_params}:
        return None
    return "collection response without limit/offset/page/cursor parameters"


def _ver001(routes: Sequence[ApiRouteInfo], _handlers: Sequence[str]) -> list[str]:
    api = [r for r in routes if _segments(r.path) and _segments(r.path)[0].lower() not in _NON_API_SEGMENTS]
    unversioned = [r for r in api if not any(_VERSION.fullmatch(s) for s in _segments(r.path))]
    if not unversioned:
        return []
    if len(unversioned) == len(api):
        return [
            "No API version signal (no /vN path, version header/param, or versioned media type) was detected across"
            f" {len(api)} handler(s)."
        ]
    examples = ", ".join(_describe(r) for r in unversioned[:5])
    return [
        f"Versioning is applied inconsistently: {len(unversioned)} of {len(api)} API handler(s) have no version"
        f" signal while others do. Unversioned example(s): {examples}"
    ]


def _err001(routes: Sequence[ApiRouteInfo], handlers: Sequence[str]) -> list[str]:
    app_handlers = [h for h in handlers if h.partition(":")[0].partition(".")[0] not in _FRAMEWORK_MODULES]
    if not routes or app_handlers:
        return []
    return [
        "No application-wide exception handler was registered in app.exception_handlers for"
        f" {len(routes)} route handler(s)."
    ]


def _doc001(route: ApiRouteInfo) -> str | None:
    return None if (route.summary or "").strip() or (route.description or "").strip() else "no summary or description"


def _doc002(route: ApiRouteInfo) -> str | None:
    return None if route.tags else "no tags"


_CHECKS: dict[str, Check] = {
    "RAPI-MAP-001": _each(_map001),
    "RAPI-MAP-002": _map002,
    "RAPI-MAP-003": _each(_map003),
    "RAPI-MAP-005": _each(_map005),
    "RAPI-MAP-007": _each(_map007),
    "RAPI-MAP-010": _each(_map010),
    "RAPI-MAP-011": _each(_map011),
    "RAPI-NAME-001": _each(_name001),
    "RAPI-NAME-002": _each(_name002),
    "RAPI-NAME-003": _each(_name003),
    "RAPI-RESP-001": _each(_resp001),
    "RAPI-RESP-002": _each(_resp002),
    "RAPI-RESP-006": _each(_resp006),
    "RAPI-DTO-001": _each(_dto001),
    "RAPI-DTO-002": _each(_dto002),
    "RAPI-PAGE-001": _each(_page001),
    "RAPI-VER-001": _ver001,
    "RAPI-ERR-001": _err001,
    "RAPI-DOC-001": _each(_doc001),
    "RAPI-DOC-002": _each(_doc002),
}


def application_routes(routes: Sequence[ApiRouteInfo]) -> list[ApiRouteInfo]:
    """The host's own handlers: FastAPI's docs routes, Starlette apps and sharpit's routes are not reviewed."""
    return [r for r in routes if not _is_framework(r)]


def violations(routes: Sequence[ApiRouteInfo], exception_handlers: Sequence[str]) -> dict[str, list[str]]:
    """Every ported rule's violations, in ``RULES`` order. Pure: reads the given metadata only."""
    own = application_routes(routes)
    return {rule.id: _CHECKS[rule.id](own, exception_handlers) for rule in RULES}


def scan(routes: Sequence[ApiRouteInfo], exception_handlers: Sequence[str]) -> list[RuleResult]:
    found = violations(routes, exception_handlers)
    return [RuleResult.evaluate(rule, found[rule.id]) for rule in RULES]
