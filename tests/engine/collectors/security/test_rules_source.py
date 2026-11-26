"""Source rules over the app package (``engine/appsource.py``): passlib hashing and literal secrets."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param('audience="api", options={"verify_signature": False}', id="audience"),
        pytest.param('options={"verify_signature": False}', id="no-audience"),
        pytest.param('audience="api", options={"verify_signature": False, "verify_aud": True}', id="verify-aud-on"),
        pytest.param('audience="api", options={"verify_aud": False, "verify_signature": False}', id="both-off"),
    ],
)
def test_jwt_decode_with_signature_verification_disabled_fires(run_rule: RuleRun, tmp_path: Path, arguments: str):
    package = _package(tmp_path)
    (package / "auth.py").write_text(f"import jwt\njwt.decode(token, key, {arguments})\n", encoding="utf-8")
    messages = [message for _, message in run_rule("SEC-OAUTH-002", FastAPI(), source=package)]
    assert messages == ["shop/auth.py line 2: jwt.decode disables signature verification with verify_signature=False."]


def test_jwt_decode_with_signature_verification_enabled_does_not_fire(run_rule: RuleRun, tmp_path: Path):
    package = _package(tmp_path)
    (package / "auth.py").write_text(
        'import jwt\njwt.decode(token, key, audience="api", options={"verify_signature": True})\n', encoding="utf-8"
    )
    assert run_rule("SEC-OAUTH-002", FastAPI(), source=package) == []


def test_jwt_message_survives_masking_in_a_file_named_auth(
    inputs_of,
    service_for,
    tmp_path: Path,
):
    package = _package(tmp_path)
    (package / "auth.py").write_text(
        'import jwt\njwt.decode(token, key, audience="api", options={"verify_signature": False})\n', encoding="utf-8"
    )
    service = service_for(lambda: inputs_of(FastAPI(), source=package))
    results = service.scan()["results"]
    result = next(row for row in results if row["id"] == "SEC-OAUTH-002")
    assert result["sampleViolations"] == [
        "shop/auth.py line 2: jwt.decode disables signature verification with verify_signature=False."
    ]


@pytest.mark.parametrize(
    "options",
    [
        pytest.param('{"verify_signature": False, "verify_signature": True}', id="overwritten"),
        pytest.param('{"verify_signature": False, **{"verify_signature": True}}', id="overwritten-by-unpack"),
        pytest.param('{"verify_signature": False, **overrides}', id="unknown-unpack"),
    ],
)
def test_jwt_option_that_may_be_overwritten_does_not_fire(run_rule: RuleRun, tmp_path: Path, options: str):
    package = _package(tmp_path)
    (package / "auth.py").write_text(
        f'import jwt\njwt.decode(token, key, audience="api", options={options})\n', encoding="utf-8"
    )
    assert run_rule("SEC-OAUTH-002", FastAPI(), source=package) == []


@pytest.mark.parametrize(
    "options",
    [
        pytest.param('{"verify_signature": False, **{"verify_exp": True}}', id="unrelated-unpack"),
        pytest.param('{"verify_aud": False, **{"verify_exp": True}}', id="unrelated-unpack-aud"),
        pytest.param('{**{"verify_signature": False}}', id="nested"),
        pytest.param('{**base, "verify_signature": False}', id="earlier-unpack"),
    ],
)
def test_jwt_option_that_stays_disabled_fires(run_rule: RuleRun, tmp_path: Path, options: str):
    package = _package(tmp_path)
    (package / "auth.py").write_text(
        f'import jwt\njwt.decode(token, key, audience="api", options={options})\n', encoding="utf-8"
    )
    assert _targets(run_rule("SEC-OAUTH-002", FastAPI(), source=package)) == ["shop/auth.py:2"]


def test_decode_from_a_project_jwt_module_does_not_fire(run_rule: RuleRun, tmp_path: Path):
    package = _package(tmp_path)
    (package / "auth.py").write_text("from .jwt import decode\ndecode(token, key)\n", encoding="utf-8")
    assert run_rule("SEC-OAUTH-002", FastAPI(), source=package) == []


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


PLAINTEXT_CONTEXT = 'from passlib.context import CryptContext\npwd = CryptContext(schemes=["plaintext"])\n'


def _shopapp(root: Path, files: dict[str, str]) -> Path:
    package = root / "shopapp"
    for name, text in files.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        init = path.parent / "__init__.py"
        init.exists() or init.write_text("", encoding="utf-8")
    return package


def _samples(service, rule_id: str) -> list[str]:
    return next(row for row in service.scan()["results"] if row["id"] == rule_id)["sampleViolations"]


def test_source_finding_in_a_file_named_tokens_keeps_its_line_and_message(inputs_of, service_for, tmp_path: Path):
    package = _shopapp(tmp_path, {"crypto.py": PLAINTEXT_CONTEXT, "tokens.py": PLAINTEXT_CONTEXT})
    service = service_for(lambda: inputs_of(FastAPI(), source=package))
    assert _samples(service, "SEC-AUTH-001") == [
        "shopapp/crypto.py line 2: a CryptContext lists a plaintext scheme.",
        "shopapp/tokens.py line 2: a CryptContext lists a plaintext scheme.",
    ]


def test_source_finding_target_and_fingerprint_are_unchanged(inputs_of, service_for, tmp_path: Path):
    package = _shopapp(tmp_path, {"crypto.py": PLAINTEXT_CONTEXT, "tokens.py": PLAINTEXT_CONTEXT})
    service = service_for(lambda: inputs_of(FastAPI(), source=package))
    occurrences = service._scan_once(None).occurrences["SEC-AUTH-001"]
    assert [(fingerprint, identity) for fingerprint, _, identity in occurrences] == [
        ("security:SEC-AUTH-001:719f7214e56b8204", "shopapp/crypto.py:2"),
        ("security:SEC-AUTH-001:535d315899101a9a", "shopapp/tokens.py:******"),
    ]


def test_a_path_holding_a_secret_shaped_pair_stays_masked(inputs_of, service_for, tmp_path: Path):
    package = _shopapp(tmp_path, {"token=abc12345678/crypto.py": PLAINTEXT_CONTEXT})
    service = service_for(lambda: inputs_of(FastAPI(), source=package))
    samples = _samples(service, "SEC-AUTH-001")
    assert samples != []
    assert "abc12345678" not in repr(samples)


def test_a_secret_shaped_name_in_the_message_slot_stays_masked(inputs_of, service_for, tmp_path: Path):
    package = _shopapp(tmp_path, {"keys.py": 'CONFIG = {"token=abc12345678": "literal-value-1234"}\n'})
    service = service_for(lambda: inputs_of(FastAPI(), source=package))
    samples = _samples(service, "SEC-SRC-001")
    assert samples != []
    assert "abc12345678" not in repr(samples)


def test_a_secret_shaped_environment_key_stays_masked(inputs_of, service_for, tmp_path: Path):
    package = _shopapp(tmp_path, {"settings.py": 'import os\nKEY = os.getenv("token=abc12345678", "dev-secret")\n'})
    service = service_for(lambda: inputs_of(FastAPI(), source=package))
    samples = _samples(service, "SEC-CONFIG-007")
    assert samples != []
    assert "abc12345678" not in repr(samples)


@pytest.mark.parametrize(
    ("rule_id", "files", "expected"),
    [
        pytest.param(
            "SEC-AUTH-001",
            {"tokens.py": PLAINTEXT_CONTEXT},
            ["shopapp/tokens.py line 2: a CryptContext lists a plaintext scheme."],
            id="plaintext",
        ),
        pytest.param(
            "SEC-AUTH-002",
            {"tokens.py": 'from passlib.context import CryptContext\nc = CryptContext(schemes=["md5_crypt"])\n'},
            ["shopapp/tokens.py line 2: a CryptContext hashes new passwords with a legacy scheme."],
            id="legacy",
        ),
        pytest.param(
            "SEC-AUTH-006",
            {"tokens.py": "import bcrypt\nsalt = bcrypt.gensalt(rounds=6)\n"},
            ["shopapp/tokens.py line 2: bcrypt runs with fewer than 10 rounds."],
            id="bcrypt",
        ),
        pytest.param(
            "SEC-SRC-001",
            {"tokens.py": f'STRIPE = "{STRIPE_KEY}"\nSECRET_KEY = "{NAMED_SECRET}"\n'},
            [
                "shopapp/tokens.py line 1: holds a literal the secret detectors flag.",
                "shopapp/tokens.py line 2: assigns a literal to the secret-like name SECRET_KEY.",
            ],
            id="literal-secret",
        ),
        pytest.param(
            "SEC-CONFIG-007",
            {"tokens.py": 'import os\nKEY = os.getenv("SECRET_KEY", "dev-secret")\n'},
            ["shopapp/tokens.py line 2: reads SECRET_KEY with a literal default."],
            id="literal-default",
        ),
        pytest.param(
            "SEC-OAUTH-002",
            {"tokens.py": 'import jwt\njwt.decode(t, k, audience="a", options={"verify_aud": False})\n'},
            ["shopapp/tokens.py line 2: jwt.decode disables audience validation with verify_aud=False."],
            id="jwt",
        ),
    ],
)
def test_source_rule_text_leads_with_the_location(run_rule: RuleRun, tmp_path: Path, rule_id, files, expected):
    package = _shopapp(tmp_path, files)
    assert [message for _, message in run_rule(rule_id, FastAPI(), source=package)] == expected
