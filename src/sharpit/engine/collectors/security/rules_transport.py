"""Session, CORS, OAuth2 endpoint and host/proxy rules over the middleware and scheme facts (never their values)."""

from __future__ import annotations

from collections.abc import Callable

from sharpit.engine.collectors.security import Inputs, SecurityRule, Violation, rule, simple
from sharpit.engine.collectors.security.rules_common import _production_only
from sharpit.engine.spi import MiddlewareFacts

_SESSION_MANAGEMENT = "Session management"
_CORS = "https://fastapi.tiangolo.com/tutorial/cors/"
_SESSIONS = "https://www.starlette.io/middleware/#sessionmiddleware"
_OAUTH = "https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/"
_MIDDLEWARE = "https://fastapi.tiangolo.com/advanced/middleware/"


def _of(inputs: Inputs, kind: str) -> list[MiddlewareFacts]:
    return [m for m in inputs.facts.middleware if simple(m.name) == kind]


def _at(m: MiddlewareFacts, kind: str, message: str) -> Violation:
    """The violation for one middleware; a mounted app's names its mount in the target and the message."""
    if m.mount is None:
        return Violation(kind, message)
    return Violation(f"{kind} at {m.mount}", message.replace(kind, f"{kind} on the app mounted at {m.mount}", 1))


def _flagged(kind: str, test: Callable[[tuple[str, ...]], bool], message: str) -> Callable[[Inputs], list[Violation]]:
    """One violation per ``kind`` middleware whose option facts pass ``test``; the message names facts, not values."""

    def check(inputs: Inputs) -> list[Violation]:
        return [_at(m, kind, message) for m in _of(inputs, kind) if test(m.flags)]

    return check


_session_insecure = _production_only(
    _flagged(
        "SessionMiddleware",
        lambda f: "https_only" not in f,
        "SessionMiddleware sends the session cookie without the Secure flag (https_only is off).",
    )
)


_session_same_site = _flagged(
    "SessionMiddleware",
    lambda f: "same_site_none" in f,
    'SessionMiddleware sets SameSite=None on the session cookie (same_site="none").',
)
_session_short_secret = _flagged(
    "SessionMiddleware",
    lambda f: "short_secret" in f,
    "SessionMiddleware signs sessions with a secret_key shorter than 32 characters.",
)
_cors_wildcard = _flagged(
    "CORSMiddleware",
    lambda f: "any_origin" in f and "credentials" not in f,
    'CORSMiddleware allows any origin ("*").',
)
_cors_credentials = _flagged(
    "CORSMiddleware",
    lambda f: "any_origin" in f and "credentials" in f,
    'CORSMiddleware allows any origin ("*") with allow_credentials=True; the request Origin is reflected.',
)


def _cors_broad(inputs: Inputs) -> list[Violation]:
    found: list[Violation] = []
    for m in _of(inputs, "CORSMiddleware"):
        if "broad_origin_regex" in m.flags:
            extra = " with allow_credentials=True" if "credentials" in m.flags else ""
            found.append(_at(m, "CORSMiddleware", f"CORSMiddleware allow_origin_regex matches any host{extra}."))
    return found


def _insecure_urls(fields: tuple[str, ...], kind: str | None) -> Callable[[Inputs], list[Violation]]:
    def check(inputs: Inputs) -> list[Violation]:
        return [
            Violation(
                f"{simple(u.scheme)} {u.field}", f"{simple(u.scheme)} declares an http:// {u.field} to a remote host."
            )
            for u in inputs.facts.scheme_urls
            if u.insecure and u.field in fields and (kind is None or simple(u.scheme) == kind)
        ]

    return _production_only(check)


def _host_header(inputs: Inputs) -> list[Violation]:
    trusted = _of(inputs, "TrustedHostMiddleware")
    if not any(m.mount is None for m in trusted):  # a mounted app's TrustedHostMiddleware does not cover the root
        return [Violation("ASGI middleware stack", "No TrustedHostMiddleware: any Host header is accepted.")]
    message = 'TrustedHostMiddleware allows any host (allowed_hosts includes "*").'
    return [_at(m, "TrustedHostMiddleware", message) for m in trusted if "any_host" in m.flags]


_proxy_any = _flagged(
    "ProxyHeadersMiddleware",
    lambda f: "trust_any_proxy" in f,
    'ProxyHeadersMiddleware trusts forwarded headers from any client (trusted_hosts="*").',
)


RULES: tuple[SecurityRule, ...] = (
    SecurityRule(
        rule(
            "SEC-SESSION-002",
            "Session cookie should set the Secure flag",
            _SESSION_MANAGEMENT,
            "MEDIUM",
            "SessionMiddleware without https_only=True sends the signed session cookie over plain HTTP too.",
            "Pass https_only=True to SessionMiddleware when the app is served over HTTPS.",
            _SESSIONS,
        ),
        _session_insecure,
    ),
    SecurityRule(
        rule(
            "SEC-SESSION-004",
            "Review SameSite=None on the session cookie",
            _SESSION_MANAGEMENT,
            "LOW",
            'same_site="none" makes browsers send the session cookie on cross-site requests.',
            'Keep the default same_site="lax" (or "strict") unless a cross-site flow needs the session.',
            _SESSIONS,
        ),
        _session_same_site,
    ),
    SecurityRule(
        rule(
            "SEC-SESSION-008",
            "Remember-me signing key should be sufficiently long",
            _SESSION_MANAGEMENT,
            "MEDIUM",
            "The SessionMiddleware secret_key signs every session cookie; a key shorter than 32 characters is easier"
            " to brute-force. Only its length is read.",
            "Use a random secret of at least 32 characters, loaded from the environment or a secret store.",
            _SESSIONS,
        ),
        _session_short_secret,
    ),
    SecurityRule(
        rule(
            "SEC-CORS-001",
            "CORS should not allow all origins",
            "CORS",
            "LOW",
            'CORSMiddleware allows any origin ("*") without credentials. This can be intentional for public data;'
            " credentialed cases belong to SEC-CORS-002.",
            'List the exact trusted origins in allow_origins instead of "*".',
            _CORS,
        ),
        _cors_wildcard,
    ),
    SecurityRule(
        rule(
            "SEC-CORS-002",
            "CORS must not combine wildcard origins with credentials",
            "CORS",
            "HIGH",
            'With allow_origins=["*"] and allow_credentials=True, Starlette reflects the request Origin: any site'
            " can make credentialed requests and read the responses.",
            "Never pair allow_credentials=True with a wildcard origin; list explicit origins.",
            _CORS,
        ),
        _cors_credentials,
    ),
    SecurityRule(
        rule(
            "SEC-CORS-006",
            "CORS should not allow broad origin patterns",
            "CORS",
            "LOW",
            "allow_origin_regex matches arbitrary hosts, which is a wildcard origin in disguise (worse with"
            " allow_credentials=True).",
            "Anchor the pattern to the trusted domains only.",
            _CORS,
        ),
        _cors_broad,
    ),
    SecurityRule(
        rule(
            "SEC-OAUTH-004",
            "JWT issuer and JWK endpoints should use HTTPS",
            "OAuth2 / JWT",
            "HIGH",
            "The OpenIdConnect scheme's discovery URL is plain HTTP to a non-loopback host: issuer metadata and keys"
            " can be tampered with in transit.",
            "Use an https:// openIdConnectUrl.",
            "https://fastapi.tiangolo.com/reference/security/#fastapi.security.OpenIdConnect",
        ),
        _insecure_urls(("openIdConnectUrl",), "OpenIdConnect"),
    ),
    SecurityRule(
        rule(
            "SEC-OAUTH-006",
            "OAuth2 client provider endpoints must use HTTPS",
            "OAuth2 / JWT",
            "HIGH",
            "An OAuth2 scheme declares an authorization, token or refresh URL over plain HTTP to a non-loopback host:"
            " codes and tokens travel in clear text.",
            "Use https:// for every OAuth2 flow URL.",
            _OAUTH,
        ),
        _insecure_urls(("authorizationUrl", "tokenUrl", "refreshUrl"), None),
    ),
    SecurityRule(
        rule(
            "SEC-FAPI-001",
            "Host header should be restricted to known hosts",
            "Transport and headers",
            "MEDIUM",
            'Without TrustedHostMiddleware (or with allowed_hosts=["*"]) any Host header is accepted, which enables'
            " host-header injection in generated URLs and cache poisoning.",
            "Add TrustedHostMiddleware with the exact host names the app serves.",
            _MIDDLEWARE,
        ),
        _host_header,
    ),
    SecurityRule(
        rule(
            "SEC-FAPI-003",
            "Proxy headers should be trusted only from known proxies",
            "Transport and headers",
            "MEDIUM",
            'ProxyHeadersMiddleware with trusted_hosts="*" lets any client set X-Forwarded-For and X-Forwarded-Proto,'
            " spoofing its address and the request scheme.",
            "Pass the proxy's address in trusted_hosts (or uvicorn --forwarded-allow-ips).",
            "https://www.uvicorn.org/deployment/#proxies-and-forwarded-headers",
        ),
        _proxy_any,
    ),
)
