from typing import Any

import pytest

from sharpit.engine.masking import (
    MASK,
    Exposure,
    Masker,
    carries_credentials,
    decode_path_component,
    decode_query_component,
    is_secret_value,
    is_sensitive_header,
    is_sensitive_key,
    mask_path,
    mask_query_string,
    mask_uri,
    mask_user_info,
    redact_credentials,
    redact_message,
)

M = Exposure.MASKED
FULL = Exposure.FULL
META = Exposure.METADATA_ONLY

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
H = "https://api.example.com"


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


# ---- SensitiveNames ------------------------------------------------------------------------------------------------
# ported: SensitiveNamesTests.recognizesKeywordNamesAndTheHeaderAllowList / recognizesPercentEncodedNames /
# recognizesNamesHiddenBehindNonAsciiEncoding / survivesMalformedPercentEscapes /
# decodesValidEscapesEvenWhenAMalformedSequenceIsPresent / decodesAValueEndingInATruncatedEscape
@pytest.mark.parametrize(
    "name",
    [
        "apiKey", "access_token", "Authorization", "Set-Cookie", "X-XSRF-TOKEN", "Cookie", "proxy-authorization",
        "x-csrf-token",
        "%70assword", "api%2Dkey", "%41uthorization", "client%5Fsecret",
        "%E2%80%8Bpassword",
        "token%", "%70assword%ZZ", "api%2Dkey%", "%70assword%7",
    ],
)  # fmt: skip
def test_sensitive_headers(name: str) -> None:
    assert is_sensitive_header(name)


# ported: SensitiveNamesTests.leavesOrdinaryNamesAlone / treatsNullAndBlankNamesAsNotSensitive /
# survivesMalformedPercentEscapes / doesNotDoubleDecode / replacesInvalidUtf8BytesInsteadOfRaising
@pytest.mark.parametrize("name", ["page", "X-Trace", "content-length", "", "   ", "%zz", "%2570assword", "%FF"])
def test_not_sensitive_headers(name: str) -> None:
    assert not is_sensitive_header(name)


# ported: SensitiveNamesTests.treatsPlusAsSpaceInQueryNamesButNotInPathSegments
def test_plus_decoding() -> None:
    assert decode_query_component("api+key") == "api key"
    assert decode_path_component("api+key") == "api+key"


# ported: SensitiveNamesTests.survivesMalformedPercentEscapes / doesNotDoubleDecode /
# decodesValidEscapesEvenWhenAMalformedSequenceIsPresent / decodesAValueEndingInATruncatedEscape /
# replacesInvalidUtf8BytesInsteadOfRaising / acceptsBothHexCases
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("%", "%"),
        ("%zz", "%zz"),
        ("token%", "token%"),
        ("%2570assword", "%70assword"),
        ("%70assword%ZZ", "password%ZZ"),
        ("%70assword%7", "password%7"),
        ("%FF", "�"),
        ("%2f%2F", "//"),
        ("", ""),
    ],
)
def test_decode_query_component(raw: str, expected: str) -> None:
    assert decode_query_component(raw) == expected


# ported: SensitiveNamesTests.handlesNullAndEmptyDecodeInput
def test_decode_null() -> None:
    assert decode_query_component(None) is None
    assert decode_path_component(None) is None


# ---- UriMasking ----------------------------------------------------------------------------------------------------
# ported: UriMaskingTests.removesAuthorityUserInfoButKeepsHostAndPort / removesUserInfoThatContainsNoPassword /
# removesUserInfoFromIpv6AndProtocolRelativeAuthorities / removesUserInfoWhenTheAuthorityIsFollowedDirectly... /
# leavesOrdinaryUrisUntouched / doesNotMistakeAnAtSignInThePathForUserInfo
@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("https://alice:s3cr3t@api.example.com:8443/orders", f"https://{MASK}@api.example.com:8443/orders"),
        ("https://alice@api.example.com/orders", f"https://{MASK}@api.example.com/orders"),
        ("http://alice:s3cr3t@[::1]:8080/x", f"http://{MASK}@[::1]:8080/x"),
        ("//alice:s3cr3t@api.example.com/x", f"//{MASK}@api.example.com/x"),
        ("https://alice:s3cr3t@api.example.com?page=2", f"https://{MASK}@api.example.com?page=2"),
        ("https://alice:s3cr3t@api.example.com#top", f"https://{MASK}@api.example.com#top"),
        ("https://api.example.com/orders?page=2#top", "https://api.example.com/orders?page=2#top"),
        ("/orders/42", "/orders/42"),
        ("", ""),
        ("https://api.example.com/users/alice@example.com", "https://api.example.com/users/alice@example.com"),
        ("/a//alice@example.com/b", "/a//alice@example.com/b"),
    ],
)
def test_mask_user_info(uri: str, expected: str) -> None:
    assert mask_user_info(uri) == expected


# ported: UriMaskingTests.leavesOrdinaryUrisUntouched (null)
def test_mask_user_info_none() -> None:
    assert mask_user_info(None) is None


# ported: UriMaskingTests.masksSensitiveQueryValuesByNameAndKeepsTheRest / masksPercentEncodedSensitiveQueryNames /
# masksAValuelessSensitiveParameterWholesale / keepsEmptyParametersAndPreservesParameterOrder /
# honorsTheExposurePolicy / preservesTheOriginalParameterSeparators
@pytest.mark.parametrize(
    ("query", "mask_secrets", "exposure", "expected"),
    [
        ("apiKey=s3cr3t&page=2", True, M, f"apiKey={MASK}&page=2"),
        ("%70assword=s3cr3t&page=2", True, M, f"%70assword={MASK}&page=2"),
        ("api%2Dkey=s3cr3t", True, M, f"api%2Dkey={MASK}"),
        ("access_token&page=2", True, M, f"{MASK}&page=2"),
        ("verbose&page=2", True, M, "verbose&page=2"),
        ("a=1&&b=2", True, M, "a=1&&b=2"),
        ("", True, M, ""),
        (None, True, M, None),
        ("apiKey=s3cr3t", False, M, "apiKey=s3cr3t"),
        ("apiKey=s3cr3t", True, FULL, "apiKey=s3cr3t"),
        ("apiKey=s3cr3t", True, META, None),
        ("a=1;b=2&c=3", True, M, "a=1;b=2&c=3"),
    ],
)
def test_mask_query_string(query: str | None, mask_secrets: bool, exposure: Exposure, expected: str | None) -> None:
    assert mask_query_string(query, mask_secrets, exposure) == expected


# ported: UriMaskingTests maskUri cases; the Java test name precedes each case
@pytest.mark.parametrize(
    ("uri", "mask_secrets", "exposure", "expected"),
    [
        # masksUserInfoQueryAndFragmentTogether
        (
            "https://alice:s3cr3t@api.example.com/orders?apiKey=abc&page=2#access_token=xyz",
            True,
            M,
            f"https://{MASK}@api.example.com/orders?apiKey={MASK}&page=2#access_token={MASK}",
        ),
        # keepsUserInfoMaskedEvenUnderFullExposure
        (
            "https://alice:s3cr3t@api.example.com/orders?apiKey=abc",
            True,
            FULL,
            f"https://{MASK}@api.example.com/orders?apiKey=abc",
        ),
        ("https://alice:s3cr3t@api.example.com/orders", False, FULL, f"https://{MASK}@api.example.com/orders"),
        # dropsQueryAndFragmentUnderMetadataOnlyExposure
        (f"{H}/orders?page=2#section", True, META, f"{H}/orders"),
        # keepsANonSensitiveFragment
        (f"{H}/docs#installation", True, M, f"{H}/docs#installation"),
        # treatsEverythingAfterTheFirstHashAsFragmentAndStillMasksSecretsInIt
        (f"{H}/docs#a?token=abc", True, M, f"{H}/docs#a?token={MASK}"),
        (f"{H}/docs#a?page=2", True, M, f"{H}/docs#a?page=2"),
        # leavesOrdinaryAndRelativeUrisUnchanged
        (f"{H}/orders", True, M, f"{H}/orders"),
        ("/orders?page=2", True, M, "/orders?page=2"),
        (f"{H}/orders?", True, M, f"{H}/orders?"),
        # masksATruncatedUriWithoutFailing
        (
            "https://alice:s3cr3t@api.example.com/orders?apiKey=abc…",
            True,
            M,
            f"https://{MASK}@api.example.com/orders?apiKey={MASK}",
        ),
        # masksParametersSeparatedByTheLegacySemicolon
        (f"{H}/orders?page=2;token=qsecret", True, M, f"{H}/orders?page=2;token={MASK}"),
        # masksSensitiveMatrixParametersInThePath
        (f"{H}/orders;token=pathsecret/42?page=2", True, M, f"{H}/orders;token={MASK}/42?page=2"),
        # masksSensitiveMatrixParametersEvenUnderMetadataOnlyExposure
        (f"{H}/orders;token=pathsecret?page=2", True, META, f"{H}/orders;token={MASK}"),
        # doesNotMistakeAHostPortForAMatrixParameter
        (f"{H}:8443/orders", True, M, f"{H}:8443/orders"),
        # masksAParameterValueCarryingANestedEncodedCredentialUrl
        (
            f"{H}/go?redirect=https%3A%2F%2Fevil%2Fcb%3Faccess_token%3Dnestedsecret",
            True,
            M,
            f"{H}/go?redirect={MASK}",
        ),
        # masksAParameterValueCarryingNestedUserInfo
        (f"{H}/go?next=https://alice:s3cr3t@evil/cb", True, M, f"{H}/go?next={MASK}"),
        # masksNestedCredentialsEvenUnderFullExposure
        (f"{H}/go?next=https://alice:s3cr3t@evil/cb", True, FULL, f"{H}/go?next={MASK}"),
        # leavesAnOrdinaryNestedRedirectUrlVisible
        (
            f"{H}/go?redirect=https%3A%2F%2Fexample.com%2Fhome",
            True,
            M,
            f"{H}/go?redirect=https%3A%2F%2Fexample.com%2Fhome",
        ),
        # masksMatrixValuesUnderMetadataOnlyEvenWhenMaskSecretsIsOff
        ("https://h/orders;token=secret", False, META, f"https://h/orders;token={MASK}"),
        # keepsMatrixValuesVisibleUnderMaskedExposureWhenMaskSecretsIsOff
        ("https://h/orders;token=secret", False, M, "https://h/orders;token=secret"),
        # neverMasksAPathSegmentThatSharesASensitiveParameterName
        ("https://h/api/token/refresh;v=1", True, M, "https://h/api/token/refresh;v=1"),
        # masksAnEncodedSensitiveNameCarryingAMalformedEscape
        ("https://h/x?%70assword%ZZ=secret", True, M, f"https://h/x?%70assword%ZZ={MASK}"),
        # masksANestedCredentialUrlEndingInAMalformedEscape
        (
            "https://h/x?redirect=https%3A%2F%2Falice%3Apw%40host%2Fcb%ZZ",
            True,
            M,
            f"https://h/x?redirect={MASK}",
        ),
        # masksASensitiveNameLongerThanAnyMatcherBound
        ("https://h/x?" + "a" * 200 + "password=secret", True, M, "https://h/x?" + "a" * 200 + f"password={MASK}"),
        # masksASecretAfterAnHtmlEscapedAmpersandBecauseBothCharactersSeparate
        ("https://h/x?page=2&amp;access_token=secret", True, M, f"https://h/x?page=2&amp;access_token={MASK}"),
    ],
)
def test_mask_uri_cases(uri: str, mask_secrets: bool, exposure: Exposure, expected: str) -> None:
    assert mask_uri(uri, mask_secrets, exposure) == expected


def test_mask_uri_defaults_and_none() -> None:
    # sharpit: mask_uri(uri) defaults to mask_secrets=True, exposure=MASKED
    assert mask_uri("https://u:p@h/x?token=a") == f"https://{MASK}@h/x?token={MASK}"
    assert mask_uri(None) is None  # ported: UriMaskingTests.leavesOrdinaryAndRelativeUrisUnchanged


# ported: UriMaskingTests.masksPathMatrixParametersThroughMaskPath /
# masksMatrixValuesUnderMetadataOnlyEvenWhenMaskSecretsIsOff / neverMasksAPathSegmentThatSharesASensitiveParameterName
@pytest.mark.parametrize(
    ("path", "mask_secrets", "exposure", "expected"),
    [
        ("/orders;token=abc/42", True, M, f"/orders;token={MASK}/42"),
        ("/orders/42", True, M, "/orders/42"),
        ("/orders;token=abc", True, FULL, "/orders;token=abc"),
        (None, True, M, None),
        ("/orders;token=secret", False, META, f"/orders;token={MASK}"),
        ("/api/token/refresh;v=1", True, M, "/api/token/refresh;v=1"),
    ],
)
def test_mask_path(path: str | None, mask_secrets: bool, exposure: Exposure, expected: str | None) -> None:
    assert mask_path(path, mask_secrets, exposure) == expected


# ---- CredentialRedaction -------------------------------------------------------------------------------------------
# ported: CredentialRedactionTests.redactsUserAndPasswordEmbeddedInAConnectionUrl /
# redactsCredentialQueryParametersInBothCommonSeparatorStyles / leavesTextWithoutCredentialsUnchanged
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("jdbc:postgresql://app:sup3rs3cret@db.internal:5432/orders", "jdbc:postgresql://******@db.internal:5432/orders"),
        (
            "jdbc:mysql://db/app?user=root&password=hunter2&useSsl=true",
            "jdbc:mysql://db/app?user=******&password=******&useSsl=true",
        ),
        (
            "jdbc:sqlserver://db;user=sa;password=hunter2;encrypt=true",
            "jdbc:sqlserver://db;user=******;password=******;encrypt=true",
        ),
        ('relation "orders" does not exist', 'relation "orders" does not exist'),
        ("", ""),
    ],
)  # fmt: skip
def test_redact_credentials(text: str, expected: str) -> None:
    assert redact_credentials(text) == expected


# ported: CredentialRedactionTests.redactsCredentialsInsideADriverErrorMessage
def test_redact_credentials_in_driver_error() -> None:
    message = (
        "FATAL: password authentication failed while opening jdbc:postgresql://reporting:s3cr3t@10.0.0.4:5432/warehouse"
    )
    out = redact_credentials(message)
    assert "s3cr3t" not in out
    assert "******@10.0.0.4" in out


# ported: CredentialRedactionTests.leavesTextWithoutCredentialsUnchanged / redactMessageLeavesOrdinaryTextUnchanged
def test_redact_none() -> None:
    assert redact_credentials(None) is None
    assert redact_message(None) is None


# ported: CredentialRedactionTests.redactMessage*; the Java test name precedes each case
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # redactMessageAlsoMasksSensitiveQueryValuesByName
        (
            'I/O error on GET request for "https://api.example.com/orders?apiKey=verysecretvalue&page=2": '
            "Connection refused",
            'I/O error on GET request for "https://api.example.com/orders?apiKey=******&page=2": Connection refused',
        ),
        # redactMessageMasksPercentEncodedSensitiveQueryNames
        ("failed: https://api/x?%70assword=hunter2&page=2", "failed: https://api/x?%70assword=******&page=2"),
        # redactMessageMasksSeveralParametersInOneMessage
        (
            "GET https://api/x?token=a&page=2&client_secret=b failed",
            "GET https://api/x?token=******&page=2&client_secret=****** failed",
        ),
        # redactMessageStillRedactsUrlCredentials
        (
            "Connect to https://alice:hunter2@api.example.com failed",
            "Connect to https://******@api.example.com failed",
        ),
        # redactMessageRemovesPercentEncodedUserInfo
        ("failed https://alice%3As3cr3t@host/x", "failed https://******@host/x"),
        # redactMessageRemovesUserInfoFromASchemeRelativeAuthority
        ("failed //alice:s3cr3t@host/x", "failed //******@host/x"),
        # redactMessageMasksSensitiveFragmentParameters
        ("failed https://host/x#access_token=fragsecret", "failed https://host/x#access_token=******"),
        # redactMessageMasksAQueryParameterFollowedByAFragment
        ("failed https://host/x?token=a#state=b", "failed https://host/x?token=******#state=b"),
        # redactMessageMasksASensitiveNameLongerThanAnyMatcherBound
        ("failed https://h/x?" + "a" * 200 + "password=secret", "failed https://h/x?" + "a" * 200 + "password=******"),
        # redactMessageMasksAnEncodedNestedCredentialUrl
        ("failed https://h/x?redirect=https%3A%2F%2Falice%3Apw%40host%2Fcb", "failed https://h/x?redirect=******"),
        # redactMessageMasksAnEncodedNestedSensitiveParameter
        (
            "failed https://h/x?redirect=https%3A%2F%2Fevil%2Fcb%3Faccess_token%3Dnested",
            "failed https://h/x?redirect=******",
        ),
        # redactMessageMasksAnEncodedSensitiveNameCarryingAMalformedEscape
        ("failed https://h/x?%70assword%ZZ=secret", "failed https://h/x?%70assword%ZZ=******"),
        # redactMessageMasksASecretAfterAnHtmlEscapedAmpersand
        ("failed https://h/x?page=2&amp;access_token=secret", "failed https://h/x?page=2&amp;access_token=******"),
        # redactMessageLeavesOrdinaryTextUnchanged
        (
            "Connection refused: connect to api.example.com:443?page=2",
            "Connection refused: connect to api.example.com:443?page=2",
        ),
        ("", ""),
        # redactMessageDoesNotMistakeAnEmailAddressInAPathForUserInfo
        ("404 for https://host/users/alice@example.com", "404 for https://host/users/alice@example.com"),
        # redactMessageLeavesAnOrdinaryNestedRedirectVisible
        (
            "failed https://h/x?redirect=https%3A%2F%2Fexample.com%2Fhome",
            "failed https://h/x?redirect=https%3A%2F%2Fexample.com%2Fhome",
        ),
    ],
)
def test_redact_message(text: str, expected: str) -> None:
    assert redact_message(text) == expected


# ported: CredentialRedactionTests.carriesCredentialsDetectsNestedCredentialsAndIgnoresOrdinaryValues
def test_carries_credentials() -> None:
    assert carries_credentials("https%3A%2F%2Falice%3Apw%40host%2Fcb")
    assert not carries_credentials("https://example.com/home")
    assert not carries_credentials("")
    assert not carries_credentials(None)


def test_non_string_value_untouched() -> None:
    value: Any = 8080
    assert Masker(M, True).mask("port", value) == (8080, False)


def test_empty_user_url_password_is_secret() -> None:
    # sharpit widening of SecretValueDetector: an empty user still carries a password (redis://:pw@host)
    assert is_secret_value("redis://:pw@host:6379/0")
    assert Masker(M, True).mask("APP_CACHE", "redis://:redispw@localhost:6379/0") == (MASK, True)
    assert mask_user_info("redis://:pw@host:6379/0") == f"redis://{MASK}@host:6379/0"
    assert mask_uri("redis://:pw@host:6379/0") == f"redis://{MASK}@host:6379/0"
