"""``fastapi-security`` DTO assembly and rule classification (engine only; the adapter builds the model)."""

from __future__ import annotations

import pytest

from sharpit.engine.collectors.appsecurity import classify, endpoints_report, explain, security_report
from sharpit.engine.spi import SecuredRoute, SecurityChain, SecurityModel, SecurityScheme

BEARER = "fastapi.security.oauth2.OAuth2PasswordBearer"
API_KEY = "fastapi.security.api_key.APIKeyHeader"
APP_CHAIN = SecurityChain(None, ("starlette.middleware.cors.CORSMiddleware",))


def _model(*routes: SecuredRoute, chains: tuple[SecurityChain, ...] = (APP_CHAIN,), backends=()) -> SecurityModel:
    return SecurityModel(True, chains, tuple(backends), routes, ())


def _route(*schemes: SecurityScheme, unknown: bool = False, path: str = "/items", methods=("GET",)) -> SecuredRoute:
    return SecuredRoute(methods, path, "app.main:items", schemes, unknown)


@pytest.mark.parametrize(
    ("schemes", "expected"),
    [
        ((), ("unsecured", False, [], False)),
        ((SecurityScheme(BEARER, True, ()),), ("authenticated", True, [], False)),
        ((SecurityScheme(BEARER, False, ()),), ("permitAll", False, [], False)),
        ((SecurityScheme(BEARER, True, ("write", "admin")),), ("hasAuthority", True, ["admin", "write"], False)),
        ((SecurityScheme(BEARER, False, ("admin",)),), ("permitAll", False, [], False)),
        ((SecurityScheme(BEARER, False, ()), SecurityScheme(API_KEY, True, ())), ("authenticated", True, [], False)),
    ],
    ids=["none", "required", "optional", "scopes", "optional-with-scopes", "optional-plus-required"],
)
def test_rule_classification_table(schemes: tuple[SecurityScheme, ...], expected: tuple[object, ...]):
    assert classify(_route(*schemes)) == expected


def test_single_chain_lists_middleware_outermost_first():
    # ported: SpringSecurityControllerTests.singleChainFiltersListedBySimpleClassName
    chain = SecurityChain(
        None,
        (
            "starlette.middleware.trustedhost.TrustedHostMiddleware",
            "starlette.middleware.cors.CORSMiddleware",
            "starlette.middleware.sessions.SessionMiddleware",
            "starlette_csrf.middleware.CSRFMiddleware",
        ),
    )
    body = security_report(_model(chains=(chain,)))
    assert body["chains"] == [
        {
            "order": 0,
            "requestMatcher": "any request",
            "requestMatcherType": "ASGI middleware stack",
            "filters": ["TrustedHostMiddleware", "CORSMiddleware", "SessionMiddleware", "CSRFMiddleware"],
            "csrfEnabled": True,
            "corsEnabled": True,
            "sessionManagementPresent": True,
        }
    ]


def test_two_mounted_apps_two_chains_in_order():
    # ported: SpringSecurityControllerTests.twoFilterChainsProducedTwoDtoEntriesInOrder
    chains = (
        SecurityChain(None, ()),
        SecurityChain("/admin", ("starlette.middleware.sessions.SessionMiddleware",)),
        SecurityChain("/api", ("starlette.middleware.gzip.GZipMiddleware",)),
    )
    body = security_report(_model(chains=chains))
    assert [(c["order"], c["requestMatcher"], c["filters"]) for c in body["chains"]] == [
        (0, "any request", []),
        (1, "/admin/**", ["SessionMiddleware"]),
        (2, "/api/**", ["GZipMiddleware"]),
    ]


def test_auth_provider_types_listed():
    # ported: SpringSecurityControllerTests.authenticationProviderTypeListed
    model = _model(
        _route(SecurityScheme(BEARER, True, ())),
        _route(SecurityScheme(API_KEY, True, ()), SecurityScheme(BEARER, False, ()), path="/b"),
        backends=("app.auth.JWTBackend",),
    )
    auth = security_report(model)["auth"]
    assert auth == {
        "authenticationProviderTypes": [API_KEY, BEARER],
        "userDetailsServiceTypes": ["app.auth.JWTBackend"],
        "configuredUsername": None,
    }


def test_no_auth_providers_empty_lists():
    # ported: SpringSecurityControllerTests.noAuthProvidersResultsInEmptyLists
    body = security_report(_model(_route()))
    assert body["springSecurityPresent"] is True
    empty = {"authenticationProviderTypes": [], "userDetailsServiceTypes": [], "configuredUsername": None}
    assert body["auth"] == empty


def test_configured_username_is_null():
    # derived: no analogue; intent of SpringSecurityControllerTests.configuredUsernameIsExposedButPasswordIsNot
    body = security_report(_model(_route(SecurityScheme(BEARER, True, ()))))
    assert body["auth"] is not None
    assert body["auth"]["configuredUsername"] is None


def test_endpoints_sorted_by_pattern_then_method():
    model = _model(
        _route(path="/b", methods=("POST", "GET")),
        _route(SecurityScheme(BEARER, True, ()), path="/a"),
        SecuredRoute((), "/static/{path}", "starlette.staticfiles:StaticFiles", opaque=True),
    )
    body = endpoints_report(model)
    rows = [(e["pattern"], e["method"], e["rule"], e["bestEffort"]) for e in body["endpoints"]]
    assert rows == [
        ("/a", "GET", "authenticated", False),
        ("/b", "GET", "unsecured", False),
        ("/b", "POST", "unsecured", False),
        ("/static/{path}", "ANY", "unknown", True),
    ]
    assert body["total"] == 4


def test_custom_guard_is_not_secured():
    # a scheme-less dependency is not a security scheme: rule custom, but nothing proves the route is secured
    assert classify(_route(unknown=True))[1] is False


def test_route_level_unknown_dependency_is_custom_but_unsecured():
    assert classify(_route(unknown=True)) == ("custom", False, [], True)


def test_explain_after_an_unreadable_route_is_best_effort():
    unreadable = SecuredRoute((), "(any)", "app.routes:Custom", opaque=True, path_regex=None)
    items = SecuredRoute(("GET",), "/items", "app.main:items", path_regex="^/items$")
    assert explain(_model(unreadable, items), "GET", "/items", "/sharpit")["bestEffort"] is True
