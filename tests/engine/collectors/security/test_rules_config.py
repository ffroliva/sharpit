"""Configuration rules: debug tracebacks, HTTPS and framework logging in production, literal secret defaults."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from fastapi import FastAPI
from sharpit.engine.collectors.security import View

RuleRun = Callable[..., list[tuple[str, str]]]
DEV_SECRET = "dev-only-signing-secret-9f8e7d"
PRODUCTION = View(production=True)


def _app(**options: object) -> FastAPI:
    app = FastAPI(**options)  # pyright: ignore[reportArgumentType]
    app.get("/items")(lambda: "items")
    return app


def _targets(found: list[tuple[str, str]]) -> list[str]:
    return [target for target, _ in found]


def test_debug_mode_returns_tracebacks(run_rule: RuleRun):
    # ported: SecurityRulesTests.securityDebugEnabled (Starlette debug tracebacks; SEC-CONFIG-005 merged here)
    found = [_targets(run_rule("SEC-CONFIG-001", _app(debug=d))) for d in (True, False)]
    assert found == [["application"], []]


def test_flags_missing_https_enforcement_in_production(run_rule: RuleRun):
    # ported: SecurityScannerTests.flagsMissingHttpsEnforcementInProduction
    redirected = _app()
    redirected.add_middleware(HTTPSRedirectMiddleware)
    found = [
        _targets(run_rule("SEC-CONFIG-006", _app(), view=PRODUCTION)),
        _targets(run_rule("SEC-CONFIG-006", redirected, view=PRODUCTION)),
        _targets(run_rule("SEC-CONFIG-006", _app())),
    ]
    assert found == [["ASGI middleware stack"], [], []]


def test_forwarded_headers_do_not_prove_https_enforcement(run_rule: RuleRun):
    # ported: SecurityScannerTests.forwardedHeadersDoNotProveHttpsEnforcement
    proxied = _app()
    proxied.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["10.0.0.1"])
    assert _targets(run_rule("SEC-CONFIG-006", proxied, view=PRODUCTION)) == ["ASGI middleware stack"]


def test_framework_debug_logging_in_production(run_rule: RuleRun):
    # ported: SecurityRulesTests.securityDebugLoggingProduction
    loud = View(production=True, debug_loggers=("sqlalchemy.engine", "uvicorn"))
    found = [
        _targets(run_rule("SEC-CONFIG-009", _app(), view=loud)),
        _targets(run_rule("SEC-CONFIG-009", _app(), view=View(debug_loggers=("uvicorn",)))),
    ]
    assert found == [["logger sqlalchemy.engine", "logger uvicorn"], []]


def _package(root: Path) -> Path:
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "settings.py").write_text(
        "import os\n"
        "from os import environ\n"
        f'SECRET_KEY = os.getenv("SECRET_KEY", "{DEV_SECRET}")\n'
        'PORT = os.getenv("PORT", "8000")\n'
        'API_TOKEN = environ.get("API_TOKEN", "")\n'
        'DB_PASSWORD = os.environ["DB_PASSWORD"]\n',
        encoding="utf-8",
    )
    return package


def test_literal_secret_default(run_rule: RuleRun, tmp_path: Path):
    # ported: SecurityRulesTests.hardcodedSecretProperty (the getenv reads moved onto engine/appsource.py)
    found = run_rule("SEC-CONFIG-007", _app(), source=_package(tmp_path))
    assert _targets(found) == ["shop/settings.py:3"]


def test_literal_secret_default_message_has_no_value(run_rule: RuleRun, tmp_path: Path):
    found = run_rule("SEC-CONFIG-007", _app(), source=_package(tmp_path))
    assert found != []
    assert DEV_SECRET not in repr(found)
