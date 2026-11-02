"""``fastapi-security`` (BootUI ``spring-security``): middleware stacks, schemes and endpoint rules, read statically."""

from __future__ import annotations

from typing import Any

from sharpit.engine.spi import SecuredRoute, SecurityChain, SecurityModel

_SECURED = frozenset({"authenticated", "hasAuthority", "custom"})


def _simple(name: str) -> str:
    return name.rpartition(".")[2]


def classify(route: SecuredRoute) -> tuple[str, bool, list[str], bool]:
    """``(rule, secured, roles, bestEffort)`` from the schemes found in the route's dependency tree."""
    if route.opaque:
        return "unknown", False, [], True
    required = [s for s in route.schemes if s.auto_error]
    roles = sorted({scope for s in required for scope in s.scopes})
    if roles:
        rule = "hasAuthority"
    elif required:
        rule = "authenticated"
    elif route.schemes:
        rule = "permitAll"  # every scheme has auto_error=False: anonymous requests get through
    elif route.unknown_dependency:
        rule = "custom"
    else:
        rule = "unsecured"
    return rule, rule in _SECURED, roles, route.unknown_dependency


def _matcher(chain: SecurityChain) -> str:
    return "any request" if chain.prefix is None else f"{chain.prefix}/**"


def _chain(order: int, chain: SecurityChain) -> dict[str, Any]:
    names = [_simple(m) for m in chain.middleware]
    return {
        "order": order,
        "requestMatcher": _matcher(chain),
        "requestMatcherType": "ASGI middleware stack" if chain.prefix is None else "Mount",
        "filters": names,
        "csrfEnabled": any(m.startswith(("starlette_csrf.", "asgi_csrf")) for m in chain.middleware),
        "corsEnabled": "CORSMiddleware" in names,
        "sessionManagementPresent": "SessionMiddleware" in names,
    }


def security_report(model: SecurityModel | None) -> dict[str, Any]:
    limitations = list(model.limitations) if model else []
    if model is None or not model.present:
        return {"springSecurityPresent": False, "chains": [], "auth": None, "limitations": limitations}
    schemes = {s.type_name for r in model.routes for s in r.schemes}
    return {
        "springSecurityPresent": True,
        "chains": [_chain(i, c) for i, c in enumerate(model.chains)],
        "auth": {
            "authenticationProviderTypes": sorted(schemes),
            "userDetailsServiceTypes": sorted(set(model.auth_backends)),
            "configuredUsername": None,  # no FastAPI analogue of spring.security.user.name
        },
        "limitations": limitations,
    }


def _description(route: SecuredRoute) -> str | None:
    if route.opaque:
        return "The route's security could not be read statically"
    if route.unknown_dependency:
        return "Route-level dependency without a security scheme (custom guard, not evaluated)"
    if route.schemes:
        return "Managed by " + ", ".join(dict.fromkeys(_simple(s.type_name) for s in route.schemes))
    return None


def _endpoint(model: SecurityModel, route: SecuredRoute, method: str) -> dict[str, Any]:
    rule, secured, roles, best_effort = classify(route)
    chain = model.chains[route.chain] if route.chain < len(model.chains) else None
    return {
        "method": method,
        "pattern": route.path or "/**",
        "handler": route.handler,
        "secured": secured,
        "rule": rule,
        "roles": roles,
        "chainIndex": route.chain if chain else None,
        "matcherDescription": _matcher(chain) if chain else None,
        "description": _description(route),
        "bestEffort": best_effort,
    }


def endpoints_report(model: SecurityModel | None) -> dict[str, Any]:
    limitations = list(model.limitations) if model else []
    if model is None or not model.present:
        return {
            "springSecurityPresent": False,
            "handlerMappingAvailable": False,
            "total": 0,
            "endpoints": [],
            "limitations": limitations,
        }
    rows = [_endpoint(model, r, m) for r in model.routes for m in (r.methods or ("ANY",))]
    rows.sort(key=lambda e: (e["pattern"], e["method"]))
    return {
        "springSecurityPresent": True,
        "handlerMappingAvailable": True,
        "total": len(rows),
        "endpoints": rows,
        "limitations": limitations,
    }


def explain(model: SecurityModel | None, method: str, path: str, hidden: str) -> dict[str, Any]:
    return {"matched": False, "bestEffort": False, "chainIndex": None, "matcherDescription": None, "filters": []}
