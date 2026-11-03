"""Authentication, authorization and CSRF rules (BootUI ``SecurityRules`` rows, plus SEC-FAPI-002/4/5)."""

from __future__ import annotations

from sharpit.engine.collectors.security import Inputs, SecurityRule, Violation, rule

_SECURITY = "https://fastapi.tiangolo.com/tutorial/security/"
_CSRF = "https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html"


def _none(_inputs: Inputs) -> list[Violation]:
    return []


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
        _none,
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
        _none,
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
        _none,
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
        _none,
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
        _none,
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
        _none,
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
        _none,
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
        _none,
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
        _none,
    ),
)
