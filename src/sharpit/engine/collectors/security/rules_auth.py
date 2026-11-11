"""Authentication, authorization and CSRF rules (BootUI ``SecurityRules`` rows, plus SEC-FAPI-002/4/5)."""

from __future__ import annotations

from collections.abc import Callable

from sharpit.engine.collectors.security import (
    UNSAFE_METHODS,
    Inputs,
    SecurityRule,
    Violation,
    chain_has,
    route_label,
    rule,
    simple,
)
from sharpit.engine.collectors.security.rules_common import _production_only
from sharpit.engine.spi import SecuredRoute

_SECURITY = "https://fastapi.tiangolo.com/tutorial/security/"
_CSRF = "https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html"


def _required(route: SecuredRoute) -> list[str]:
    return [simple(s.type_name) for s in route.schemes if s.auto_error]


def _secured(route: SecuredRoute) -> bool:
    return bool(_required(route)) or route.unknown_dependency


def _api_routes(inputs: Inputs) -> list[SecuredRoute]:
    """Known route handlers (a mount row has no methods; an opaque row cannot be classified)."""
    return [r for r in inputs.model.routes if r.methods and not r.opaque]


def _unsafe(route: SecuredRoute) -> bool:
    return bool(UNSAFE_METHODS.intersection(route.methods))


def _csrf_protected(inputs: Inputs, route: SecuredRoute) -> bool:
    chains = inputs.model.chains
    stack = chains[route.chain].middleware if 0 <= route.chain < len(chains) else ()
    return any("csrf" in simple(m).lower() for m in stack)


def _without_https(scheme: str) -> Callable[[Inputs], list[Violation]]:
    def check(inputs: Inputs) -> list[Violation]:
        return [
            Violation(
                route_label(r),
                f"{route_label(r)} requires {scheme} and its middleware stack has no HTTPSRedirectMiddleware.",
            )
            for r in _api_routes(inputs)
            if scheme in _required(r) and not chain_has(inputs.model, r.chain, "HTTPSRedirectMiddleware")
        ]

    return _production_only(check)


def _unsecured_writes(inputs: Inputs) -> list[Violation]:
    routes = _api_routes(inputs)
    if not any(_secured(r) for r in routes):
        return []  # nothing is secured: SEC-AUTHZ-002's finding, not one per route
    return [
        Violation(route_label(r), f"{route_label(r)} changes state with no security dependency.")
        for r in routes
        if _unsafe(r) and not r.schemes and not _secured(r)  # an ordinary Depends (db session) guards nothing
    ]


def _blanket_permit_all(inputs: Inputs) -> list[Violation]:
    model = inputs.model
    routes = _api_routes(inputs)
    unknown = any(r.opaque for r in model.routes)  # an unreadable route may be secured: never claim blanket access
    if not routes or unknown or model.auth_backends or any(r.schemes or _secured(r) for r in routes):
        return []
    message = (
        f"None of the {len(routes)} routes requires a security scheme or a custom dependency, and no"
        " AuthenticationMiddleware is installed."
    )
    return [Violation("application", message)]


def _csrf(test: Callable[[Inputs, SecuredRoute], bool], why: str) -> Callable[[Inputs], list[Violation]]:
    def check(inputs: Inputs) -> list[Violation]:
        return [
            Violation(route_label(r), f"{route_label(r)} {why} and no CSRF middleware is on its stack.")
            for r in _api_routes(inputs)
            if _unsafe(r) and test(inputs, r) and not _csrf_protected(inputs, r)
        ]

    return check


def _cookie_credentials(inputs: Inputs, route: SecuredRoute) -> bool:
    return "APIKeyCookie" in _required(route) or chain_has(inputs.model, route.chain, "SessionMiddleware")


def _public_openapi(inputs: Inputs) -> list[Violation]:
    url = inputs.facts.openapi_url
    secured = [r for r in _api_routes(inputs) if _required(r)]
    if url is None or not secured:
        return []
    message = f"The OpenAPI schema at {url} is public while {len(secured)} route(s) require a security scheme."
    return [Violation(url, message)]


def _optional_only(inputs: Inputs) -> list[Violation]:
    return [
        Violation(route_label(r), f"{route_label(r)} has only optional security schemes (auto_error=False).")
        for r in _api_routes(inputs)
        if r.schemes and not _required(r) and not r.unknown_dependency  # an optional scheme always marks unchecked
    ]


def _mixed_schemes(inputs: Inputs) -> list[Violation]:
    found: list[Violation] = []
    for r in _api_routes(inputs):
        kinds = sorted(set(_required(r)))
        if len(kinds) > 1:
            found.append(Violation(route_label(r), f"{route_label(r)} requires {' and '.join(kinds)}."))
    return found


RULES: tuple[SecurityRule, ...] = (
    SecurityRule(
        rule(
            "SEC-AUTH-007",
            "HTTP Basic authentication should run only over HTTPS",
            "Authentication",
            "HIGH",
            "HTTP Basic sends the password with every request; without TLS it is readable on the wire.",
            "Serve the app over HTTPS only: add HTTPSRedirectMiddleware or enforce TLS at the proxy, and prefer"
            " token-based schemes.",
            "https://fastapi.tiangolo.com/advanced/security/http-basic-auth/",
        ),
        _without_https("HTTPBasic"),
    ),
    SecurityRule(
        rule(
            "SEC-AUTH-010",
            "Form login should run only over HTTPS",
            "Authentication",
            "HIGH",
            "OAuth2PasswordBearer routes accept a username and password form at the token URL; without TLS the"
            " credentials are readable on the wire.",
            "Serve the token endpoint over HTTPS only: add HTTPSRedirectMiddleware or enforce TLS at the proxy.",
            "https://fastapi.tiangolo.com/tutorial/security/simple-oauth2/",
        ),
        _without_https("OAuth2PasswordBearer"),
    ),
    SecurityRule(
        rule(
            "SEC-AUTHZ-001",
            "Every filter chain should enforce authorization",
            "Authorization",
            "INFO",
            "A state-changing route has no security dependency while other routes of the app require one. Public"
            " write endpoints are sometimes intended; this is a review prompt.",
            "Add the app's security dependency to the route (Depends/Security), or document why it is public.",
            _SECURITY,
        ),
        _unsecured_writes,
    ),
    SecurityRule(
        rule(
            "SEC-AUTHZ-002",
            "Avoid blanket permitAll authorization",
            "Authorization",
            "HIGH",
            "No route requires a security scheme or a custom dependency and no AuthenticationMiddleware is installed:"
            " every route answers anonymous requests.",
            "Protect non-public routes with a fastapi.security scheme dependency or an authentication middleware.",
            _SECURITY,
        ),
        _blanket_permit_all,
    ),
    SecurityRule(
        rule(
            "SEC-CSRF-001",
            "CSRF protection should stay on for browser-automatic credentials",
            "CSRF",
            "HIGH",
            "A state-changing route is authenticated by a cookie the browser sends automatically (APIKeyCookie or"
            " SessionMiddleware) and no CSRF middleware is on its stack.",
            "Add a CSRF middleware (for example starlette-csrf) or require a header-borne credential on unsafe"
            " methods.",
            _CSRF,
        ),
        _csrf(_cookie_credentials, "reads a browser-sent cookie credential"),
    ),
    SecurityRule(
        rule(
            "SEC-CSRF-002",
            "CSRF protection should stay on for HTTP Basic authentication",
            "CSRF",
            "MEDIUM",
            "Browsers resend cached HTTP Basic credentials automatically; a state-changing route behind HTTPBasic with"
            " no CSRF middleware can be triggered cross-site.",
            "Add a CSRF middleware or move browser clients to a token in a request header.",
            _CSRF,
        ),
        _csrf(lambda _i, r: "HTTPBasic" in _required(r), "requires HTTPBasic"),
    ),
    SecurityRule(
        rule(
            "SEC-FAPI-002",
            "API documentation should not be public while the API is secured",
            "Configuration",
            "LOW",
            "The OpenAPI schema (and the docs pages built on it) is served without authentication while routes"
            " require a security scheme: the API surface is described to anonymous callers.",
            "Set openapi_url=None outside development, or serve the docs behind the same security dependency.",
            "https://fastapi.tiangolo.com/how-to/conditional-openapi/",
        ),
        _public_openapi,
    ),
    SecurityRule(
        rule(
            "SEC-FAPI-004",
            "Optional security schemes should not be a route's only check",
            "Authorization",
            "INFO",
            "Every security scheme on the route has auto_error=False and nothing else guards it: an anonymous request"
            " reaches the endpoint with no credentials.",
            "Check the optional credential inside the endpoint, or use auto_error=True.",
            _SECURITY,
        ),
        _optional_only,
    ),
    SecurityRule(
        rule(
            "SEC-FAPI-005",
            "A route should not mix authentication schemes",
            "Authentication",
            "INFO",
            "The route requires schemes of more than one kind; each one must succeed, which is rarely intended and"
            " easy to misconfigure.",
            "Pick one authentication scheme per route, or combine them in one dependency that accepts either.",
            _SECURITY,
        ),
        _mixed_schemes,
    ),
)
