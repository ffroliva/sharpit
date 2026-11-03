"""``fastapi-security`` (BootUI ``spring-security``): middleware stacks, schemes and endpoint rules, read statically."""

from __future__ import annotations

import re
from typing import Any

from sharpit.engine.spi import SecuredRoute, SecurityChain, SecurityModel

_SECURED = frozenset({"authenticated", "hasAuthority"})
HIDDEN = "sharpit endpoints are hidden from this report"
_Mounts = tuple[tuple[int, str | None], ...]


def model_of(ctx: Any) -> SecurityModel | None:
    """The adapter's security model (``security_model()`` is not on the ``AppIntrospector`` port); None if absent."""
    read = getattr(ctx.introspector, "security_model", None)
    if read is None:
        return None
    try:
        return read()
    except Exception as exc:  # noqa: BLE001 - introspection degrades, never crashes the host (safety 5)
        return SecurityModel(False, (), (), (), (f"FastAPI security could not be read ({type(exc).__name__}).",))


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
    return rule, rule in _SECURED, roles, route.unknown_dependency or route.unchecked_dependency


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
    if route.unchecked_dependency:
        return "Dependency without a security scheme (not evaluated)"
    return None


def _endpoint(model: SecurityModel, route: SecuredRoute, method: str) -> dict[str, Any]:
    rule, secured, roles, best_effort = classify(route)
    return {
        "method": method,
        "pattern": route.path or "/**",
        "handler": route.handler,
        "secured": secured,
        "rule": rule,
        "roles": roles,
        "chainIndex": route.chain,
        "matcherDescription": _matcher(model.chains[route.chain]),
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


def _unmatched(description: str | None = None, best_effort: bool = False) -> dict[str, Any]:
    return {
        "matched": False,
        "bestEffort": best_effort,
        "chainIndex": None,
        "matcherDescription": description,
        "filters": [],
        "rule": None,
        "roles": [],
        "pattern": None,
    }


def _accepts(route: SecuredRoute, method: str) -> bool:
    return not route.methods or method in route.methods or (method == "HEAD" and "GET" in route.methods)


def _inside(route: SecuredRoute, captured: _Mounts, path: str) -> tuple[bool, bool, _Mounts]:
    """(reached, unreadable, captured): descend the route's mounts below ``captured`` the way Starlette does."""
    remaining = path  # each mount's pattern sees only the path its parent mount left
    for depth, (_, regex) in enumerate(route.mounts):
        if regex is None:  # a Host: the request's host is not part of the question
            return False, True, captured
        match = re.match(regex, remaining)
        if match is None:
            return False, False, captured
        remaining = "/" + (match.groupdict().get("path") or "")
        if depth >= len(captured):
            captured = route.mounts[: depth + 1]  # a mount takes every path under its prefix: no fall-through after it
    return True, False, captured


def explain(model: SecurityModel | None, method: str, path: str, hidden: str) -> dict[str, Any]:
    """The first route (Starlette's order) whose compiled pattern and methods accept the request; nothing is called."""
    if path == hidden or path.startswith(hidden + "/"):
        return _unmatched(HIDDEN)
    if model is None or not model.present:
        return _unmatched()
    unreadable = False
    captured: _Mounts = ()
    for route in model.routes:
        if route.mounts[: len(captured)] != captured:
            break  # left the mount that took the request: Starlette answers inside it, never with a later route
        reached, skipped, captured = _inside(route, captured, path)
        unreadable = unreadable or skipped
        if not reached:
            continue
        if route.path_regex is None:
            unreadable = True
        elif re.match(route.path_regex, path) and _accepts(route, method):
            rule, _, roles, best_effort = classify(route)
            chain = model.chains[route.chain]
            return {
                "matched": True,
                "bestEffort": best_effort or unreadable,  # an unreadable route earlier might have taken the request
                "chainIndex": route.chain,
                "matcherDescription": _matcher(chain),
                "filters": [_simple(m) for m in chain.middleware],
                "rule": rule,
                "roles": roles,
                "pattern": route.path,
            }
    return _unmatched(best_effort=unreadable)
