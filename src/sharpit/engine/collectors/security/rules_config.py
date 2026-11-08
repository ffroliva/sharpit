"""Configuration rules: debug tracebacks, HTTPS in production, framework logging, literal secret defaults."""

from __future__ import annotations

from sharpit.engine.appsource import getenv_findings
from sharpit.engine.collectors.security import (
    Inputs,
    SecurityRule,
    Violation,
    chain_has,
    rule,
    source_file,
    source_modules,
)
from sharpit.engine.masking import is_sensitive_key

_SECRETS = "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html"


_STACK = "ASGI middleware stack"


def _debug(inputs: Inputs) -> list[Violation]:
    if not inputs.facts.debug:
        return []
    return [Violation("application", "FastAPI(debug=True): unhandled errors return their traceback to the client.")]


def _https_in_production(inputs: Inputs) -> list[Violation]:
    model = inputs.model
    if not inputs.view.production or not model.chains or chain_has(model, 0, "HTTPSRedirectMiddleware"):
        return []
    message = "A production-like profile is active and the application's stack has no HTTPSRedirectMiddleware."
    return [Violation(_STACK, message)]


def _literal_secret_defaults(inputs: Inputs) -> list[Violation]:
    return [
        Violation(read.location, f"{read.location} reads {read.key} with a literal default.")
        for module in source_modules(inputs)
        for read in getenv_findings(module.tree, source_file(module))
        if read.default and read.default.strip() and is_sensitive_key(read.key)
    ]


def _debug_logging(inputs: Inputs) -> list[Violation]:
    if not inputs.view.production:
        return []
    return [
        Violation(f"logger {name}", f"The {name} logger runs at DEBUG under a production-like profile.")
        for name in sorted(inputs.view.debug_loggers)
    ]


RULES: tuple[SecurityRule, ...] = (
    SecurityRule(
        rule(
            "SEC-CONFIG-001",
            "Spring Security debug mode should be off",
            "Configuration",
            "MEDIUM",
            "FastAPI(debug=True) makes Starlette return the full traceback of an unhandled error to the client.",
            "Leave debug off outside local development.",
            "https://www.starlette.io/applications/",
        ),
        _debug,
    ),
    SecurityRule(
        rule(
            "SEC-CONFIG-006",
            "Application should enforce HTTPS in production",
            "Configuration",
            "LOW",
            "A production-like profile is active and the app's own stack has no HTTPSRedirectMiddleware. Best effort:"
            " TLS may be enforced by a proxy, and forwarded headers do not prove it.",
            "Add HTTPSRedirectMiddleware, or confirm the proxy redirects HTTP to HTTPS.",
            "https://fastapi.tiangolo.com/advanced/middleware/#httpsredirectmiddleware",
        ),
        _https_in_production,
    ),
    SecurityRule(
        rule(
            "SEC-CONFIG-007",
            "Configuration should not hold literal secret values",
            "Configuration",
            "HIGH",
            "A secret-like environment variable is read with a literal default: when the variable is unset the app"
            " runs on a secret committed to source.",
            "Drop the default and fail at startup when the secret is missing.",
            _SECRETS,
        ),
        _literal_secret_defaults,
        needs_source=True,
    ),
    SecurityRule(
        rule(
            "SEC-CONFIG-009",
            "Spring Security framework logging should not run at DEBUG/TRACE in production",
            "Configuration",
            "MEDIUM",
            "A production-like profile is active and a framework logger runs at DEBUG; request data, headers and SQL"
            " parameters reach the logs.",
            "Set the fastapi, starlette, uvicorn and sqlalchemy.engine loggers to INFO or higher in production.",
            "https://docs.python.org/3/library/logging.html#logging-levels",
        ),
        _debug_logging,
    ),
)
