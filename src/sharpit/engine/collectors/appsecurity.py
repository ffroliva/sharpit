"""``fastapi-security`` (BootUI ``spring-security``): middleware stacks, schemes and endpoint rules, read statically."""

from __future__ import annotations

from typing import Any

from sharpit.engine.spi import SecuredRoute, SecurityModel


def classify(route: SecuredRoute) -> tuple[str, bool, list[str], bool]:
    return "unknown", False, [], False


def security_report(model: SecurityModel | None) -> dict[str, Any]:
    return {"springSecurityPresent": False, "chains": [], "auth": None, "limitations": []}


def endpoints_report(model: SecurityModel | None) -> dict[str, Any]:
    return {"springSecurityPresent": False, "handlerMappingAvailable": False, "total": 0, "endpoints": []}


def explain(model: SecurityModel | None, method: str, path: str, hidden: str) -> dict[str, Any]:
    return {"matched": False, "bestEffort": False, "chainIndex": None, "matcherDescription": None, "filters": []}
