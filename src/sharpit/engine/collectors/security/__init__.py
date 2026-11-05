"""The ``security`` advisor (BootUI ``SecurityScanner``/``SecurityRules``) over the FastAPI security model.

Rules are pure functions of one ``Inputs``: the ``SecurityModel`` (routes, schemes, middleware stacks), the
``SecurityFacts`` (middleware options as facts, never values), the app's ``SourceIndex`` (None when unreadable) and a
``View`` of the settings. A violation names a route, a middleware or a ``file:line``; never a literal or option value.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sharpit.engine.advisors.rules import RuleDefinition, Severity
from sharpit.engine.appsource import ModuleInfo, SourceIndex
from sharpit.engine.spi import SecuredRoute, SecurityFacts, SecurityModel

ADVISOR = "security"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class View:
    """What the rules read from the settings and the process (read on the scan, never changed)."""

    production: bool = False  # an active profile is one of ``disabled_profiles`` (``prod``, ``production``)
    debug_loggers: tuple[str, ...] = ()  # framework loggers whose own level is DEBUG or lower


@dataclass(frozen=True)
class Inputs:
    model: SecurityModel
    facts: SecurityFacts
    source: SourceIndex | None  # None: the app's source could not be resolved (a limitation says why)
    view: View = View()
    limitations: tuple[str, ...] = ()  # source resolution notes


@dataclass(frozen=True)
class Violation:
    target: str  # a route (``POST /items``), a middleware name or ``file:line``
    message: str
    identity: str | None = None  # a stable identity for the fingerprint, when the target is not one


@dataclass(frozen=True)
class SecurityRule:
    definition: RuleDefinition
    check: Callable[[Inputs], list[Violation]]
    needs_source: bool = False  # not evaluated when the source is unavailable


def simple(name: str) -> str:
    return name.rpartition(".")[2]


def route_label(route: SecuredRoute) -> str:
    return f"{','.join(route.methods) or 'ANY'} {route.path}"


def chain_has(model: SecurityModel, chain: int, middleware: str) -> bool:
    """The route's middleware stack holds a middleware of that simple class name."""
    if not 0 <= chain < len(model.chains):
        return False
    return any(simple(m) == middleware for m in model.chains[chain].middleware)


def rule(
    rule_id: str, name: str, category: str, severity: Severity, description: str, recommendation: str, url: str
) -> RuleDefinition:
    return RuleDefinition(rule_id, name, category, severity, description, recommendation, url)


def source_modules(inputs: Inputs) -> list[ModuleInfo]:
    return list(inputs.source.modules.values()) if inputs.source is not None else []


def source_file(module: ModuleInfo) -> str:
    """The module's path from its top package's parent (shop/settings.py), as appsource names it."""
    depth = len(module.name.split(".")) + (module.path.name == "__init__.py")
    return module.path.relative_to(module.path.parents[depth - 1]).as_posix()
