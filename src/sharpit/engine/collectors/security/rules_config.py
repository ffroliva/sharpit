"""Configuration rules: debug tracebacks, HTTPS in production, framework logging, literal secret defaults."""

from __future__ import annotations

from sharpit.engine.collectors.security import Inputs, SecurityRule, Violation, rule

_SECRETS = "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html"


def _none(_inputs: Inputs) -> list[Violation]:
    return []


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
        _none,
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
        _none,
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
        _none,
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
        _none,
    ),
)
