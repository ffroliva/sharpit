"""Parity tests for security advisor rules vs BootUI 2.3.0.

Ported from BootUI SecurityRulesTests, SecurityScannerTests and SecurityAuditAccuracyTests.
All tests assert rule id, severity, and location target (locations only, never values/secrets).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyCookie, HTTPBasic, OAuth2AuthorizationCodeBearer, OAuth2PasswordBearer
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import Depends, FastAPI
from sharpit.engine import appsource
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.advisors.scan import Evaluation
from sharpit.engine.collectors.security import Inputs, View
from sharpit.engine.collectors.security.report import SecurityService, scan_evaluation
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.fastapi.introspector import FastApiIntrospector

PLANTED_SECRET = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"


class FakeCsrfMiddleware:
    """Stands in for starlette_csrf.CSRFMiddleware."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class SessionMiddleware:
    """Stands in for Starlette's (which needs itsdangerous): same name and options."""

    def __init__(self, app: ASGIApp, secret_key: str, same_site: str = "lax", https_only: bool = False) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


def _never(*_args: Any) -> str:
    raise AssertionError("an endpoint was called")


def _evaluate(app: Any, *, source: Path | None = None, view: View | None = None) -> Evaluation:
    introspector = FastApiIntrospector(app)
    index = appsource.build_index(source, thread=False) if source is not None else None
    return scan_evaluation(Inputs(introspector.security_model(), introspector.security_facts(), index, view or View()))


def _findings(evaluation: Evaluation, rule_id: str) -> list[Any]:
    return [finding for finding in evaluation.findings if finding.rule_id == rule_id]


# ============================================================================
# Group 1: Authentication (SEC-AUTH-001, 002, 006, 007, 010)
# ============================================================================


@pytest.mark.bootui("rule:SEC-AUTH-001")
def test_sec_auth_001_plaintext_password_encoder(tmp_path: Path):
    # ported: SecurityRulesTests.noOpPasswordEncoderIsCritical
    # ported: SecurityAuditAccuracyTests.activeProviderSelectedEncoderIsInspectedWithoutCallingSupplier
    src = tmp_path / "app"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "sec.py").write_text(
        'from passlib.context import CryptContext\npwd_context = CryptContext(schemes=["plaintext"])\n',
        encoding="utf-8",
    )
    evaluation = _evaluate(FastAPI(), source=src)
    findings = _findings(evaluation, "SEC-AUTH-001")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-AUTH-001"
    assert findings[0].severity == "CRITICAL"
    assert findings[0].target == "app/sec.py:2"

    src2 = tmp_path / "app2"
    src2.mkdir()
    (src2 / "__init__.py").write_text("", encoding="utf-8")
    (src2 / "sec.py").write_text(
        'from passlib.context import CryptContext\npwd_context = CryptContext(schemes=["bcrypt"])\n',
        encoding="utf-8",
    )
    evaluation2 = _evaluate(FastAPI(), source=src2)
    findings2 = _findings(evaluation2, "SEC-AUTH-001")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-AUTH-002")
def test_sec_auth_002_weak_password_encoder(tmp_path: Path):
    # ported: SecurityAuditAccuracyTests.activeProviderSelectedEncoderIsInspectedWithoutCallingSupplier
    src = tmp_path / "app"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "sec.py").write_text(
        'from passlib.context import CryptContext\npwd_context = CryptContext(schemes=["md5_crypt"])\n',
        encoding="utf-8",
    )
    evaluation = _evaluate(FastAPI(), source=src)
    findings = _findings(evaluation, "SEC-AUTH-002")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-AUTH-002"
    assert findings[0].severity == "HIGH"
    assert findings[0].target == "app/sec.py:2"

    src2 = tmp_path / "app2"
    src2.mkdir()
    (src2 / "__init__.py").write_text("", encoding="utf-8")
    (src2 / "sec.py").write_text(
        "from passlib.context import CryptContext\n"
        'pwd_context = CryptContext(schemes=["argon2", "bcrypt"], default="argon2")\n',
        encoding="utf-8",
    )
    evaluation2 = _evaluate(FastAPI(), source=src2)
    findings2 = _findings(evaluation2, "SEC-AUTH-002")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-AUTH-006")
def test_sec_auth_006_bcrypt_rounds(tmp_path: Path):
    # ported: SecurityScannerTests.flagsBcryptEncoderConfiguredBelowRecommendedStrength
    # ported: SecurityScannerTests.doesNotFlagBcryptEncoderUsingDefaultOrAdequateStrength
    src = tmp_path / "app"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "sec.py").write_text(
        'from passlib.context import CryptContext\npwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4)\n',
        encoding="utf-8",
    )
    evaluation = _evaluate(FastAPI(), source=src)
    findings = _findings(evaluation, "SEC-AUTH-006")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-AUTH-006"
    assert findings[0].severity == "LOW"
    assert findings[0].target == "app/sec.py:2"

    src2 = tmp_path / "app2"
    src2.mkdir()
    (src2 / "__init__.py").write_text("", encoding="utf-8")
    (src2 / "sec.py").write_text(
        'from passlib.context import CryptContext\npwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)\n',
        encoding="utf-8",
    )
    evaluation2 = _evaluate(FastAPI(), source=src2)
    findings2 = _findings(evaluation2, "SEC-AUTH-006")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-AUTH-007")
def test_sec_auth_007_basic_auth_without_https():
    # ported: SecurityRulesTests.basicAuthWithoutTlsFiresInProduction
    # ported: SecurityRulesTests.basicAuthWithoutTlsIsIgnoredOutsideProduction
    app = FastAPI()
    app.add_api_route("/items", _never, methods=["GET"], dependencies=[Depends(HTTPBasic())])
    assert _findings(_evaluate(app), "SEC-AUTH-007") == []
    evaluation = _evaluate(app, view=View(production=True))
    findings = _findings(evaluation, "SEC-AUTH-007")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-AUTH-007"
    assert findings[0].severity == "HIGH"
    assert findings[0].target == "GET /items"

    app2 = FastAPI()
    app2.add_middleware(HTTPSRedirectMiddleware)
    app2.add_api_route("/items", _never, methods=["GET"], dependencies=[Depends(HTTPBasic())])
    evaluation2 = _evaluate(app2, view=View(production=True))
    findings2 = _findings(evaluation2, "SEC-AUTH-007")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-AUTH-010")
def test_sec_auth_010_form_login_without_https():
    # ported: SecurityRulesTests.formLoginWithoutTlsFiresInProduction
    # ported: SecurityRulesTests.formLoginWithoutTlsIsIgnoredOutsideProduction
    app = FastAPI()
    bearer = OAuth2PasswordBearer(tokenUrl="token")
    app.add_api_route("/items", _never, methods=["GET"], dependencies=[Depends(bearer)])
    assert _findings(_evaluate(app), "SEC-AUTH-010") == []
    evaluation = _evaluate(app, view=View(production=True))
    findings = _findings(evaluation, "SEC-AUTH-010")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-AUTH-010"
    assert findings[0].severity == "HIGH"
    assert findings[0].target == "GET /items"

    app2 = FastAPI()
    app2.add_middleware(HTTPSRedirectMiddleware)
    bearer2 = OAuth2PasswordBearer(tokenUrl="token")
    app2.add_api_route("/items", _never, methods=["GET"], dependencies=[Depends(bearer2)])
    evaluation2 = _evaluate(app2, view=View(production=True))
    findings2 = _findings(evaluation2, "SEC-AUTH-010")
    assert findings2 == []


# ============================================================================
# Group 2: Authorization (SEC-AUTHZ-001, 002, 003)
# ============================================================================


@pytest.mark.bootui("rule:SEC-AUTHZ-001")
def test_sec_authz_001_unsecured_write_in_secured_app():
    # ported from the rule class: SEC-AUTHZ-001 checks unsecured writes in an otherwise secured app.
    app = FastAPI()
    app.add_api_route("/secured", _never, methods=["GET"], dependencies=[Depends(HTTPBasic())])
    app.add_api_route("/public", _never, methods=["POST"])
    evaluation = _evaluate(app)
    findings = _findings(evaluation, "SEC-AUTHZ-001")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-AUTHZ-001"
    assert findings[0].severity == "INFO"  # recorded BootUI severity deviation
    assert findings[0].target == "POST /public"

    app2 = FastAPI()
    app2.add_api_route("/secured", _never, methods=["GET"], dependencies=[Depends(HTTPBasic())])
    app2.add_api_route("/write", _never, methods=["POST"], dependencies=[Depends(HTTPBasic())])
    evaluation2 = _evaluate(app2)
    findings2 = _findings(evaluation2, "SEC-AUTHZ-001")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-AUTHZ-002")
def test_sec_authz_002_blanket_permit_all():
    # ported from the rule class: SEC-AUTHZ-002 checks whether all routes are anonymous.
    app = FastAPI()
    app.add_api_route("/items", _never, methods=["GET", "POST"])
    evaluation = _evaluate(app)
    findings = _findings(evaluation, "SEC-AUTHZ-002")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-AUTHZ-002"
    assert findings[0].severity == "HIGH"
    assert findings[0].target == "application"

    app2 = FastAPI()
    app2.add_api_route("/items", _never, methods=["GET"], dependencies=[Depends(HTTPBasic())])
    evaluation2 = _evaluate(app2)
    findings2 = _findings(evaluation2, "SEC-AUTHZ-002")
    assert findings2 == []


# ============================================================================
# Group 3: Configuration (SEC-CONFIG-001, 006, 007, 009)
# ============================================================================


@pytest.mark.bootui("rule:SEC-CONFIG-001")
def test_sec_config_001_debug_mode():
    # ported: SecurityRulesTests.securityDebugFilterFires
    # ported: SecurityRulesTests.unsupportedSpringSecurityDebugPropertyDoesNotFire
    app = FastAPI(debug=True)
    evaluation = _evaluate(app)
    findings = _findings(evaluation, "SEC-CONFIG-001")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-CONFIG-001"
    assert findings[0].severity == "MEDIUM"
    assert findings[0].target == "application"

    app2 = FastAPI(debug=False)
    evaluation2 = _evaluate(app2)
    findings2 = _findings(evaluation2, "SEC-CONFIG-001")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-CONFIG-006")
def test_sec_config_006_https_in_production():
    # ported: SecurityScannerTests.flagsMissingHttpsEnforcementInProduction
    # ported: SecurityScannerTests.forwardedHeadersDoNotProveHttpsEnforcement
    app = FastAPI()
    app.add_api_route("/items", _never, methods=["GET"])
    evaluation = _evaluate(app, view=View(production=True))
    findings = _findings(evaluation, "SEC-CONFIG-006")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-CONFIG-006"
    assert findings[0].severity == "LOW"
    assert findings[0].target == "ASGI middleware stack"

    app2 = FastAPI()
    app2.add_middleware(HTTPSRedirectMiddleware)
    app2.add_api_route("/items", _never, methods=["GET"])
    evaluation2 = _evaluate(app2, view=View(production=True))
    findings2 = _findings(evaluation2, "SEC-CONFIG-006")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-CONFIG-007")
def test_sec_config_007_literal_secret_defaults(tmp_path: Path):
    # ported: SecurityRulesTests.hardcodedSecretPropertyFiresHighViolationWithoutLeakingTheValue
    # ported: SecurityRulesTests.hardcodedSecretPropertyPassesWhenNoSecretLikeKeysPresent
    src = tmp_path / "app"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "cfg.py").write_text(
        'import os\nKEY = os.getenv("SECRET_KEY", "static-literal-secret-12345")\n',
        encoding="utf-8",
    )
    evaluation = _evaluate(FastAPI(), source=src)
    findings = _findings(evaluation, "SEC-CONFIG-007")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-CONFIG-007"
    assert findings[0].severity == "HIGH"
    assert findings[0].target == "app/cfg.py:2"

    src2 = tmp_path / "app2"
    src2.mkdir()
    (src2 / "__init__.py").write_text("", encoding="utf-8")
    (src2 / "cfg.py").write_text(
        'import os\nKEY = os.getenv("SECRET_KEY")\n',
        encoding="utf-8",
    )
    evaluation2 = _evaluate(FastAPI(), source=src2)
    findings2 = _findings(evaluation2, "SEC-CONFIG-007")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-CONFIG-009")
def test_sec_config_009_debug_logging_in_production():
    # ported: SecurityRulesTests.securityDebugLoggingFiresForDebugLevelInProduction
    # ported: SecurityRulesTests.securityDebugLoggingPassesWhenLevelIsNotDebugOrTrace
    app = FastAPI()
    evaluation = _evaluate(app, view=View(production=True, debug_loggers=("uvicorn",)))
    findings = _findings(evaluation, "SEC-CONFIG-009")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-CONFIG-009"
    assert findings[0].severity == "MEDIUM"
    assert findings[0].target == "logger uvicorn"

    evaluation2 = _evaluate(app, view=View(production=False, debug_loggers=("uvicorn",)))
    findings2 = _findings(evaluation2, "SEC-CONFIG-009")
    assert findings2 == []


# ============================================================================
# Group 4: CORS (SEC-CORS-001, 002, 006)
# ============================================================================


@pytest.mark.bootui("rule:SEC-CORS-001")
def test_sec_cors_001_wildcard_origin():
    # ported: SecurityRulesTests.corsWildcardOriginRuleStillFiresARealViolationEvenWithACustomSourceAlsoPresent
    # ported: SecurityRulesTests.corsCompletionRequiresAnActuallyEvaluatedConfiguration
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False)
    evaluation = _evaluate(app)
    findings = _findings(evaluation, "SEC-CORS-001")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-CORS-001"
    assert findings[0].severity == "LOW"
    assert findings[0].target == "CORSMiddleware"

    app2 = FastAPI()
    app2.add_middleware(CORSMiddleware, allow_origins=["https://example.com"], allow_credentials=False)
    evaluation2 = _evaluate(app2)
    findings2 = _findings(evaluation2, "SEC-CORS-001")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-CORS-002")
def test_sec_cors_002_wildcard_with_credentials():
    # ported from the rule class: wildcard origins with credentials are a high-severity violation.
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
    evaluation = _evaluate(app)
    findings = _findings(evaluation, "SEC-CORS-002")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-CORS-002"
    assert findings[0].severity == "HIGH"
    assert findings[0].target == "CORSMiddleware"

    app2 = FastAPI()
    app2.add_middleware(CORSMiddleware, allow_origins=["https://example.com"], allow_credentials=True)
    evaluation2 = _evaluate(app2)
    findings2 = _findings(evaluation2, "SEC-CORS-002")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-CORS-006")
def test_sec_cors_006_broad_origin_pattern():
    # ported: SecurityRulesTests.broadCorsOriginPatternIsLowContextualReviewWithoutCredentials
    # ported: SecurityRulesTests.broadCorsOriginPatternIgnoresScopedSubdomainWildcard
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origin_regex=r".*")
    evaluation = _evaluate(app)
    findings = _findings(evaluation, "SEC-CORS-006")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-CORS-006"
    assert findings[0].severity == "LOW"
    assert findings[0].target == "CORSMiddleware"

    app2 = FastAPI()
    app2.add_middleware(CORSMiddleware, allow_origin_regex=r"^https://[a-z0-9]+\.example\.com$")
    evaluation2 = _evaluate(app2)
    findings2 = _findings(evaluation2, "SEC-CORS-006")
    assert findings2 == []


# ============================================================================
# Group 5: CSRF (SEC-CSRF-001, 002)
# ============================================================================


@pytest.mark.bootui("rule:SEC-CSRF-001")
def test_sec_csrf_001_cookie_credentials_without_csrf():
    # ported from the rule class: Starlette cookie credentials need CSRF middleware.
    app = FastAPI()
    app.add_api_route("/items", _never, methods=["POST"], dependencies=[Depends(APIKeyCookie(name="session"))])
    evaluation = _evaluate(app)
    findings = _findings(evaluation, "SEC-CSRF-001")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-CSRF-001"
    assert findings[0].severity == "HIGH"
    assert findings[0].target == "POST /items"

    app2 = FastAPI()
    app2.add_middleware(FakeCsrfMiddleware)
    app2.add_api_route("/items", _never, methods=["POST"], dependencies=[Depends(APIKeyCookie(name="session"))])
    evaluation2 = _evaluate(app2)
    findings2 = _findings(evaluation2, "SEC-CSRF-001")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-CSRF-002")
def test_sec_csrf_002_basic_auth_without_csrf():
    # ported from the rule class: CSRF disabled for HTTP Basic is a finding.
    # ported from the rule class: bearer schemes are not browser-automatic credentials.
    app = FastAPI()
    app.add_api_route("/items", _never, methods=["POST"], dependencies=[Depends(HTTPBasic())])
    evaluation = _evaluate(app)
    findings = _findings(evaluation, "SEC-CSRF-002")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-CSRF-002"
    assert findings[0].severity == "MEDIUM"
    assert findings[0].target == "POST /items"

    app2 = FastAPI()
    app2.add_middleware(FakeCsrfMiddleware)
    app2.add_api_route("/items", _never, methods=["POST"], dependencies=[Depends(HTTPBasic())])
    evaluation2 = _evaluate(app2)
    findings2 = _findings(evaluation2, "SEC-CSRF-002")
    assert findings2 == []


# ============================================================================
# Group 6: OAuth2 (SEC-OAUTH-004, 006)
# ============================================================================


@pytest.mark.bootui("rule:SEC-OAUTH-004")
def test_sec_oauth_004_insecure_jwt_metadata_url():
    # ported: SecurityRulesTests.insecureIssuerUriFires
    # ported from the rule class: HTTPS metadata URLs pass.
    from fastapi.security import OpenIdConnect

    app = FastAPI()
    app.add_api_route(
        "/items",
        _never,
        methods=["GET"],
        dependencies=[Depends(OpenIdConnect(openIdConnectUrl="http://remote.idp.example/openid"))],
    )
    assert _findings(_evaluate(app), "SEC-OAUTH-004") == []
    evaluation = _evaluate(app, view=View(production=True))
    findings = _findings(evaluation, "SEC-OAUTH-004")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-OAUTH-004"
    assert findings[0].severity == "HIGH"
    assert findings[0].target == "OpenIdConnect openIdConnectUrl"

    app2 = FastAPI()
    app2.add_api_route(
        "/items",
        _never,
        methods=["GET"],
        dependencies=[Depends(OpenIdConnect(openIdConnectUrl="https://remote.idp.example/openid"))],
    )
    evaluation2 = _evaluate(app2, view=View(production=True))
    findings2 = _findings(evaluation2, "SEC-OAUTH-004")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-OAUTH-002")
def test_sec_oauth_002_jwt_decode_requires_audience(tmp_path: Path):
    # partial: BootUI checks framework-managed decoders on active bearer chains, not custom decoders.
    src = tmp_path / "app"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "auth.py").write_text(
        'import jwt\nclaims = jwt.decode(token, key, algorithms=["RS256"])\n', encoding="utf-8"
    )
    evaluation = _evaluate(FastAPI(), source=src)
    findings = _findings(evaluation, "SEC-OAUTH-002")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-OAUTH-002"
    assert findings[0].severity == "INFO"
    assert findings[0].target == "app/auth.py:2"
    assert (
        "Without audience=, PyJWT rejects tokens with aud, so the risk is tokens without an aud claim."
        in findings[0].message
    )

    (src / "auth.py").write_text(
        'import jwt\nclaims = jwt.decode(token, key, audience="api", algorithms=["RS256"])\n', encoding="utf-8"
    )
    evaluation2 = _evaluate(FastAPI(), source=src)
    findings2 = _findings(evaluation2, "SEC-OAUTH-002")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-OAUTH-006")
def test_sec_oauth_006_insecure_oauth2_client_endpoint():
    # ported: SecurityRulesTests.plainHttpClientProviderEndpointsAreReportedOnlyWhenLinkedToARegistration
    # ported: SecurityRulesTests.plainHttpClientProviderEndpointsAreNotFlaggedInDevelopment
    scheme = OAuth2AuthorizationCodeBearer(
        authorizationUrl="http://remote.idp.example/auth",
        tokenUrl="https://remote.idp.example/token",
    )
    app = FastAPI()
    app.add_api_route("/items", _never, methods=["GET"], dependencies=[Depends(scheme)])
    assert _findings(_evaluate(app), "SEC-OAUTH-006") == []
    evaluation = _evaluate(app, view=View(production=True))
    findings = _findings(evaluation, "SEC-OAUTH-006")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-OAUTH-006"
    assert findings[0].severity == "HIGH"
    assert findings[0].target == "OAuth2AuthorizationCodeBearer authorizationUrl"

    scheme2 = OAuth2AuthorizationCodeBearer(
        authorizationUrl="https://remote.idp.example/auth",
        tokenUrl="https://remote.idp.example/token",
    )
    app2 = FastAPI()
    app2.add_api_route("/items", _never, methods=["GET"], dependencies=[Depends(scheme2)])
    evaluation2 = _evaluate(app2, view=View(production=True))
    findings2 = _findings(evaluation2, "SEC-OAUTH-006")
    assert findings2 == []


# ============================================================================
# Group 7: Session (SEC-SESSION-002, 004, 008)
# ============================================================================


@pytest.mark.bootui("rule:SEC-SESSION-002")
def test_sec_session_002_cookie_secure_flag():
    # ported: SecurityRulesTests.sessionCookieSecureReviewsProductionWithoutDirectTls
    # ported: SecurityRulesTests.unsetSessionCookieSecurePassesForStatelessChainInProduction
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="a" * 32, https_only=False)
    assert _findings(_evaluate(app), "SEC-SESSION-002") == []
    evaluation = _evaluate(app, view=View(production=True))
    findings = _findings(evaluation, "SEC-SESSION-002")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-SESSION-002"
    assert findings[0].severity == "MEDIUM"
    assert findings[0].target == "SessionMiddleware"

    app2 = FastAPI()
    app2.add_middleware(SessionMiddleware, secret_key="a" * 32, https_only=True)
    evaluation2 = _evaluate(app2, view=View(production=True))
    findings2 = _findings(evaluation2, "SEC-SESSION-002")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-SESSION-004")
def test_sec_session_004_same_site_none():
    # ported: SecurityRulesTests.sameSiteNoneIsReviewedButUnsetLaxAndPentestOwnedCombinationAreNot
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="a" * 32, same_site="none")
    evaluation = _evaluate(app)
    findings = _findings(evaluation, "SEC-SESSION-004")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-SESSION-004"
    assert findings[0].severity == "LOW"
    assert findings[0].target == "SessionMiddleware"

    app2 = FastAPI()
    app2.add_middleware(SessionMiddleware, secret_key="a" * 32, same_site="lax")
    evaluation2 = _evaluate(app2)
    findings2 = _findings(evaluation2, "SEC-SESSION-004")
    assert findings2 == []


@pytest.mark.bootui("rule:SEC-SESSION-008")
def test_sec_session_008_short_signing_key():
    # ported: SecurityRulesTests.weakRememberMeKeyFiresForAShortSigningKey
    # ported: SecurityRulesTests.weakRememberMeKeyPassesForALongSigningKey
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="short")
    evaluation = _evaluate(app)
    findings = _findings(evaluation, "SEC-SESSION-008")
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC-SESSION-008"
    assert findings[0].severity == "MEDIUM"
    assert findings[0].target == "SessionMiddleware"

    app2 = FastAPI()
    app2.add_middleware(SessionMiddleware, secret_key="a" * 32)
    evaluation2 = _evaluate(app2)
    findings2 = _findings(evaluation2, "SEC-SESSION-008")
    assert findings2 == []


# ============================================================================
# Group 8: Leak test (locations only, secrets never leak)
# ============================================================================


def test_planted_secret_never_leaks_in_security_findings(tmp_path: Path):
    src = tmp_path / "app"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "cfg.py").write_text(
        f'import os\nSECRET = os.getenv("SECRET_KEY", "{PLANTED_SECRET}")\n',
        encoding="utf-8",
    )
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key=PLANTED_SECRET)
    app.add_api_route(
        f"/auth/{PLANTED_SECRET}",
        _never,
        methods=["GET"],
        dependencies=[Depends(HTTPBasic())],
    )
    introspector = FastApiIntrospector(app)
    service = SecurityService(
        lambda: Inputs(
            introspector.security_model(),
            introspector.security_facts(),
            appsource.build_index(src, thread=False),
            View(production=True),
        ),
        DismissalStore(tmp_path / "state"),
        Masker(Exposure.MASKED, True),
        SingleFlight(),
        max_retained=10000,
    )
    output = json.dumps(service.scan())
    assert "SEC-AUTH-007" in output
    assert PLANTED_SECRET not in output
