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


# sharpit widening (Task P1): DSN userinfo with no password and connection-string credential segments
@pytest.mark.parametrize(
    "value",
    [
        "https://abc123def456@o1.ingest.sentry.io/1",
        "amqp://guestkey@broker:5672/vhost",
        "Server=db;Database=app;User Id=sa;Password=Pa55;",
        "Server=db;Uid=sa;Pwd=Pa55",
        "password=Pa55;Server=db",
        "DefaultEndpointsProtocol=https;AccountName=acct;AccountKey=abc==;EndpointSuffix=core.windows.net",
        "Endpoint=sb://ns.servicebus.windows.net/;SharedAccessKeyName=Root;SharedAccessKey=abc=",
        "Server=db; PASSWORD = Pa55",
    ],
)
def test_widened_secret_values_detected(value: str) -> None:
    assert is_secret_value(value)
    assert Masker(M, True).mask("APP_CONNECTION", value) == (MASK, True)


@pytest.mark.parametrize(
    "value", ["https://example.com/a@b", "user@example.com", "Server=db;Database=app;", "PasswordPolicy=strict"]
)
def test_widened_patterns_leave_benign_values(value: str) -> None:
    assert not is_secret_value(value)


VENDOR_PREFIXES = (
    "sk_live_",
    "sk_test_",
    "rk_live_",
    "pk_live_",
    "ghp_",
    "gho_",
    "ghs_",
    "ghu_",
    "github_pat_",
    "glpat-",
    "xoxb-",
    "xoxp-",
    "xoxa-",
    "AIza",
    "sk-ant-",
    "sk-proj-",
)


# sharpit widening (0.3.0 spec §9 A4): vendor token prefixes
@pytest.mark.parametrize(
    "value",
    [f"{prefix}0123456789abcdefABCDEF-_" for prefix in VENDOR_PREFIXES],
)
def test_vendor_prefix_is_secret(value: str) -> None:
    """A4: Vendor token prefixes in secret values."""
    assert is_secret_value(value)


@pytest.mark.parametrize(
    "value",
    [f"{prefix}{'a' * 15}" for prefix in VENDOR_PREFIXES],
)
def test_vendor_prefix_needs_16_token_chars(value: str) -> None:
    """A4: Vendor token prefix needs at least 16 token characters."""
    assert not is_secret_value(value)


@pytest.mark.parametrize("value", ["task_live_report", "mask-ant-farm"])
def test_prefix_inside_a_word_is_not_secret(value: str) -> None:
    """A4: Vendor token prefix inside a word is not secret."""
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


# sharpit widening (Task P1): ``pass`` as a whole name segment, so DB_PASS and PASS mask but bypass/compass do not
@pytest.mark.parametrize("name", ["PASS", "DB_PASS", "SMTP_PASS", "pass.word.file", "redis-pass", "APP_PASS_FILE"])
def test_pass_segment_is_sensitive(name: str) -> None:
    assert is_sensitive_key(name)


@pytest.mark.parametrize("name", ["CACHE_BYPASS", "COMPASS_HEADING", "PASSENGER_COUNT", "app.passthrough"])
def test_pass_inside_a_word_is_not_sensitive(name: str) -> None:
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


def test_own_token_never_shown() -> None:
    # sharpit's own token is masked by value whatever the mask setting or exposure (it would hand the console away)
    token = "tok-3f9a"
    for masker in (Masker(M, False, token), Masker(FULL, True, token), Masker(M, True, token)):
        assert masker.mask("SHARPIT_AUTHENTICATION_TOKEN", token) == (MASK, True)
        assert masker.mask("HARMLESS_COPY", token) == (MASK, True)
    assert Masker(META, True, token).mask("SHARPIT_AUTHENTICATION_TOKEN", token) == (None, False)
    assert Masker(M, False, token).mask("OTHER", "plain") == ("plain", False)


def test_own_token_masked_when_padded_or_embedded() -> None:
    # the configured token may carry whitespace; a copy of it can sit inside a URL or a padded value
    for configured in ("tok-3f9a", "  tok-3f9a\n"):
        for masker in (Masker(M, False, configured), Masker(FULL, True, configured)):
            assert masker.mask("PADDED", " tok-3f9a ") == (MASK, True)
            assert masker.mask("CALLBACK", "https://ci.example/hook?token=tok-3f9a&x=1") == (MASK, True)
            assert masker.mask("OTHER", "tok-3f9") == ("tok-3f9", False)
    assert Masker(M, False, "   ").mask("OTHER", "plain") == ("plain", False)  # a blank token masks nothing


def test_full_returns_raw() -> None:
    assert Masker(FULL, True).mask("db.password", "plain") == ("plain", False)


def test_non_string_value_untouched() -> None:
    value: Any = 8080
    assert Masker(M, True).mask("port", value) == (8080, False)


def test_empty_user_url_password_is_secret() -> None:
    # sharpit widening of SecretValueDetector: an empty user still carries a password (redis://:pw@host)
    assert is_secret_value("redis://:pw@host:6379/0")
    assert Masker(M, True).mask("APP_CACHE", "redis://:redispw@localhost:6379/0") == (MASK, True)


# ---- 0.2.0 text, path and header masking (spec §11) ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("login failed password=hunter2 for bob", "login failed password=****** for bob"),
        ("db.password: hunter2", "db.password: ******"),
        ("Authorization: Bearer abc.def", "Authorization: ******"),
        ('{"token": "abc", "user": "bob"}', '{"token": "******", "user": "bob"}'),
        ("connect to postgres://u:p@h/db failed", "connect to postgres://******@h/db failed"),
        ("redis://:pw@cache:6379/0", "redis://******@cache:6379/0"),
        (f"user sent {JWT} twice", f"user sent {MASK} twice"),
        (f'token was "{JWT}".', f'token was "{MASK}".'),
        (
            f'127.0.0.1:5000 - "GET /reset/{JWT} HTTP/1.1" 200 OK',
            f'127.0.0.1:5000 - "GET /reset/{MASK} HTTP/1.1" 200 OK',
        ),
        (
            "(sqlite3.IntegrityError) UNIQUE failed\n[SQL: INSERT INTO u VALUES (?, ?)]\n[parameters: ('bob', 'x')]\n"
            "(Background on this error at: https://sqlalche.me/e/20/gkpj)",
            "(sqlite3.IntegrityError) UNIQUE failed\n[SQL: INSERT INTO u VALUES (?, ?)]\n[parameters: ******]\n"
            "(Background on this error at: https://sqlalche.me/e/20/gkpj)",
        ),
        ("[parameters: [('a', 1), ('b', 2)]]", "[parameters: ******]"),
        ("GET /owners/42 HTTP/1.1 200", "GET /owners/42 HTTP/1.1 200"),
        ("plain words only", "plain words only"),
        # Python dict reprs and non-string JSON values (review r0)
        ("{'password': 'hunter2', 'user': 'bob'}", "{'password': '******', 'user': 'bob'}"),
        ("kwargs={'api_key': 'sk-live-abcdef123456'}", "kwargs={'api_key': '******'}"),
        ('{"password": 12345, "user": "bob"}', '{"password": "******", "user": "bob"}'),
        ("{'secret': None}", "{'secret': '******'}"),
        ("secret: [1, 2]", "secret: ******"),
        ("[parameters: ('bob', 'secret')", "[parameters: ******]"),
        ("Cookie: session=abc123; theme=dark", "Cookie: ******; theme=dark"),
    ],
)
def test_mask_text_corpus(text: str, expected: str) -> None:
    assert Masker(M, True).mask_text(text) == expected


def test_mask_text_json_stays_valid() -> None:
    import json

    masked = Masker(M, True).mask_text('{"token": "abc", "nested": {"password": "p w"}, "n": 1}')
    assert masked is not None
    assert json.loads(masked) == {"token": MASK, "nested": {"password": MASK}, "n": 1}


def test_mask_text_json_non_string_values_stay_valid() -> None:
    import json

    masked = Masker(M, True).mask_text('{"password": 12345, "pin_token": true, "api_keys": [1, 2], "n": null}')
    assert masked is not None
    assert json.loads(masked) == {"password": MASK, "pin_token": MASK, "api_keys": MASK, "n": None}


def test_mask_text_parameters_kept_when_capture_on() -> None:
    masker = Masker(M, True, capture_parameters=True)
    assert masker.mask_text("[parameters: ('bob', 'x')]") == "[parameters: ('bob', 'x')]"
    assert masker.mask_text(f"[parameters: ('bob', '{JWT}')]") == f"[parameters: ('bob', '{MASK}')]"


def test_mask_text_parameters_dropped_even_when_mask_secrets_off() -> None:
    assert Masker(M, False).mask_text("[parameters: ('bob',)] password=x") == "[parameters: ******] password=x"


def test_mask_text_none() -> None:
    assert Masker(M, True).mask_text(None) is None


def test_mask_text_metadata_only_none() -> None:
    assert Masker(META, True).mask_text("hello password=x") is None


def test_mask_text_metadata_only_drops_parameters_even_when_capture_on() -> None:
    masker = Masker(META, True, capture_parameters=True)
    assert masker.capture_parameters is False
    assert masker.mask_text("[parameters: ('bob', 'x')]") is None


def test_mask_text_full_unchanged() -> None:
    text = f"password=hunter2 {JWT} [parameters: ('bob',)] postgres://u:p@h/db"
    assert Masker(FULL, True).mask_text(text) == text


def test_mask_text_masks_own_token() -> None:
    token = "tok-3f9a"
    for masker in (Masker(M, True, token), Masker(M, False, token), Masker(FULL, True, token)):
        assert masker.mask_text(f"GET /sharpit?x={token}&y=1 sent tok-3f9a") == f"GET /sharpit?x={MASK}&y=1 sent {MASK}"


def test_mask_path_jwt_segment() -> None:
    masker = Masker(M, True)
    assert masker.mask_path(f"/reset/{JWT}/confirm") == f"/reset/{MASK}/confirm"
    assert masker.mask_path("/owners/42/pets") == "/owners/42/pets"
    assert masker.mask_path("/") == "/"
    assert Masker(FULL, True).mask_path(f"/reset/{JWT}") == f"/reset/{JWT}"
    assert Masker(M, True, "tok-3f9a").mask_path("/hook/tok-3f9a") == f"/hook/{MASK}"


def test_mask_header_by_name_and_value() -> None:
    masker = Masker(M, True)
    for name in ("Authorization", "proxy-authorization", "Cookie", "Set-Cookie", "X-API-Key", "x-csrf-token"):
        assert masker.mask_header(name, ["v1", "v2"]) == ([MASK, MASK], True), name
    assert masker.mask_header("x-forwarded-for", [JWT, "1.2.3.4"]) == ([MASK, "1.2.3.4"], True)
    assert masker.mask_header("accept", ["text/html"]) == (["text/html"], False)
    assert Masker(META, True).mask_header("accept", ["text/html"]) == ([], False)
    assert Masker(FULL, True).mask_header("cookie", ["a=b"]) == (["a=b"], False)
    assert Masker(FULL, True, "tok-3f9a").mask_header("authorization", ["Bearer tok-3f9a"]) == ([MASK], True)
