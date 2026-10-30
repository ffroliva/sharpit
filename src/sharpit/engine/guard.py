"""Request guard (port of BootUI ``LocalhostGuard``, ``ApiTokenAuthenticator``, ``PanelAccessFilter``).

Order: trusted source -> Host allow-list -> cross-site (every method, and the full origin on API paths: sharpit
deviations) -> token for untrusted sources on API paths -> panel access. Nothing here resolves names or opens sockets.
"""

from __future__ import annotations

import hmac
import ipaddress
import secrets
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

from sharpit.engine.panels import disabled_reason, panel_for_api_path, read_only_reason
from sharpit.settings import PanelSettings, SharpitSettings

SESSION_COOKIE = "SHARPIT_SESSION"

MESSAGE_NON_LOOPBACK_SOURCE = (
    "sharpit is restricted to loopback requests. Set SHARPIT_ALLOW_NON_LOCALHOST=true to override, "
    "add a trusted source range to SHARPIT_TRUSTED_PROXIES, or (when running in a container) "
    "set SHARPIT_TRUST_CONTAINER_GATEWAY=AUTO to trust the auto-detected container gateway."
)
MESSAGE_DISALLOWED_HOST = (
    "sharpit rejected an unrecognized Host header. Add it to SHARPIT_ALLOWED_HOSTS to allow this hostname."
)
MESSAGE_CROSS_SITE = "sharpit rejected a cross-site request."
AUTHENTICATION_REQUIRED_MESSAGE = "sharpit authentication required"
AUTHENTICATION_CHALLENGE = 'Bearer realm="sharpit"'
PANEL_ACCESS_DENIED = "sharpit panel access denied"

_BUILT_IN_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1"})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_FORWARDED_HEADERS = ("forwarded", "x-forwarded-for", "x-real-ip")
_GLOBAL_WRITE_SUBJECTS = {"/dismissed-rules": "dismissed-rules"}  # port of BootUiGlobalWritePolicy
_BEARER = "bearer "
_JAVA_TRIM = "".join(chr(c) for c in range(0x21))  # Java String.trim() strips every char <= U+0020
# Java isBlank() whitespace, minus the Unicode spaces: a header is "absent" only when made of these (fail closed)
_BLANK = frozenset(chr(c) for c in (0x20, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x1F))
_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")
_IPV6_CHARS = frozenset("0123456789abcdefABCDEF:.")
_NUMERIC_IP_CHARS = frozenset("0123456789abcdef:.")
_HEX = frozenset("0123456789abcdefABCDEF")
_CONTAINER_MARKERS = (Path("/.dockerenv"), Path("/run/.containerenv"))
_DEFAULT_ROUTE = "00000000"

_IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
_IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True)
class RequestFacts:
    method: str
    peer: str | None
    headers: Mapping[str, str]  # lower-case keys
    api_sub_path: str | None  # path after api_path; None for the shell and assets
    scheme: str = "http"  # the request's own scheme (ASGI ``scope["scheme"]``)


@dataclass(frozen=True)
class Denial:
    status: int
    body: dict[str, str]
    headers: tuple[tuple[str, str], ...] = ()


# --- Authority parsing (exact port of LocalhostGuard.extractRequestHost / extractOriginHost) -------------------------


def extract_request_host(value: str | None) -> str | None:
    """Lower-cased host of an authority-form ``Host`` value, or None when absent, blank or malformed."""
    if value is None:
        return None
    candidate = value.strip(_JAVA_TRIM)
    return _parse_authority(candidate) if candidate else None


def extract_origin_host(value: str | None) -> str | None:
    """Lower-cased host of an ``Origin`` value; None for the opaque ``null`` origin or anything unparseable."""
    if value is None:
        return None
    candidate = value.strip(_JAVA_TRIM)
    if candidate.lower() == "null":
        return None
    scheme = candidate.find("://")
    if scheme >= 0:
        candidate = candidate[scheme + 3 :]
    slash = candidate.find("/")
    if slash >= 0:
        candidate = candidate[:slash]
    return _parse_authority(candidate) if candidate else None


def _parse_authority(candidate: str) -> str | None:
    parts = _split_authority(candidate)
    return None if parts is None else parts[0]


def _split_authority(candidate: str) -> tuple[str, str] | None:
    """``(lower-cased host, port digits or "")`` of an authority, or None when malformed."""
    if candidate.startswith("["):
        close = candidate.find("]")
        if close < 0:
            return None
        host, port_suffix = candidate[1:close], candidate[close + 1 :]
        if not _is_ipv6_literal(host):
            return None
    else:
        colon = candidate.find(":")
        host, port_suffix = (candidate[:colon], candidate[colon:]) if colon >= 0 else (candidate, "")
        if not _is_registered_name(host):
            return None
    if port_suffix and (port_suffix[0] != ":" or not all("0" <= c <= "9" for c in port_suffix[1:])):
        return None
    return host.lower(), port_suffix[1:]


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin_tuple(scheme: str, authority: str) -> tuple[str, str, int] | None:
    """``(scheme, host, port)`` with the scheme's default port filled in; None when anything is unparseable."""
    parts = _split_authority(authority) if authority else None
    scheme = scheme.lower()
    if parts is None or (not parts[1] and scheme not in _DEFAULT_PORTS):
        return None
    host, port = parts
    return scheme, host, int(port) if port else _DEFAULT_PORTS[scheme]


def _request_origin(facts: RequestFacts) -> tuple[str, str, int] | None:
    host = facts.headers.get("host")
    return None if host is None else _origin_tuple(facts.scheme, host.strip(_JAVA_TRIM))


def _parse_origin(value: str) -> tuple[str, str, int] | None:
    scheme, sep, rest = value.strip(_JAVA_TRIM).partition("://")
    return _origin_tuple(scheme, rest.partition("/")[0]) if sep else None


def _is_registered_name(host: str) -> bool:
    return bool(host) and all(c in _NAME_CHARS for c in host)


def _is_ipv6_literal(host: str) -> bool:
    address, sep, zone_id = host.partition("%")
    if not address or ":" not in address or not all(c in _IPV6_CHARS for c in address):
        return False
    return not sep or _is_registered_name(zone_id.replace("%", ""))


# --- Trusted source -------------------------------------------------------------------------------------------------


def _is_blank(value: str | None) -> bool:
    return value is None or all(c in _BLANK for c in value)


def _parse_ip(value: str | None) -> _IpAddress | None:
    """Numeric IP literal only (never DNS); IPv4-mapped IPv6 unwraps to IPv4, as Java's InetAddress does."""
    if not value:
        return None
    try:
        address = ipaddress.ip_address(value)  # no trimming: Java's getByName rejects padded input too
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


@lru_cache(maxsize=64)
def _trusted_ranges(entries: tuple[str, ...]) -> tuple[_IpNetwork, ...]:
    """Port of ``CidrRange.parse``: an unparseable entry is skipped, so it can never widen access."""
    ranges: list[_IpNetwork] = []
    for entry in entries:
        address, slash, prefix = entry.strip().partition("/")
        address, prefix = address.strip(), prefix.strip()
        if address.startswith("[") and address.endswith("]") and len(address) > 2:
            address = address[1:-1]
        if not _is_numeric_ip_literal(address) or (slash and not (prefix.isascii() and prefix.isdigit())):
            continue
        try:
            network = ipaddress.ip_network(f"{address}/{prefix}" if slash else address, strict=False)
        except ValueError:
            continue
        ranges.append(network)
    return tuple(ranges)


def _is_numeric_ip_literal(value: str) -> bool:
    host = value.lower()
    return bool(host) and all(c in _NUMERIC_IP_CHARS for c in host) and (":" in host or "." in host)


def is_trusted_source(facts: RequestFacts, settings: SharpitSettings, gateway: str | None) -> bool:
    """Loopback, a trusted-proxies range, or the detected container gateway; never via forwarded headers.

    sharpit deviation: with any forwarded header present only a trusted-proxies range can grant trust (never loopback
    or the gateway), because the ASGI server may already have rewritten the peer from those headers.
    """
    forwarded = any(h in facts.headers for h in _FORWARDED_HEADERS)
    if forwarded and not settings.trusted_proxies:
        return False
    address = _parse_ip(facts.peer)
    if address is None:
        return False
    if address.is_loopback and not forwarded:
        return True
    if any(address in network for network in _trusted_ranges(tuple(settings.trusted_proxies))):
        return True
    mode = settings.trust_container_gateway.upper()
    return not forwarded and mode in ("AUTO", "ON") and address == _parse_ip(gateway)


# --- Token ----------------------------------------------------------------------------------------------------------


def remote_access_configured(settings: SharpitSettings) -> bool:
    return (
        settings.allow_non_localhost
        or bool(settings.trusted_proxies)
        or settings.trust_container_gateway.upper() != "OFF"
    )


def resolve_token(settings: SharpitSettings) -> tuple[str | None, bool]:
    """``(token, generated)``: the configured token, else a fresh 256-bit token when remote access is on."""
    configured = settings.authentication_token
    if configured and configured.strip():
        return configured, False
    if remote_access_configured(settings):
        return secrets.token_urlsafe(32), True
    return None, False


def _bearer(header: str | None) -> str | None:
    if header is None or len(header) <= len(_BEARER) or header[: len(_BEARER)].lower() != _BEARER:
        return None
    return header[len(_BEARER) :]


def _session_cookie(header: str | None) -> str | None:
    if not header:
        return None
    prefix = SESSION_COOKIE + "="
    for cookie in header.split(";"):
        candidate = cookie.strip()
        if candidate.startswith(prefix):
            return candidate[len(prefix) :]
    return None


def _matches(token: str, candidate: str | None) -> bool:
    return candidate is not None and hmac.compare_digest(token.encode(), candidate.encode())


def _authorized(facts: RequestFacts, token: str | None) -> bool:
    if not token:
        return False  # no server token: an untrusted source can never authenticate
    return _matches(token, _bearer(facts.headers.get("authorization"))) or _matches(
        token, _session_cookie(facts.headers.get("cookie"))
    )


# --- Decision -------------------------------------------------------------------------------------------------------


def _forbidden(message: str) -> Denial:
    return Denial(403, {"error": message})


def _panel_denied(panel: str, reason: str) -> Denial:
    return Denial(403, {"error": PANEL_ACCESS_DENIED, "panel": panel, "reason": reason})


def _is_cross_site(facts: RequestFacts, request_host: str | None) -> bool:
    if facts.headers.get("sec-fetch-site", "").casefold() == "cross-site":
        return True
    origin = facts.headers.get("origin")
    if _is_blank(origin):
        return False
    origin_host = extract_origin_host(origin)
    if origin_host is None or origin_host != request_host:
        return True
    # sharpit deviation (stricter than BootUI): on API paths a present Origin must be the request's own origin, port
    # included, so a page served from another local port cannot drive sharpit with a no-preflight "simple" request
    if facts.api_sub_path is None:
        return False
    expected = _request_origin(facts)
    return expected is None or _parse_origin(cast("str", origin)) != expected


def _panel_access(method: str, sub_path: str, settings: SharpitSettings) -> Denial | None:
    unsafe = method not in _SAFE_METHODS
    if unsafe and settings.read_only:
        for prefix, subject in _GLOBAL_WRITE_SUBJECTS.items():
            if sub_path == prefix or sub_path.startswith(prefix + "/"):
                return _panel_denied(subject, read_only_reason(subject, True))
    panel = panel_for_api_path(sub_path)
    if panel is None:
        return None
    flags = settings.panels.get(panel.id, PanelSettings())
    if not flags.enabled:
        return _panel_denied(panel.id, disabled_reason(panel.id))
    if panel.action_capable and unsafe and (settings.read_only or flags.read_only):
        return _panel_denied(panel.id, read_only_reason(panel.id, settings.read_only))
    return None


def decide_guard(
    facts: RequestFacts, settings: SharpitSettings, token: str | None, gateway: str | None
) -> Denial | None:
    """None when the request may proceed, else the response to send."""
    trusted = is_trusted_source(facts, settings, gateway)
    if not settings.allow_non_localhost and not trusted:
        return _forbidden(MESSAGE_NON_LOOPBACK_SOURCE)
    host_header = facts.headers.get("host")
    request_host = extract_request_host(host_header)
    if not _is_blank(host_header):
        allowed = {h.strip(_JAVA_TRIM).lower() for h in settings.allowed_hosts}
        if request_host is None or (request_host not in _BUILT_IN_ALLOWED_HOSTS and request_host not in allowed):
            return _forbidden(MESSAGE_DISALLOWED_HOST)
    if _is_cross_site(facts, request_host):
        return _forbidden(MESSAGE_CROSS_SITE)
    if facts.api_sub_path is None:
        return None
    if not trusted and not _authorized(facts, token):
        return Denial(
            401,
            {"error": AUTHENTICATION_REQUIRED_MESSAGE},
            (("WWW-Authenticate", AUTHENTICATION_CHALLENGE), ("Cache-Control", "no-store")),
        )
    return _panel_access(facts.method, facts.api_sub_path, settings)


# --- Container gateway (port of ContainerGatewayDetector, route table only, no DNS) ---------------------------------


def _in_container() -> bool:
    if sys.platform != "linux":
        return False
    try:
        return any(marker.exists() for marker in _CONTAINER_MARKERS)
    except OSError:
        return False


def detect_container_gateway(
    route_file: Path = Path("/proc/net/route"), in_container: Callable[[], bool] = _in_container
) -> str | None:
    """Default-route IPv4 gateway from the route table, only inside a container; None anywhere else."""
    if not in_container():
        return None
    try:
        lines = route_file.read_text(encoding="ascii", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        columns = line.split()
        if len(columns) < 3:
            continue
        destination, gw = columns[1], columns[2]
        if destination.upper() != _DEFAULT_ROUTE or gw.upper() == _DEFAULT_ROUTE:
            continue
        if len(gw) == 8 and all(c in _HEX for c in gw):
            return str(ipaddress.IPv4Address(bytes.fromhex(gw)[::-1]))
    return None
