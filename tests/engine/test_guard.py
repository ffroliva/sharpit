"""Request guard tests (port of BootUI ``LocalhostGuardTests`` and the decision cases of the API filters).

Case list, one label per Java test (``same`` = outcome unchanged, ``inverted`` = sharpit deviation,
``dropped`` = reason given).

LocalhostGuardTests
- same: allowsLoopbackIpv4, allowsLoopbackIpv6, rejectsNonLoopbackSource, rejectsUnknownRemoteAddress,
  rejectsBlankRemoteAddress, rejectsNullRemoteAddress, rejectsWildcardIpv4Source,
  rejectsWildcardIpv6Source, rejectsRebindingHostHeader, allowsLoopbackHostHeaderWithPort,
  allowsBracketedIpv6HostHeader, allowsConfiguredAllowedHost, allowsBlankHostHeader, allowsMissingHostHeader,
  allowsHostHeaderCaseInsensitively, allowsLoopbackIpv4HostHeaderWithoutPort, allowsExpandedIpv6LoopbackHostHeader,
  allowsAllowedHostWithEmptyPort, allowsConfiguredIpv6ZoneHostHeader, rejectsHostHeaderThatIsOnlyAColon,
  rejectsHostHeaderWithTrailingJunkAfterIpv6Brackets, rejectsHostHeaderWithUnclosedIpv6Bracket,
  rejectsHostHeaderWithEmptyIpv6Brackets, rejectsBracketedNonIpv6HostHeader, rejectsUnbracketedIpv6HostHeader,
  rejectsHostHeaderWithNonNumericPort, rejectsHostHeaderWithEmbeddedWhitespace, rejectsHostHeaderWithUserInfo,
  rejectsHostHeaderCarryingAScheme, rejectsHostHeaderCarryingAPath,
  rejectsMalformedHostHeaderEvenWhenAllowListIsConfigured, rejectsMalformedHostHeaderWithTheCanonicalHostMessage,
  rejectsMalformedHostHeaderBeforeTheCrossSiteWriteCheck, stillReportsTheSourceRejectionWhenTheHostIsAlsoMalformed,
  rejectsMalformedHostHeaderUnderAllowNonLocalhost, parsesWellFormedHostHeaders, reportsMalformedHostHeadersAsUnusable,
  parsesOriginHeadersThroughTheSameAuthorityParser, allowsSameOriginStateChangingRequest,
  allowsSameOriginStateChangingRequestWithTrailingSlashOrigin, allowsStateChangingRequestWithoutOrigin,
  allowsTrustedSourceRangeWithAcceptableHost, rejectsTrustedSourceRangeWithDisallowedHost,
  rejectsSourceOutsideTrustedRange, allowsTrustedIpv6SourceRange, autoTrustsContainerGatewayWhenInContainer,
  autoDoesNotTrustContainerGatewayWhenNotInContainer (not in a container = detector returns None),
  onTrustsDetectedGatewayEvenWhenNotInContainer (at decide level, gateway passed in; the sharpit detector itself
  returns None outside a container, see report), offNeverTrustsContainerGateway,
  doesNotTrustNonGatewaySourceWhenInContainer, stillRejectsDisallowedHostFromTrustedGateway,
  allowsViteProxyStateChangingRequestAcrossPorts,
  directTrustReportsNoGatewayTrust (outcome only; sharpit returns no Allow detail object).
- inverted (message changed: still 403, body is "sharpit rejected a cross-site request."):
  allowNonLocalhostBypassesOnlySourceCheck, rejectsMalformedOriginOnStateChangingRequest,
  rejectsCrossSiteOriginOnStateChangingRequest, rejectsOpaqueOriginOnStateChangingRequest,
  rejectsSecFetchSiteCrossSiteOnStateChangingRequest, rejectsCrossSiteWriteFromTrustedSourceRange,
  stillRejectsCrossSiteWriteFromTrustedGateway, rejectsOriginWriteWhenHostHeaderIsBlank,
  rejectsOriginWriteWhenHostHeaderIsMissing.
- inverted: allowsCrossSiteOriginOnSafeMethod (GET + foreign Origin now 403),
  exposesExactCanonicalRejectionMessages (cross-site message is "sharpit rejected a cross-site request.";
  the other two are BootUI's text with BootUI->sharpit and bootui.<prop>->SHARPIT_<PROP>).
- dropped: autoTrustsDockerDesktopGatewayAlongsideRouteTableGateway (needs the gateway.docker.internal DNS lookup;
  not supported, spec 7.5). The Allow.trustedViaGateway()/trustedGateway() detail assertions inside
  autoTrustsContainerGatewayWhenInContainer and directTrustReportsNoGatewayTrust (no Allow object in sharpit).

LocalhostOnlyFilterTests (servlet mirror of the cases above; only the extra one is ported)
- same: ignoresMalformedTrustedProxyEntries.
- dropped: skipsFilterForNonBootUiPaths (request scoping, Task 6 ASGI tests);
  autoTrustsDockerDesktopGatewayResolvedViaDnsNotInRouteTable, alsoTrustsRouteTableGatewayAlongsideDockerDesktopGateway
  (DNS). The remaining methods duplicate LocalhostGuardTests cases already listed.

CidrRangeTests (trusted-proxies parsing, exercised through decide_guard)
- same: matchesAddressInsideIpv4Range, rejectsAddressOutsideIpv4Range, matchesAddressInsideIpv6Range,
  doesNotMatchAcrossAddressFamilies, treatsBareAddressAsSingleHost, returnsNullForBlankOrNullInput,
  returnsNullForMalformedEntries (malformed entries never widen access).

ApiTokenAuthenticatorTests
- same: trustedSourcesDoNotRequireAuthentication, untrustedSourcesRequireTheBearerTokenOrSessionCookie,
  generatesAUrlSafe256BitTokenWhenNoneIsConfigured, configuredTokensAreNotMarkedAsGenerated.

ApiAuthenticationFilterTests (decision cases here; 401 HTTP shape, auth/session 204 and Set-Cookie in Task 6)
- same: loopbackApiRequestsDoNotRequireAuthentication, nonLoopbackApiRequestsRequireAuthentication (status, body,
  challenge header), sessionCookieAuthenticatesSubsequentRequests, staticUiAndApplicationRequestsAreNotAuthenticated
  (shell/assets only; application paths never reach sharpit), sourcesTrustedViaTrustedProxiesDoNotRequireAuthentication.
- moved to Task 6: validBearerTokenCreatesAnHttpOnlyBrowserSession,
  sessionCookieIncludesTheServletContextAndConfiguredApiPath.

PanelAccessFilterTests
- same: allowsEnabledPanelReadRequest, blocksDisabledPanelReadRequest, blocksDisabledPanelActionRequest,
  allowsReadOnlyPanelReadRequest, blocksReadOnlyPanelActionRequest (on loggers: config is not action-capable in the
  MVP), globalReadOnlyBlocksActionCapablePanelActions (MVP action-capable panels),
  globalReadOnlyBlocksCatalogedNonPanelBrowserWrites (dismissed-rules),
  globalReadOnlyDoesNotBlockReadOnlyPanelWithoutActions (on beans), overviewShellEndpointIsNeverGatedByPanelToggle,
  skipsCorePanelMetadataEndpoint.
- dropped: perPanelReadOnlyBlocksPentestingScanAction, perPanelReadOnlyAllowsPentestingReportRead (no pentesting
  panel), skipsOtlpIngestionEndpoint (no OTLP), honorsCustomApiPathAndContextPath (path scoping, Task 6).

ContainerGatewayDetectorTests
- same: parsesDockerDesktopGateway, parsesDockerEngineBridgeGateway, returnsEmptyWhenNoDefaultRoute,
  returnsEmptyWhenDefaultRouteHasNoGateway, returnsEmptyForMalformedRows, returnsEmptyForMissingRouteFile,
  isInContainerWhenMarkerFileExists, isNotInContainerWhenNoMarkerAndNoCgroupHint.
- dropped: isInContainerWhenCgroupMentionsDocker, isInContainerWhenCgroupMentionsKubepods,
  isNotInContainerWhenCgroupHasNoContainerHint (brief: container = marker files only; fewer trust grants),
  resolvesDockerDesktopGatewayIpv4, resolvesDockerDesktopGatewayOnGatewayHostNameOnly,
  keepsBothIpv4AndIpv6DockerDesktopGateways, returnsEmptyWhenDockerDesktopGatewayDoesNotResolve,
  ignoresLoopbackDockerDesktopGatewayResolution (DNS, spec 7.5).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sharpit.engine.guard import (
    SESSION_COOKIE,
    Denial,
    RequestFacts,
    decide_guard,
    detect_container_gateway,
    extract_origin_host,
    extract_request_host,
    is_trusted_source,
    remote_access_configured,
    resolve_token,
)
from sharpit.settings import PanelSettings, SharpitSettings

SOURCE_MSG = (
    "sharpit is restricted to loopback requests. Set SHARPIT_ALLOW_NON_LOCALHOST=true to override, "
    "add a trusted source range to SHARPIT_TRUSTED_PROXIES, or (when running in a container) "
    "set SHARPIT_TRUST_CONTAINER_GATEWAY=AUTO to trust the auto-detected container gateway."
)
HOST_MSG = "sharpit rejected an unrecognized Host header. Add it to SHARPIT_ALLOWED_HOSTS to allow this hostname."
CROSS_MSG = "sharpit rejected a cross-site request."
TOKEN = "test-token"
GATEWAY = "192.168.65.1"

SOURCE = Denial(403, {"error": SOURCE_MSG})
HOST = Denial(403, {"error": HOST_MSG})
CROSS = Denial(403, {"error": CROSS_MSG})
AUTH = Denial(
    401,
    {"error": "sharpit authentication required"},
    (("WWW-Authenticate", 'Bearer realm="sharpit"'), ("Cache-Control", "no-store")),
)


def facts(
    method: str = "GET",
    peer: str | None = "127.0.0.1",
    host: str | None = None,
    origin: str | None = None,
    sec_fetch_site: str | None = None,
    api: str | None = None,
    **extra: str,
) -> RequestFacts:
    headers = {k.replace("_", "-"): v for k, v in extra.items()}
    for key, value in (("host", host), ("origin", origin), ("sec-fetch-site", sec_fetch_site)):
        if value is not None:
            headers[key] = value
    return RequestFacts(method=method, peer=peer, headers=headers, api_sub_path=api)


def get(peer: str | None, host: str | None) -> RequestFacts:
    return facts("GET", peer, host)


def post(peer: str | None, host: str | None, origin: str | None, sec_fetch_site: str | None) -> RequestFacts:
    return facts("POST", peer, host, origin, sec_fetch_site)


def decide(
    f: RequestFacts, settings: SharpitSettings | None = None, token: str | None = TOKEN, gateway: str | None = None
) -> Denial | None:
    return decide_guard(f, settings or SharpitSettings(), token, gateway)


ALLOW_NON_LOCALHOST = SharpitSettings(allow_non_localhost=True)


def allowed_hosts(*hosts: str) -> SharpitSettings:
    return SharpitSettings(allowed_hosts=hosts)


def trusted_range(*cidrs: str) -> SharpitSettings:
    return SharpitSettings(trusted_proxies=cidrs)


def gateway_mode(mode: str) -> SharpitSettings:
    return SharpitSettings(trust_container_gateway=mode)


# --- Trusted source -------------------------------------------------------------------------------------------------


# ported: LocalhostGuardTests.allowsLoopbackIpv4
def test_allows_loopback_ipv4():
    assert decide(get("127.0.0.1", None)) is None


# ported: LocalhostGuardTests.allowsLoopbackIpv6
def test_allows_loopback_ipv6():
    assert decide(get("::1", None)) is None


# ported: LocalhostGuardTests.rejectsNonLoopbackSource
def test_rejects_non_loopback_source():
    assert decide(get("192.168.65.1", "localhost:8080")) == SOURCE


# ported: LocalhostGuardTests.allowNonLocalhostBypassesOnlySourceCheck
def test_allow_non_localhost_bypasses_only_source_check():
    assert decide(get("203.0.113.5", "localhost:8080"), ALLOW_NON_LOCALHOST) is None
    assert decide(get("203.0.113.5", "attacker.example.com"), ALLOW_NON_LOCALHOST) == HOST
    cross = post("203.0.113.5", "localhost:8080", "https://attacker.example.com", "cross-site")
    assert decide(cross, ALLOW_NON_LOCALHOST) == CROSS


# ported: LocalhostGuardTests.rejectsUnknownRemoteAddress
def test_rejects_unknown_remote_address():
    assert decide(get("not-an-address", None)) == SOURCE


# ported: LocalhostGuardTests.rejectsBlankRemoteAddress
def test_rejects_blank_remote_address():
    assert decide(get("", None)) == SOURCE


# ported: LocalhostGuardTests.rejectsNullRemoteAddress
def test_rejects_null_remote_address():
    assert decide(get(None, None)) == SOURCE


# ported: LocalhostGuardTests.rejectsWildcardIpv4Source
def test_rejects_wildcard_ipv4_source():
    assert decide(get("0.0.0.0", None)) == SOURCE


# ported: LocalhostGuardTests.rejectsWildcardIpv6Source
def test_rejects_wildcard_ipv6_source():
    assert decide(get("::", None)) == SOURCE


@pytest.mark.parametrize("peer", [" 127.0.0.1", "127.0.0.1 ", "localhost", "127.1"])
def test_peer_must_be_a_plain_ip_literal(peer: str):
    # No trimming, no names, no legacy shorthand: nothing here may resolve or guess.
    assert decide(get(peer, None)) == SOURCE


def test_ipv4_mapped_loopback_is_loopback():
    # Java's InetAddress unwraps ::ffff:127.0.0.1 to 127.0.0.1; a dual-stack server reports local IPv4 peers this way.
    assert decide(get("::ffff:127.0.0.1", None)) is None
    assert decide(get("::ffff:10.0.0.5", None)) == SOURCE


def test_xff_with_no_trusted_proxies_is_untrusted():
    assert decide(facts(peer="127.0.0.1", x_forwarded_for="127.0.0.1")) == SOURCE


@pytest.mark.parametrize("header", ["forwarded", "x-forwarded-for", "x-real-ip"])
def test_any_forwarded_header_makes_source_untrusted(header: str):
    f = RequestFacts("GET", "127.0.0.1", {header: "127.0.0.1"}, None)
    assert is_trusted_source(f, SharpitSettings(), None) is False
    assert is_trusted_source(f, trusted_range("10.0.0.0/8"), None) is False  # loopback grant never applies
    in_range = RequestFacts("GET", "10.0.0.5", {header: "127.0.0.1"}, None)
    assert is_trusted_source(in_range, trusted_range("10.0.0.0/8"), None) is True  # the range still trusts


def test_xff_loopback_denied_even_with_trusted_proxies():
    # Review fix: uvicorn --proxy-headers may have rewritten the peer to 127.0.0.1 from a spoofed X-Forwarded-For.
    f = RequestFacts("GET", "127.0.0.1", {"host": "localhost", "x-forwarded-for": "127.0.0.1"}, "/overview")
    assert decide_guard(f, trusted_range("10.0.0.0/8"), TOKEN, None) == SOURCE


def test_forwarded_header_denies_gateway_grant():
    f = RequestFacts("GET", GATEWAY, {"x-forwarded-for": GATEWAY}, None)
    s = SharpitSettings(trust_container_gateway="AUTO", trusted_proxies=("10.0.0.0/8",))
    assert is_trusted_source(f, s, GATEWAY) is False


@pytest.mark.parametrize("mode", ["auto", "Auto", "on"])
def test_gateway_mode_is_case_insensitive(mode: str):
    assert decide(get(GATEWAY, "localhost:8080"), gateway_mode(mode), gateway=GATEWAY) is None


def test_forwarded_header_under_allow_non_localhost_requires_token():
    f = facts(peer="127.0.0.1", host="localhost:8000", api="/overview", x_forwarded_for="203.0.113.5")
    assert decide(f, ALLOW_NON_LOCALHOST) == AUTH
    assert (
        decide(
            facts(peer="127.0.0.1", api="/overview", x_real_ip="1.2.3.4", authorization=f"Bearer {TOKEN}"),
            ALLOW_NON_LOCALHOST,
        )
        is None
    )


# --- Host allow-list ------------------------------------------------------------------------------------------------


# ported: LocalhostGuardTests.rejectsRebindingHostHeader
def test_rejects_rebinding_host_header():
    assert decide(get("127.0.0.1", "attacker.example.com")) == HOST


@pytest.mark.parametrize(
    ("peer", "host", "settings"),
    [
        ("127.0.0.1", "localhost:8080", None),  # ported: LocalhostGuardTests.allowsLoopbackHostHeaderWithPort
        ("::1", "[::1]:8080", None),  # ported: LocalhostGuardTests.allowsBracketedIpv6HostHeader
        (
            "127.0.0.1",
            "app.local:8080",
            allowed_hosts("app.local"),
        ),  # ported: LocalhostGuardTests.allowsConfiguredAllowedHost
        ("127.0.0.1", "   ", None),  # ported: LocalhostGuardTests.allowsBlankHostHeader
        ("127.0.0.1", None, None),  # ported: LocalhostGuardTests.allowsMissingHostHeader
        ("127.0.0.1", "LocalHost:8080", None),  # ported: LocalhostGuardTests.allowsHostHeaderCaseInsensitively
        ("127.0.0.1", "127.0.0.1", None),  # ported: LocalhostGuardTests.allowsLoopbackIpv4HostHeaderWithoutPort
        ("::1", "[0:0:0:0:0:0:0:1]:8080", None),  # ported: LocalhostGuardTests.allowsExpandedIpv6LoopbackHostHeader
        ("127.0.0.1", "localhost:", None),  # ported: LocalhostGuardTests.allowsAllowedHostWithEmptyPort
        # ported: LocalhostGuardTests.allowsConfiguredIpv6ZoneHostHeader
        ("127.0.0.1", "[fe80::1%25eth0]:8080", allowed_hosts("fe80::1%25eth0")),
    ],
)
def test_allowed_hosts(peer: str, host: str | None, settings: SharpitSettings | None):
    assert decide(get(peer, host), settings) is None


@pytest.mark.parametrize(
    ("peer", "host"),
    [
        ("127.0.0.1", ":"),  # ported: LocalhostGuardTests.rejectsHostHeaderThatIsOnlyAColon
        ("127.0.0.1", "[::1]junk"),  # ported: LocalhostGuardTests.rejectsHostHeaderWithTrailingJunkAfterIpv6Brackets
        ("127.0.0.1", "[::1"),  # ported: LocalhostGuardTests.rejectsHostHeaderWithUnclosedIpv6Bracket
        ("127.0.0.1", "[]"),  # ported: LocalhostGuardTests.rejectsHostHeaderWithEmptyIpv6Brackets
        ("127.0.0.1", "[localhost]:8080"),  # ported: LocalhostGuardTests.rejectsBracketedNonIpv6HostHeader
        ("::1", "::1"),  # ported: LocalhostGuardTests.rejectsUnbracketedIpv6HostHeader
        ("127.0.0.1", "localhost:80x"),  # ported: LocalhostGuardTests.rejectsHostHeaderWithNonNumericPort
        ("127.0.0.1", "local host"),  # ported: LocalhostGuardTests.rejectsHostHeaderWithEmbeddedWhitespace
        ("127.0.0.1", "localhost@evil.example.com"),  # ported: LocalhostGuardTests.rejectsHostHeaderWithUserInfo
        ("127.0.0.1", "http://localhost:8080"),  # ported: LocalhostGuardTests.rejectsHostHeaderCarryingAScheme
        ("127.0.0.1", "localhost:8080/@evil.example.com"),  # ported: LocalhostGuardTests.rejectsHostHeaderCarryingAPath
    ],
)
def test_malformed_hosts_rejected(peer: str, host: str):
    assert decide(get(peer, host)) == HOST


@pytest.mark.parametrize("host", ["\u0000", " ", "　", " \u0000 "])
def test_odd_blank_host_is_present_and_rejected(host: str):
    # Only ASCII whitespace counts as an absent Host; anything else must parse, and these do not.
    assert decide(get("127.0.0.1", host)) == HOST


def test_odd_blank_origin_is_cross_site():
    assert decide(facts("GET", "127.0.0.1", "localhost:8000", " ")) == CROSS
    assert decide(facts("GET", "127.0.0.1", "localhost:8000", " \t ")) is None


# ported: LocalhostGuardTests.rejectsMalformedHostHeaderEvenWhenAllowListIsConfigured
def test_rejects_malformed_host_even_when_allow_list_configured():
    assert decide(get("127.0.0.1", ":"), allowed_hosts("localhost", "app.local")) == HOST


# ported: LocalhostGuardTests.rejectsMalformedHostHeaderWithTheCanonicalHostMessage
def test_rejects_malformed_host_with_canonical_message():
    denial = decide(get("127.0.0.1", "[::1]junk"))
    assert denial is not None and denial.body == {"error": HOST_MSG}


# ported: LocalhostGuardTests.rejectsMalformedHostHeaderBeforeTheCrossSiteWriteCheck
def test_rejects_malformed_host_before_cross_site_check():
    assert decide(post("127.0.0.1", ":", "http://evil.example.com", "cross-site")) == HOST


# ported: LocalhostGuardTests.stillReportsTheSourceRejectionWhenTheHostIsAlsoMalformed
def test_source_rejection_reported_before_malformed_host():
    assert decide(get("192.168.65.1", ":")) == SOURCE


# ported: LocalhostGuardTests.rejectsMalformedHostHeaderUnderAllowNonLocalhost
def test_rejects_malformed_host_under_allow_non_localhost():
    assert decide(get("203.0.113.5", "[::1]junk"), ALLOW_NON_LOCALHOST) == HOST


# ported: LocalhostGuardTests.rejectsMalformedOriginOnStateChangingRequest
def test_rejects_malformed_origin_on_state_changing_request():
    assert decide(post("127.0.0.1", "localhost:8080", "http://local host:8080", None)) == CROSS


# --- Authority parsing ----------------------------------------------------------------------------------------------


# ported: LocalhostGuardTests.parsesWellFormedHostHeaders
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("localhost", "localhost"),
        ("localhost:8080", "localhost"),
        ("LOCALHOST:8080", "localhost"),
        ("  localhost:8080  ", "localhost"),
        ("127.0.0.1:8080", "127.0.0.1"),
        ("[::1]", "::1"),
        ("[::1]:8080", "::1"),
        ("[0:0:0:0:0:0:0:1]:8080", "0:0:0:0:0:0:0:1"),
        ("[::ffff:127.0.0.1]:8080", "::ffff:127.0.0.1"),
        ("[fe80::1%25eth0]:8080", "fe80::1%25eth0"),
        ("[fe80::1%eth0]", "fe80::1%eth0"),
        ("my_app-1.local:8080", "my_app-1.local"),
        ("xn--mnchen-3ya.local", "xn--mnchen-3ya.local"),
        ("localhost:", "localhost"),
    ],
)
def test_parses_well_formed_host_headers(value: str, expected: str):
    assert extract_request_host(value) == expected


# ported: LocalhostGuardTests.reportsMalformedHostHeadersAsUnusable
@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        ":",
        ":8080",
        "/path",
        "[::1]junk",
        "[::1]:8080junk",
        "[::1",
        "[]",
        "[]:8080",
        "[localhost]",
        "[::1%]",
        "::1",
        "localhost:80x",
        "localhost:8080:9090",
        "local host",
        "localhost@evil.example.com",
        "local\u0000host",
        "http://localhost:8080",
        "localhost:8080/path",
        "localhost/@evil.example.com",
        "löcalhost",  # non-ASCII letters are not hostname characters (Java checks ASCII ranges)
        " localhost",  # Java trim() only strips <= U+0020, so a no-break space stays and is rejected
    ],
)
def test_reports_malformed_host_headers_as_unusable(value: str | None):
    assert extract_request_host(value) is None


# ported: LocalhostGuardTests.parsesOriginHeadersThroughTheSameAuthorityParser
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://localhost:8080", "localhost"),
        ("https://localhost:8080/", "localhost"),
        ("http://[::1]:8080/api", "::1"),
        ("http://localhost:5173", "localhost"),
        (None, None),
        ("   ", None),
        ("null", None),
        ("  NULL  ", None),
        ("http://", None),
        ("http://local host:8080", None),
        ("http://[::1]junk", None),
    ],
)
def test_parses_origin_headers(value: str | None, expected: str | None):
    assert extract_origin_host(value) == expected


# --- Cross-site (every method in sharpit) ---------------------------------------------------------------------------


# ported: LocalhostGuardTests.rejectsCrossSiteOriginOnStateChangingRequest
def test_rejects_cross_site_origin_on_state_changing_request():
    assert decide(post("127.0.0.1", "localhost:8080", "http://evil.example.com", None)) == CROSS


# ported: LocalhostGuardTests.allowsSameOriginStateChangingRequest
def test_allows_same_origin_state_changing_request():
    assert decide(post("127.0.0.1", "localhost:8080", "http://localhost:8080", None)) is None


# ported: LocalhostGuardTests.allowsSameOriginStateChangingRequestWithTrailingSlashOrigin
def test_allows_same_origin_with_trailing_slash_origin():
    assert decide(post("127.0.0.1", "localhost:8080", "http://localhost:8080/", None)) is None


# ported: LocalhostGuardTests.allowsStateChangingRequestWithoutOrigin
def test_allows_state_changing_request_without_origin():
    assert decide(post("127.0.0.1", "localhost:8080", None, None)) is None


# ported: LocalhostGuardTests.rejectsOpaqueOriginOnStateChangingRequest
def test_rejects_opaque_origin_on_state_changing_request():
    assert decide(post("127.0.0.1", "localhost:8080", "null", None)) == CROSS


# ported: LocalhostGuardTests.rejectsSecFetchSiteCrossSiteOnStateChangingRequest
def test_rejects_sec_fetch_site_cross_site_on_state_changing_request():
    assert decide(post("127.0.0.1", "localhost:8080", None, "cross-site")) == CROSS
    assert decide(post("127.0.0.1", "localhost:8080", None, "Cross-Site")) == CROSS
    assert decide(post("127.0.0.1", "localhost:8080", None, "same-origin")) is None


# ported: LocalhostGuardTests.allowsCrossSiteOriginOnSafeMethod (inverted: sharpit rejects cross-site on every method)
def test_cross_site_origin_on_safe_method_rejected():
    for method in ("GET", "HEAD", "OPTIONS"):
        assert decide(facts(method, "127.0.0.1", "localhost:8080", "http://evil.example.com")) == CROSS


def test_cross_site_get_rejected():
    assert decide(facts("GET", "127.0.0.1", "localhost:8000", sec_fetch_site="cross-site")) == CROSS


def test_origin_mismatch_get_rejected():
    assert decide(facts("GET", "127.0.0.1", "localhost:8000", "http://evil.example.com")) == CROSS
    assert decide(facts("GET", "127.0.0.1", "localhost:8000", "null")) == CROSS


def test_same_origin_vite_port_allowed():
    assert decide(facts("GET", "127.0.0.1", "localhost:8000", "http://localhost:5173")) is None


# ported: LocalhostGuardTests.allowsViteProxyStateChangingRequestAcrossPorts
def test_allows_vite_proxy_state_changing_request_across_ports():
    assert decide(post("127.0.0.1", "localhost:8080", "http://localhost:5173", None)) is None


# ported: LocalhostGuardTests.rejectsOriginWriteWhenHostHeaderIsBlank
def test_rejects_origin_write_when_host_blank():
    assert decide(post("127.0.0.1", "   ", "http://localhost:8080", None)) == CROSS


# ported: LocalhostGuardTests.rejectsOriginWriteWhenHostHeaderIsMissing
def test_rejects_origin_write_when_host_missing():
    assert decide(post("127.0.0.1", None, "http://localhost:8080", None)) == CROSS


# ported: LocalhostGuardTests.exposesExactCanonicalRejectionMessages (inverted: cross-site text is sharpit's)
def test_exposes_exact_canonical_rejection_messages():
    assert decide(get("192.168.65.1", "localhost:8080")) == Denial(403, {"error": SOURCE_MSG})
    assert decide(get("127.0.0.1", "attacker.example.com")) == Denial(403, {"error": HOST_MSG})
    cross = decide(post("127.0.0.1", "localhost:8080", "http://evil.example.com", None))
    assert cross == Denial(403, {"error": "sharpit rejected a cross-site request."})


# --- Trusted proxies (CIDR ranges) ----------------------------------------------------------------------------------


# ported: LocalhostGuardTests.allowsTrustedSourceRangeWithAcceptableHost
def test_allows_trusted_source_range_with_acceptable_host():
    assert decide(get("172.17.0.1", "localhost:8080"), trusted_range("172.16.0.0/12")) is None


# ported: LocalhostGuardTests.rejectsTrustedSourceRangeWithDisallowedHost
def test_rejects_trusted_source_range_with_disallowed_host():
    assert decide(get("172.17.0.1", "attacker.example.com"), trusted_range("172.16.0.0/12")) == HOST


# ported: LocalhostGuardTests.rejectsCrossSiteWriteFromTrustedSourceRange
def test_rejects_cross_site_write_from_trusted_source_range():
    f = post("172.17.0.1", "localhost:8080", "http://evil.example.com", None)
    assert decide(f, trusted_range("172.16.0.0/12")) == CROSS


# ported: LocalhostGuardTests.rejectsSourceOutsideTrustedRange
def test_rejects_source_outside_trusted_range():
    assert decide(get("10.0.0.5", "localhost:8080"), trusted_range("172.16.0.0/12")) == SOURCE


# ported: LocalhostGuardTests.allowsTrustedIpv6SourceRange
def test_allows_trusted_ipv6_source_range():
    assert decide(get("fd00::1234", "localhost:8080"), trusted_range("fd00::/8")) is None


# ported: LocalhostOnlyFilterTests.ignoresMalformedTrustedProxyEntries
def test_ignores_malformed_trusted_proxy_entries():
    assert decide(get("172.17.0.1", "localhost:8080"), trusted_range("not-a-cidr", "172.16.0.0/12", "  ")) is None


@pytest.mark.parametrize(
    ("cidr", "peer", "trusted"),
    [
        ("172.16.0.0/12", "172.17.0.1", True),  # ported: CidrRangeTests.matchesAddressInsideIpv4Range
        ("172.16.0.0/12", "172.31.255.255", True),
        ("172.16.0.0/12", "10.0.0.1", False),  # ported: CidrRangeTests.rejectsAddressOutsideIpv4Range
        ("172.16.0.0/12", "192.168.0.1", False),
        ("fd00::/8", "fd00::1234", True),  # ported: CidrRangeTests.matchesAddressInsideIpv6Range
        ("172.16.0.0/12", "fd00::1", False),  # ported: CidrRangeTests.doesNotMatchAcrossAddressFamilies
        ("172.17.0.1", "172.17.0.1", True),  # ported: CidrRangeTests.treatsBareAddressAsSingleHost
        ("172.17.0.1", "172.17.0.2", False),
        ("[fd00::1]", "fd00::1", True),  # Java strips brackets from an IPv6 literal
        ("   ", "10.0.0.1", False),  # ported: CidrRangeTests.returnsNullForBlankOrNullInput
        ("not-a-cidr", "10.0.0.1", False),  # ported: CidrRangeTests.returnsNullForMalformedEntries
        ("172.16.0.0/abc", "172.16.0.1", False),
        ("172.16.0.0/40", "172.16.0.1", False),
        ("example.com/24", "10.0.0.1", False),
        ("0.0.0.0/-1", "10.0.0.1", False),
        ("10.0.0.0/ 8", "10.0.0.1", True),  # Java trims the prefix part
        ("10.0.0.0/+8", "10.0.0.1", False),  # a signed prefix is not a plain number (narrower than parseInt)
        ("fe80::1%eth0/64", "fe80::1", False),  # zone ids are not numeric literals
        ("*", "10.0.0.1", False),
    ],
)
def test_trusted_proxy_parsing(cidr: str, peer: str, trusted: bool):
    assert is_trusted_source(facts(peer=peer), trusted_range(cidr), None) is trusted


# --- Container gateway ----------------------------------------------------------------------------------------------


# ported: LocalhostGuardTests.autoTrustsContainerGatewayWhenInContainer
def test_auto_trusts_container_gateway_when_in_container():
    assert decide(get(GATEWAY, "localhost:8080"), gateway_mode("AUTO"), gateway=GATEWAY) is None


# ported: LocalhostGuardTests.autoDoesNotTrustContainerGatewayWhenNotInContainer
def test_auto_does_not_trust_gateway_when_not_in_container():
    assert decide(get(GATEWAY, "localhost:8080"), gateway_mode("AUTO"), gateway=None) == SOURCE


# ported: LocalhostGuardTests.onTrustsDetectedGatewayEvenWhenNotInContainer
def test_on_trusts_detected_gateway():
    assert decide(get(GATEWAY, "localhost:8080"), gateway_mode("ON"), gateway=GATEWAY) is None


# ported: LocalhostGuardTests.offNeverTrustsContainerGateway
def test_off_never_trusts_container_gateway():
    assert decide(get(GATEWAY, "localhost:8080"), gateway_mode("OFF"), gateway=GATEWAY) == SOURCE


# ported: LocalhostGuardTests.doesNotTrustNonGatewaySourceWhenInContainer
def test_does_not_trust_non_gateway_source():
    assert decide(get("192.168.65.99", "localhost:8080"), gateway_mode("AUTO"), gateway=GATEWAY) == SOURCE


# ported: LocalhostGuardTests.stillRejectsDisallowedHostFromTrustedGateway
def test_still_rejects_disallowed_host_from_trusted_gateway():
    assert decide(get(GATEWAY, "attacker.example.com"), gateway_mode("AUTO"), gateway=GATEWAY) == HOST


# ported: LocalhostGuardTests.stillRejectsCrossSiteWriteFromTrustedGateway
def test_still_rejects_cross_site_write_from_trusted_gateway():
    f = post(GATEWAY, "localhost:8080", "http://evil.example.com", None)
    assert decide(f, gateway_mode("AUTO"), gateway=GATEWAY) == CROSS


# ported: LocalhostGuardTests.directTrustReportsNoGatewayTrust (outcome only)
def test_direct_trust_allows():
    assert decide(get("127.0.0.1", "localhost:8080")) is None


def test_unparseable_gateway_never_trusts():
    assert decide(get(GATEWAY, "localhost:8080"), gateway_mode("ON"), gateway="not-an-ip") == SOURCE


ROUTE_HEADER = "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT"


def _route(tmp_path: Path, *rows: str) -> Path:
    path = tmp_path / "route"
    path.write_text("\n".join([ROUTE_HEADER, *rows]) + "\n")
    return path


def _in() -> bool:
    return True


def _out() -> bool:
    return False


# ported: ContainerGatewayDetectorTests.parsesDockerDesktopGateway
def test_parses_docker_desktop_gateway(tmp_path: Path):
    route = _route(
        tmp_path,
        "eth0\t00000000\t0141A8C0\t0003\t0\t0\t0\t00000000\t0\t0\t0",
        "eth0\t0041A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0",
    )
    assert detect_container_gateway(route, _in) == "192.168.65.1"


# ported: ContainerGatewayDetectorTests.parsesDockerEngineBridgeGateway
def test_parses_docker_engine_bridge_gateway(tmp_path: Path):
    route = _route(tmp_path, "eth0\t00000000\t010011AC\t0003\t0\t0\t0\t00000000\t0\t0\t0")
    assert detect_container_gateway(route, _in) == "172.17.0.1"


# ported: ContainerGatewayDetectorTests.returnsEmptyWhenNoDefaultRoute
def test_returns_none_when_no_default_route(tmp_path: Path):
    route = _route(tmp_path, "eth0\t0041A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0")
    assert detect_container_gateway(route, _in) is None


# ported: ContainerGatewayDetectorTests.returnsEmptyWhenDefaultRouteHasNoGateway
def test_returns_none_when_default_route_has_no_gateway(tmp_path: Path):
    route = _route(tmp_path, "eth0\t00000000\t00000000\t0001\t0\t0\t0\t00000000\t0\t0\t0")
    assert detect_container_gateway(route, _in) is None


# ported: ContainerGatewayDetectorTests.returnsEmptyForMalformedRows
def test_returns_none_for_malformed_rows(tmp_path: Path):
    route = _route(
        tmp_path, "garbage", "eth0\t00000000\tZZZZZZZZ\t0003", "   ", "eth0\t00000000", "eth0\t00000000\t-1A8C0AB"
    )
    assert detect_container_gateway(route, _in) is None


# ported: ContainerGatewayDetectorTests.returnsEmptyForMissingRouteFile
def test_returns_none_for_missing_route_file(tmp_path: Path):
    assert detect_container_gateway(tmp_path / "missing", _in) is None


def test_not_in_container_never_reads_route(tmp_path: Path):
    route = _route(tmp_path, "eth0\t00000000\t010011AC\t0003\t0\t0\t0\t00000000\t0\t0\t0")
    assert detect_container_gateway(route, _out) is None


# ported: ContainerGatewayDetectorTests.isInContainerWhenMarkerFileExists
# ported: ContainerGatewayDetectorTests.isNotInContainerWhenNoMarkerAndNoCgroupHint
def test_container_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from sharpit.engine import guard

    route = _route(tmp_path, "eth0\t00000000\t010011AC\t0003\t0\t0\t0\t00000000\t0\t0\t0")
    marker = tmp_path / ".dockerenv"
    monkeypatch.setattr(guard, "_CONTAINER_MARKERS", (marker, tmp_path / ".containerenv"))
    monkeypatch.setattr(guard.sys, "platform", "linux")
    assert detect_container_gateway(route) is None
    marker.write_text("")
    assert detect_container_gateway(route) == "172.17.0.1"
    monkeypatch.setattr(guard.sys, "platform", "win32")
    assert detect_container_gateway(route) is None


# --- Token ----------------------------------------------------------------------------------------------------------


def _remote(**headers: str) -> RequestFacts:
    return facts(peer="10.0.0.5", host="localhost:8000", api="/overview", **headers)


# ported: ApiTokenAuthenticatorTests.trustedSourcesDoNotRequireAuthentication
# ported: ApiAuthenticationFilterTests.loopbackApiRequestsDoNotRequireAuthentication
def test_trusted_source_needs_no_token():
    assert decide(facts(peer="127.0.0.1", api="/overview")) is None
    assert decide(facts(peer="127.0.0.1", api="/overview"), ALLOW_NON_LOCALHOST) is None
    assert decide(facts(peer="127.0.0.1", api="/overview"), token=None) is None


# ported: ApiAuthenticationFilterTests.nonLoopbackApiRequestsRequireAuthentication
# ported: ApiTokenAuthenticatorTests.untrustedSourcesRequireTheBearerTokenOrSessionCookie
def test_untrusted_source_requires_token():
    s = ALLOW_NON_LOCALHOST
    assert decide(_remote(), s) == AUTH
    assert decide(_remote(authorization="invalid"), s) == AUTH
    assert decide(_remote(authorization="Bearer "), s) == AUTH
    assert decide(_remote(authorization="Bearer wrong-token"), s) == AUTH
    assert decide(_remote(authorization=f"Bearer {TOKEN}x"), s) == AUTH
    assert decide(_remote(authorization=f"Basic {TOKEN}"), s) == AUTH
    assert decide(_remote(authorization=f"Bearer {TOKEN}"), s) is None
    assert decide(_remote(authorization=f"bearer {TOKEN}"), s) is None


# ported: ApiAuthenticationFilterTests.sessionCookieAuthenticatesSubsequentRequests
def test_session_cookie_authenticates():
    s = ALLOW_NON_LOCALHOST
    assert decide(_remote(cookie=f"other=value; {SESSION_COOKIE}={TOKEN}"), s) is None
    assert decide(_remote(cookie=f"{SESSION_COOKIE}=nope"), s) == AUTH
    assert decide(_remote(cookie=f"X{SESSION_COOKIE}={TOKEN}"), s) == AUTH


def test_session_cookie_name():
    assert SESSION_COOKIE == "SHARPIT_SESSION"


def test_missing_server_token_fails_closed():
    assert decide(_remote(authorization="Bearer "), ALLOW_NON_LOCALHOST, token=None) == AUTH
    assert decide(_remote(cookie=f"{SESSION_COOKIE}="), ALLOW_NON_LOCALHOST, token=None) == AUTH


def test_token_compare_is_constant_time(monkeypatch: pytest.MonkeyPatch):
    from sharpit.engine import guard

    calls: list[tuple[bytes, bytes]] = []

    def spy(a: bytes, b: bytes) -> bool:
        calls.append((a, b))
        return a == b

    monkeypatch.setattr(guard.hmac, "compare_digest", spy)
    assert decide(_remote(authorization=f"Bearer {TOKEN}"), ALLOW_NON_LOCALHOST) is None
    assert calls == [(TOKEN.encode(), TOKEN.encode())]


# ported: ApiAuthenticationFilterTests.staticUiAndApplicationRequestsAreNotAuthenticated
def test_shell_and_assets_need_no_token():
    assert decide(facts(peer="10.0.0.5", host="localhost:8000"), ALLOW_NON_LOCALHOST) is None


# ported: ApiAuthenticationFilterTests.sourcesTrustedViaTrustedProxiesDoNotRequireAuthentication
def test_trusted_proxy_source_needs_no_token():
    assert decide(facts(peer="10.0.0.5", api="/overview"), trusted_range("10.0.0.0/24")) is None


def test_auth_session_path_needs_token():
    assert decide(facts("POST", "10.0.0.5", api="/auth/session"), ALLOW_NON_LOCALHOST) == AUTH
    assert (
        decide(facts("POST", "10.0.0.5", api="/auth/session", authorization=f"Bearer {TOKEN}"), ALLOW_NON_LOCALHOST)
        is None
    )


def test_remote_access_configured():
    assert remote_access_configured(SharpitSettings()) is False
    assert remote_access_configured(ALLOW_NON_LOCALHOST) is True
    assert remote_access_configured(trusted_range("not-a-cidr")) is True
    assert remote_access_configured(gateway_mode("AUTO")) is True
    assert remote_access_configured(gateway_mode("ON")) is True


# ported: ApiTokenAuthenticatorTests.generatesAUrlSafe256BitTokenWhenNoneIsConfigured
def test_generates_url_safe_256_bit_token():
    token, generated = resolve_token(ALLOW_NON_LOCALHOST)
    assert generated is True
    assert token is not None and len(token) == 43 and re.fullmatch(r"[A-Za-z0-9_-]+", token)
    assert resolve_token(ALLOW_NON_LOCALHOST)[0] != token


# ported: ApiTokenAuthenticatorTests.configuredTokensAreNotMarkedAsGenerated
def test_configured_token_not_generated():
    assert resolve_token(SharpitSettings(authentication_token=TOKEN, allow_non_localhost=True)) == (TOKEN, False)
    assert resolve_token(SharpitSettings(authentication_token=TOKEN)) == (TOKEN, False)


def test_no_token_without_remote_access():
    assert resolve_token(SharpitSettings()) == (None, False)


# --- Panel access ---------------------------------------------------------------------------------------------------


def _panels(**flags: PanelSettings) -> SharpitSettings:
    return SharpitSettings(panels={k.replace("_", "-"): v for k, v in flags.items()})


def _panel_denial(panel: str, reason: str) -> Denial:
    return Denial(403, {"error": "sharpit panel access denied", "panel": panel, "reason": reason})


RO_GLOBAL = "sharpit is read-only via SHARPIT_READ_ONLY=true"


# ported: PanelAccessFilterTests.allowsEnabledPanelReadRequest
def test_allows_enabled_panel_read():
    assert decide(facts("GET", api="/config")) is None


# ported: PanelAccessFilterTests.blocksDisabledPanelReadRequest
def test_blocks_disabled_panel_read():
    denial = _panel_denial("config", "Panel is disabled via SHARPIT_PANELS_CONFIG_ENABLED=false")
    assert decide(facts("GET", api="/config"), _panels(config=PanelSettings(enabled=False))) == denial


# ported: PanelAccessFilterTests.blocksDisabledPanelActionRequest
def test_blocks_disabled_panel_action():
    denial = decide(facts("POST", api="/loggers/sharpit"), _panels(loggers=PanelSettings(enabled=False)))
    assert denial == _panel_denial("loggers", "Panel is disabled via SHARPIT_PANELS_LOGGERS_ENABLED=false")


def test_panel_disabled_all_methods_403_body():
    s = _panels(mcp_server=PanelSettings(enabled=False))
    expected = _panel_denial("mcp-server", "Panel is disabled via SHARPIT_PANELS_MCP_SERVER_ENABLED=false")
    for method in ("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"):
        assert decide(facts(method, api="/mcp-server"), s) == expected
        assert decide(facts(method, api="/mcp-server/status"), s) == expected
    assert decide(facts("GET", api="/mcp"), s) is None  # /mcp is not under the /mcp-server prefix
    assert decide(facts("GET", api="/mcp-serverx"), s) is None


# ported: PanelAccessFilterTests.allowsReadOnlyPanelReadRequest
def test_allows_read_only_panel_read():
    assert decide(facts("GET", api="/loggers"), _panels(loggers=PanelSettings(read_only=True))) is None


# ported: PanelAccessFilterTests.blocksReadOnlyPanelActionRequest (loggers: config is not action-capable in the MVP)
def test_blocks_read_only_panel_action():
    denial = decide(facts("POST", api="/loggers/root"), _panels(loggers=PanelSettings(read_only=True)))
    assert denial == _panel_denial("loggers", "Panel is read-only via SHARPIT_PANELS_LOGGERS_READ_ONLY=true")


# ported: PanelAccessFilterTests.globalReadOnlyBlocksActionCapablePanelActions
@pytest.mark.parametrize(
    ("method", "path", "panel"),
    [
        ("POST", "/loggers/root", "loggers"),
        ("POST", "/vulnerabilities/scan", "vulnerabilities"),
        ("DELETE", "/vulnerabilities/dismissals/x", "vulnerabilities"),
        ("PUT", "/mcp-server", "mcp-server"),
        ("PATCH", "/mcp-server/enabled", "mcp-server"),
    ],
)
def test_global_read_only_blocks_action_capable_panel_actions(method: str, path: str, panel: str):
    assert decide(facts(method, api=path), SharpitSettings(read_only=True)) == _panel_denial(panel, RO_GLOBAL)


# ported: PanelAccessFilterTests.globalReadOnlyBlocksCatalogedNonPanelBrowserWrites
def test_dismissed_rules_global_read_only():
    s = SharpitSettings(read_only=True)
    expected = _panel_denial("dismissed-rules", RO_GLOBAL)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert decide(facts(method, api="/dismissed-rules"), s) == expected
        assert decide(facts(method, api="/dismissed-rules/abc"), s) == expected
    assert decide(facts("GET", api="/dismissed-rules"), s) is None
    assert decide(facts("POST", api="/dismissed-rules")) is None
    assert decide(facts("POST", api="/dismissed-rulesx"), s) is None


# ported: PanelAccessFilterTests.globalReadOnlyDoesNotBlockReadOnlyPanelWithoutActions
def test_global_read_only_does_not_block_panel_without_actions():
    assert decide(facts("GET", api="/beans"), SharpitSettings(read_only=True)) is None
    assert decide(facts("POST", api="/config"), SharpitSettings(read_only=True)) is None


# ported: PanelAccessFilterTests.overviewShellEndpointIsNeverGatedByPanelToggle
def test_overview_endpoint_never_gated():
    assert decide(facts("GET", api="/overview"), _panels(overview=PanelSettings(enabled=False))) is None


# ported: PanelAccessFilterTests.skipsCorePanelMetadataEndpoint
def test_panels_endpoint_never_gated():
    assert decide(facts("GET", api="/panels"), SharpitSettings(read_only=True)) is None


def test_lower_case_method_is_not_safe():
    # Safe-method matching is exact, as PanelAccessFilter: "get" is not GET, so it cannot slip past read-only.
    assert decide(facts("get", api="/loggers/root"), SharpitSettings(read_only=True)) == _panel_denial(
        "loggers", RO_GLOBAL
    )


def test_panels_are_not_checked_outside_the_api():
    assert decide(facts("GET", api=None), _panels(config=PanelSettings(enabled=False))) is None


def test_missing_panel_id_means_enabled_and_writable():
    assert decide(facts("POST", api="/loggers/root"), SharpitSettings(panels={})) is None


def test_order_cross_site_before_token_before_panel():
    s = SharpitSettings(allow_non_localhost=True, read_only=True)
    f = facts("POST", "10.0.0.5", "localhost:8000", "http://evil.example.com", api="/loggers/root")
    assert decide(f, s) == CROSS
    f = facts("POST", "10.0.0.5", "localhost:8000", api="/loggers/root")
    assert decide(f, s) == AUTH
    f = facts("POST", "10.0.0.5", "localhost:8000", api="/loggers/root", authorization=f"Bearer {TOKEN}")
    assert decide(f, s) == _panel_denial("loggers", RO_GLOBAL)
