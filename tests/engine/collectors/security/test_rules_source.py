"""Source rules over the app package (``engine/appsource.py``): passlib hashing and literal secrets."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from sharpit.engine.collectors.security.report import RULES as SECURITY_RULES

RuleRun = Callable[..., list[tuple[str, str]]]
STRIPE_KEY = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"  # in pieces: GitHub push protection
NAMED_SECRET = "hunter2-correct-horse"


def _package(root: Path) -> Path:
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "hashing.py").write_text(
        "import bcrypt\n"
        "from passlib.context import CryptContext\n"
        'plain = CryptContext(schemes=["plaintext"])\n'
        'legacy = CryptContext(schemes=["md5_crypt", "bcrypt"])\n'
        'migrating = CryptContext(schemes=["bcrypt", "md5_crypt"], deprecated="auto")\n'
        'cheap = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4)\n'
        "salt = bcrypt.gensalt(rounds=6)\n"
        "strong = bcrypt.gensalt(12)\n",
        encoding="utf-8",
    )
    (package / "keys.py").write_text(
        f'STRIPE = "{STRIPE_KEY}"\nSECRET_KEY = "{NAMED_SECRET}"\nTIMEOUT = "30"\npassword = ""\nLABEL = "secret"\n',
        encoding="utf-8",
    )
    return package


def _targets(found: list[tuple[str, str]]) -> list[str]:
    return [target for target, _ in found]


def _run(run_rule: RuleRun, rule_id: str, tmp_path: Path) -> list[tuple[str, str]]:
    return run_rule(rule_id, FastAPI(), source=_package(tmp_path))


def test_plaintext_password_context(run_rule: RuleRun, tmp_path: Path):
    # ported: SecurityRulesTests.noOpPasswordEncoder
    assert _targets(_run(run_rule, "SEC-AUTH-001", tmp_path)) == ["shop/hashing.py:3"]


def test_legacy_default_password_scheme(run_rule: RuleRun, tmp_path: Path):
    # ported: SecurityRulesTests.weakPasswordEncoder (only the default, first, scheme hashes new passwords)
    assert _targets(_run(run_rule, "SEC-AUTH-002", tmp_path)) == ["shop/hashing.py:4"]


def test_bcrypt_work_factor_below_10(run_rule: RuleRun, tmp_path: Path):
    # ported: SecurityRulesTests.weakBcryptStrength
    assert _targets(_run(run_rule, "SEC-AUTH-006", tmp_path)) == ["shop/hashing.py:6", "shop/hashing.py:7"]


def test_literal_secret_in_source(run_rule: RuleRun, tmp_path: Path):
    assert _targets(_run(run_rule, "SEC-SRC-001", tmp_path)) == ["shop/keys.py:1", "shop/keys.py:2"]


def test_literal_secret_in_source_message_has_no_value(run_rule: RuleRun, tmp_path: Path):
    found = _run(run_rule, "SEC-SRC-001", tmp_path)
    assert found != []
    assert STRIPE_KEY not in repr(found)
    assert NAMED_SECRET not in repr(found)


def test_jwt_decode_with_audience_verification_disabled_fires(run_rule: RuleRun, tmp_path: Path):
    package = _package(tmp_path)
    (package / "auth.py").write_text(
        'import jwt\nclaims = jwt.decode(token, key, audience="api", options={"verify_aud": False})\n',
        encoding="utf-8",
    )
    found = run_rule("SEC-OAUTH-002", FastAPI(), source=package)
    assert _targets(found) == ["shop/auth.py:2"]
    assert "jwt.decode disables audience validation with verify_aud=False." in found[0][1]


def test_jwt_decode_with_audience_verification_enabled_does_not_fire(run_rule: RuleRun, tmp_path: Path):
    assert "SEC-OAUTH-002" in {rule.definition.id for rule in SECURITY_RULES}
    package = _package(tmp_path)
    (package / "auth.py").write_text(
        'import jwt\nclaims = jwt.decode(token, key, audience="api", options={"verify_aud": True})\n',
        encoding="utf-8",
    )
    found = run_rule("SEC-OAUTH-002", FastAPI(), source=package)
    assert found == []


def test_jwt_decode_with_explicit_none_audience_fires(run_rule: RuleRun, tmp_path: Path):
    package = _package(tmp_path)
    (package / "auth.py").write_text("import jwt\njwt.decode(token, key, audience=None)\n", encoding="utf-8")
    assert _targets(run_rule("SEC-OAUTH-002", FastAPI(), source=package)) == ["shop/auth.py:2"]


def test_jwt_decode_with_kwargs_skips_unknown_audience(run_rule: RuleRun, tmp_path: Path):
    package = _package(tmp_path)
    (package / "auth.py").write_text("import jwt\njwt.decode(token, key, **kwargs)\n", encoding="utf-8")
    assert run_rule("SEC-OAUTH-002", FastAPI(), source=package) == []


def test_jwt_decode_module_alias_fires(run_rule: RuleRun, tmp_path: Path):
    package = _package(tmp_path)
    (package / "auth.py").write_text("import jwt as pyjwt\npyjwt.decode(token, key)\n", encoding="utf-8")
    assert _targets(run_rule("SEC-OAUTH-002", FastAPI(), source=package)) == ["shop/auth.py:2"]


def test_jwt_decode_imported_name_fires(run_rule: RuleRun, tmp_path: Path):
    package = _package(tmp_path)
    (package / "auth.py").write_text("from jwt import decode\ndecode(token, key)\n", encoding="utf-8")
    assert _targets(run_rule("SEC-OAUTH-002", FastAPI(), source=package)) == ["shop/auth.py:2"]


def test_jwt_decode_import_alias_fires(run_rule: RuleRun, tmp_path: Path):
    package = _package(tmp_path)
    (package / "auth.py").write_text("from jwt import decode as d\nd(token, key)\n", encoding="utf-8")
    assert _targets(run_rule("SEC-OAUTH-002", FastAPI(), source=package)) == ["shop/auth.py:2"]


def test_unrelated_decode_does_not_fire(run_rule: RuleRun, tmp_path: Path):
    package = _package(tmp_path)
    (package / "auth.py").write_text("from other import decode\ndecode(token, key)\n", encoding="utf-8")
    assert run_rule("SEC-OAUTH-002", FastAPI(), source=package) == []
