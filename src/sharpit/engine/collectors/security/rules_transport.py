"""Session, CORS, OAuth2 endpoint and host/proxy rules over the middleware and scheme facts (never their values)."""

from __future__ import annotations

from sharpit.engine.collectors.security import Inputs, SecurityRule, Violation, rule

_CORS = "https://fastapi.tiangolo.com/tutorial/cors/"
_SESSIONS = "https://www.starlette.io/middleware/#sessionmiddleware"
_OAUTH = "https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/"
_MIDDLEWARE = "https://fastapi.tiangolo.com/advanced/middleware/"


def _none(_inputs: Inputs) -> list[Violation]:
    return []


RULES: tuple[SecurityRule, ...] = (
    SecurityRule(
        rule(
            "SEC-SESSION-002",
            "Session cookie should set the Secure flag",
            "Session management",
            "MEDIUM",
            "SessionMiddleware without https_only=True sends the signed session cookie over plain HTTP too.",
            "Pass https_only=True to SessionMiddleware when the app is served over HTTPS.",
            _SESSIONS,
        ),
        _none,
    ),
    SecurityRule(
        rule(
            "SEC-SESSION-004",
            "Review SameSite=None on the session cookie",
            "Session management",
            "LOW",
            'same_site="none" makes browsers send the session cookie on cross-site requests.',
            'Keep the default same_site="lax" (or "strict") unless a cross-site flow needs the session.',
            _SESSIONS,
        ),
        _none,
    ),
    SecurityRule(
        rule(
            "SEC-SESSION-008",
            "Remember-me signing key should be sufficiently long",
            "Session management",
            "MEDIUM",
            "The SessionMiddleware secret_key signs every session cookie; a key shorter than 32 characters is easier"
            " to brute-force. Only its length is read.",
            "Use a random secret of at least 32 characters, loaded from the environment or a secret store.",
            _SESSIONS,
        ),
        _none,
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
        _none,
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
        _none,
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
        _none,
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
        _none,
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
        _none,
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
        _none,
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
        _none,
    ),
)
