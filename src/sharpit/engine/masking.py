"""Secret masking, URI masking and credential redaction.

Port of BootUI's ``KeywordPatternMasker``, ``SecretValueDetector``, ``ValueExposure``, ``SecretMasker`` and the
engine ``SensitiveNames``, ``UriMasking`` and ``CredentialRedaction`` helpers. Regexes are kept verbatim; they use
``re.ASCII`` because Java's ``\\s``/``\\b`` are ASCII-only by default.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from enum import StrEnum
from typing import overload

MASK = "******"


class Exposure(StrEnum):
    MASKED = "MASKED"
    METADATA_ONLY = "METADATA_ONLY"
    FULL = "FULL"


# ---- SecretValueDetector -------------------------------------------------------------------------------------------
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+")  # used with fullmatch
_PEM_PRIVATE_KEY = re.compile(r"BEGIN[A-Z0-9 ]*PRIVATE KEY")
_AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", re.ASCII)
_URL_USERINFO = re.compile(r"://[^/?#\s:@]+:[^/?#\s@]+@", re.ASCII)
_URL_QUERY_CREDENTIAL = re.compile(
    r"[?&](?:access[-_]?token|refresh[-_]?token|id[-_]?token|auth[-_]?token|session[-_]?token|client[-_]?secret"
    r"|secret[-_]?key|api[-_]?key|access[-_]?key|password|passwd|passphrase|pwd|secret|token|credential)=[^&\s]+",
    re.IGNORECASE | re.ASCII,
)


def is_secret_value(value: str) -> bool:
    """True when the value matches a high-confidence secret pattern (SecretValueDetector)."""
    if not value.strip():
        return False
    return bool(
        _JWT.fullmatch(value.strip())
        or _PEM_PRIVATE_KEY.search(value)
        or _AWS_ACCESS_KEY.search(value)
        or _URL_USERINFO.search(value)
        or _URL_QUERY_CREDENTIAL.search(value)
    )


# ---- KeywordPatternMasker / SensitiveNames -------------------------------------------------------------------------
DEFAULT_KEY_PATTERNS = (
    "password", "passwd", "passphrase", "pwd", "secret", "token", "key", "credential", "credentials", "private",
    "apikey", "api-key", "client-secret", "client_secret", "auth", "authorization", "session-id", "session_id",
)  # fmt: skip

_SENSITIVE_HEADER_NAMES = frozenset(
    {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-xsrf-token", "x-csrf-token"}
)


def is_sensitive_key(name: str) -> bool:
    """Case-insensitive substring match on the default key patterns (KeywordPatternMasker.isSecret)."""
    if not name.strip():
        return False
    lowered = name.lower()
    return any(p in lowered for p in DEFAULT_KEY_PATTERNS)


_HEX = frozenset("0123456789abcdefABCDEF")


def _decode(value: str, form_encoded: bool) -> str:
    if "%" not in value and not (form_encoded and "+" in value):
        return value
    out: list[str] = []
    pending = bytearray()
    i = 0
    n = len(value)
    while i < n:
        c = value[i]
        # Mirrors the Java bound: an escape needs two hex digits strictly inside the string.
        if c == "%" and i + 2 < n and value[i + 1] in _HEX and value[i + 2] in _HEX:
            pending.append(int(value[i + 1 : i + 3], 16))
            i += 3
            continue
        if pending:
            out.append(pending.decode("utf-8", errors="replace"))
            pending.clear()
        out.append(" " if form_encoded and c == "+" else c)
        i += 1
    if pending:
        out.append(pending.decode("utf-8", errors="replace"))
    return "".join(out)


@overload
def decode_query_component(value: str) -> str: ...
@overload
def decode_query_component(value: None) -> None: ...
def decode_query_component(value: str | None) -> str | None:
    """Lenient percent-decoding of a query component; ``+`` is a space. Never raises."""
    return None if value is None else _decode(value, True)


@overload
def decode_path_component(value: str) -> str: ...
@overload
def decode_path_component(value: None) -> None: ...
def decode_path_component(value: str | None) -> str | None:
    """Lenient percent-decoding of a path component; ``+`` stays literal. Never raises."""
    return None if value is None else _decode(value, False)


def _header_matches(name: str) -> bool:
    return is_sensitive_key(name) or name.lower() in _SENSITIVE_HEADER_NAMES


def is_sensitive_header(name: str) -> bool:
    """Sensitive as captured or percent-decoded (SensitiveNames.isSensitive); blank is never sensitive."""
    if not name.strip():
        return False
    if _header_matches(name):
        return True
    decoded = decode_query_component(name)
    return decoded != name and _header_matches(decoded)


# ---- CredentialRedaction -------------------------------------------------------------------------------------------
_URL_CREDENTIALS = re.compile(r"([a-z][a-z0-9+.-]*://)([^:/@\s]+):([^@\s]+)@", re.IGNORECASE | re.ASCII)
_URL_CREDENTIAL_PARAMS = re.compile(
    r"([?&;](?:user|username|password|passwd|pwd)=)([^&;\s]*)", re.IGNORECASE | re.ASCII
)
_URL_USER_INFO = re.compile(r"(//)[^/?#\s]*@", re.ASCII)
_QUERY_PARAM = re.compile(r"[?&;#]([^?&;#=\s]+)=([^&;#\s]*)", re.ASCII)
_MAX_NESTED_URL_DEPTH = 3


def redact_credentials(text: str) -> str:
    """Replace any embedded user/password in a connection string or message (CredentialRedaction.redact)."""
    if not text:
        return text
    redacted = _URL_CREDENTIALS.sub(lambda m: f"{m[1]}{MASK}@", text)
    return _URL_CREDENTIAL_PARAMS.sub(lambda m: f"{m[1]}{MASK}", redacted)


def redact_message(value: str | None, _depth: int = _MAX_NESTED_URL_DEPTH) -> str | None:
    """redact_credentials widened for free-form text quoting a whole URL (CredentialRedaction.redactMessage)."""
    if not value:
        return value
    redacted = _URL_USER_INFO.sub(lambda m: f"{m[1]}{MASK}@", redact_credentials(value))
    parts: list[str] = []
    copied_to = 0
    for m in _QUERY_PARAM.finditer(redacted):
        if not is_sensitive_header(m[1]) and not _carries(m[2], _depth - 1):
            continue
        parts.append(redacted[copied_to : m.start(2)])
        parts.append(MASK)
        copied_to = m.end(2)
    parts.append(redacted[copied_to:])
    return "".join(parts)


def _carries(value: str | None, depth: int) -> bool:
    if not value or depth <= 0:
        return False
    if redact_message(value, depth - 1) != value:
        return True
    decoded = decode_query_component(value)
    return decoded != value and redact_message(decoded, depth - 1) != decoded


def carries_credentials(value: str | None) -> bool:
    """True when a value embeds a URL that itself carries credentials (possibly percent-encoded)."""
    return _carries(value, _MAX_NESTED_URL_DEPTH)


# ---- UriMasking ----------------------------------------------------------------------------------------------------
def _masks_by_policy(mask_secrets: bool, exposure: Exposure) -> bool:
    if exposure is Exposure.METADATA_ONLY:
        return True
    return mask_secrets and exposure is not Exposure.FULL


def _authority_bounds(uri: str) -> tuple[int, int] | None:
    sep = uri.find("//")
    if sep < 0 or (sep > 0 and uri[sep - 1] != ":"):
        return None
    start = sep + 2
    end = next((i for i in range(start, len(uri)) if uri[i] in "/?#"), len(uri))
    return start, end


@overload
def mask_user_info(uri: str) -> str: ...
@overload
def mask_user_info(uri: None) -> None: ...
def mask_user_info(uri: str | None) -> str | None:
    """Replace authority ``user:secret@`` with ``******@``, unconditionally."""
    if not uri:
        return uri
    bounds = _authority_bounds(uri)
    if bounds is None:
        return uri
    start, end = bounds
    at = uri[start:end].rfind("@")
    if at < 0:
        return uri
    return f"{uri[:start]}{MASK}@{uri[start + at + 1 : end]}{uri[end:]}"


def _mask_parameters(parameters: str, masker: Callable[[str], str]) -> str:
    if not parameters:
        return parameters
    out: list[str] = []
    start = 0
    for i in range(len(parameters) + 1):
        if i < len(parameters) and parameters[i] not in "&;":
            continue
        out.append(masker(parameters[start:i]))
        if i < len(parameters):
            out.append(parameters[i])
        start = i + 1
    return "".join(out)


def _mask_parameter(parameter: str, policy_masking: bool) -> str:
    name, eq, value = parameter.partition("=")
    if not eq:
        return MASK if policy_masking and is_sensitive_header(name) else parameter
    if (policy_masking and is_sensitive_header(name)) or carries_credentials(value):
        return f"{name}={MASK}"
    return parameter


def _mask_matrix(path: str, policy_masking: bool) -> str:
    if ";" not in path:
        return path
    segments = path.split("/")
    for i, segment in enumerate(segments):
        first = segment.find(";")
        if first >= 0:
            # The segment name is request identity (/api/token/refresh), only its matrix parameters are masked.
            rest = _mask_parameters(segment[first + 1 :], lambda p: _mask_parameter(p, policy_masking))
            segments[i] = segment[: first + 1] + rest
    return "/".join(segments)


@overload
def mask_query_string(raw_query: str, mask_secrets: bool = ..., exposure: Exposure = ...) -> str | None: ...
@overload
def mask_query_string(raw_query: None, mask_secrets: bool = ..., exposure: Exposure = ...) -> None: ...
def mask_query_string(
    raw_query: str | None, mask_secrets: bool = True, exposure: Exposure = Exposure.MASKED
) -> str | None:
    """Mask a raw query string per the exposure policy; ``None`` under METADATA_ONLY (caller drops it)."""
    if raw_query is None or exposure is Exposure.METADATA_ONLY:
        return None
    policy = _masks_by_policy(mask_secrets, exposure)
    return _mask_parameters(raw_query, lambda p: _mask_parameter(p, policy))


def mask_path(path: str | None, mask_secrets: bool = True, exposure: Exposure = Exposure.MASKED) -> str | None:
    """Mask ``;name=value`` matrix parameters of a path; segment names are preserved."""
    if path is None or ";" not in path:
        return path
    return _mask_matrix(path, _masks_by_policy(mask_secrets, exposure))


@overload
def mask_uri(uri: str, mask_secrets: bool = ..., exposure: Exposure = ...) -> str: ...
@overload
def mask_uri(uri: None, mask_secrets: bool = ..., exposure: Exposure = ...) -> None: ...
def mask_uri(uri: str | None, mask_secrets: bool = True, exposure: Exposure = Exposure.MASKED) -> str | None:
    """Mask a whole raw URI: user-info always, query/matrix/fragment parameters per the exposure policy."""
    if uri is None:
        return None
    policy = _masks_by_policy(mask_secrets, exposure)
    before_fragment, hash_, fragment = uri.partition("#")
    base, question, raw_query = before_fragment.partition("?")
    masked_base = mask_user_info(base)
    bounds = _authority_bounds(masked_base)
    path_start = 0
    if bounds is not None:
        # Java pathStart: just past the authority, up to the first "/" (a "?"/"#" cannot occur in base).
        slash = masked_base.find("/", bounds[0])
        path_start = len(masked_base) if slash < 0 else slash
    display = masked_base[:path_start] + _mask_matrix(masked_base[path_start:], policy)
    if question:
        masked_query = mask_query_string(raw_query, mask_secrets, exposure)
        if masked_query is not None:
            display += "?" + masked_query
    if hash_:
        masked_fragment = mask_query_string(fragment, mask_secrets, exposure)
        if masked_fragment is not None:
            display += "#" + masked_fragment
    return display


# ---- SecretMasker --------------------------------------------------------------------------------------------------
class Masker:
    """Decides what the UI sees for a (name, value) pair under the live exposure policy."""

    def __init__(self, exposure: Exposure, mask_secrets: bool) -> None:
        self._exposure = exposure
        self._mask_secrets = mask_secrets

    def mask(self, name: str, value: object) -> tuple[object | None, bool]:
        """Return ``(display_value, masked)``."""
        if self._exposure is Exposure.FULL:
            return value, False
        if self._exposure is Exposure.METADATA_ONLY:
            return None, False
        if value is None:
            return None, False
        if hasattr(value, "get_secret_value"):  # pydantic SecretStr / SecretBytes, always masked
            return MASK, True
        if not self._mask_secrets:
            return value, False
        if is_sensitive_key(name) or (isinstance(value, str) and is_secret_value(value)):
            return MASK, True
        return value, False
