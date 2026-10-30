from typing import Any

import pytest

from sharpit.engine.masking import MASK, Exposure, Masker, is_secret_value, is_sensitive_key

M = Exposure.MASKED
FULL = Exposure.FULL
META = Exposure.METADATA_ONLY

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"


# ---- SecretValueDetector -------------------------------------------------------------------------------------------
# ported: SecretValueDetectorTests.detectsUrlUserinfoCredentials / detectsUrlQueryParameterCredentials /
# detectsJwtTokens / detectsAwsAccessKeys / detectsPemPrivateKeys
@pytest.mark.parametrize(
    "value",
    [
        "jdbc:postgresql://alice:s3cret@db:5432/app",
        "https://user:pass@example.com/path",
        "jdbc:mysql://db/app?user=alice&password=s3cret",
        "https://api.example.com/v1?api_key=abcdef",
        "https://idp.example.com/cb?access_token=abc123",
        "https://idp.example.com/cb?refresh_token=abc123",
        "https://app.example.com/?client_secret=abc123",
        JWT,
        "AKIAIOSFODNN7EXAMPLE",
        "ASIAIOSFODNN7EXAMPLE",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END",
    ],
)
def test_secret_values_detected(value: str) -> None:
    assert is_secret_value(value)


# ported: SecretValueDetectorTests.ignoresBenignQueryParameters / ignoresBenignValues
@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/?token_type=Bearer",
        "https://example.com/?section=secret-garden",
        "jdbc:postgresql://db:5432/app",
        "https://example.com/path?user=alice",
        "checkout-service",
        "8080",
        "",
        "   ",
    ],
)
def test_benign_values_not_detected(value: str) -> None:
    assert not is_secret_value(value)


# ---- KeywordPatternMasker (no upstream oracle) ---------------------------------------------------------------------
# derived: KeywordPatternMasker (one case per DEFAULT_KEY_PATTERNS entry)
@pytest.mark.parametrize(
    "pattern",
    [
        "password", "passwd", "passphrase", "pwd", "secret", "token", "key", "credential", "credentials",
        "private", "apikey", "api-key", "client-secret", "client_secret", "auth", "authorization",
        "session-id", "session_id",
    ],
)  # fmt: skip
def test_default_key_patterns(pattern: str) -> None:
    assert is_sensitive_key(pattern)
    assert is_sensitive_key(f"my.app.{pattern.upper()}.value")  # case-insensitive substring


# derived: KeywordPatternMasker.isSecret (blank and non-matching branches)
@pytest.mark.parametrize("name", ["", "   ", "server.port", "spring.application.name"])
def test_non_sensitive_keys(name: str) -> None:
    assert not is_sensitive_key(name)


# derived: KeywordPatternMasker.shouldMask (name branch, value branch, neither, null value)
def test_should_mask_branches() -> None:
    m = Masker(M, True)
    assert m.mask("db.password", "plain") == (MASK, True)
    assert m.mask("db.url", "jdbc:postgresql://u:p@h/db") == (MASK, True)
    assert m.mask("server.port", "8080") == ("8080", False)
    assert m.mask("server.port", 8080) == (8080, False)
    assert m.mask("db.password", None) == (None, False)


# derived: KeywordPatternMasker.mask with mask_secrets=False
def test_mask_secrets_off_shows_values() -> None:
    assert Masker(M, False).mask("db.password", "plain") == ("plain", False)


def test_cache_key_prefix_masked_by_design() -> None:
    assert is_sensitive_key("cache.key-prefix")
    assert Masker(M, True).mask("cache.key-prefix", "app:") == (MASK, True)


class _Secret:
    def get_secret_value(self) -> str:
        return "hunter2"


def test_secretstr_always_masked() -> None:
    assert Masker(M, True).mask("harmless.name", _Secret()) == (MASK, True)
    assert Masker(M, False).mask("harmless.name", _Secret()) == (MASK, True)
    assert Masker(FULL, True).mask("harmless.name", _Secret())[1] is False


def test_metadata_only_hides_value() -> None:
    assert Masker(META, True).mask("server.port", "8080") == (None, False)
    assert Masker(META, True).mask("db.password", "x") == (None, False)


def test_full_returns_raw() -> None:
    assert Masker(FULL, True).mask("db.password", "plain") == ("plain", False)


def test_non_string_value_untouched() -> None:
    value: Any = 8080
    assert Masker(M, True).mask("port", value) == (8080, False)


def test_empty_user_url_password_is_secret() -> None:
    # sharpit widening of SecretValueDetector: an empty user still carries a password (redis://:pw@host)
    assert is_secret_value("redis://:pw@host:6379/0")
    assert Masker(M, True).mask("APP_CACHE", "redis://:redispw@localhost:6379/0") == (MASK, True)
