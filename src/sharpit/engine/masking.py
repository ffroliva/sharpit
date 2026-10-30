"""Secret masking.

Port of BootUI's ``KeywordPatternMasker``, ``SecretValueDetector``, ``ValueExposure`` and ``SecretMasker``.
Regexes are kept verbatim (sharpit widenings are marked); they use ``re.ASCII`` because Java's ``\\s``/``\\b`` are
ASCII-only by default.
"""

from __future__ import annotations

import re
from enum import StrEnum

MASK = "******"


class Exposure(StrEnum):
    MASKED = "MASKED"
    METADATA_ONLY = "METADATA_ONLY"
    FULL = "FULL"


# ---- SecretValueDetector -------------------------------------------------------------------------------------------
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+")  # used with fullmatch
_PEM_PRIVATE_KEY = re.compile(r"BEGIN[A-Z0-9 ]*PRIVATE KEY")
_AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", re.ASCII)
# sharpit widening: the user part may be empty (redis://:pw@host), so `*` where BootUI has `+`
_URL_USERINFO = re.compile(r"://[^/?#\s:@]*:[^/?#\s@]+@", re.ASCII)
# sharpit widening: userinfo with no password is a key too (Sentry DSN https://<key>@host/1); fail closed
_URL_USER_ONLY = re.compile(r"://[^/?#\s@]+@", re.ASCII)
# sharpit widening: ADO.NET / ODBC / Azure connection-string credential segments
_CONNECTION_STRING_CREDENTIAL = re.compile(
    r"(?:^|;)\s*(?:password|pwd|accountkey|sharedaccesskey)\s*=", re.IGNORECASE | re.ASCII
)
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
        or _URL_USER_ONLY.search(value)
        or _CONNECTION_STRING_CREDENTIAL.search(value)
        or _URL_QUERY_CREDENTIAL.search(value)
    )


# ---- KeywordPatternMasker -----------------------------------------------------------------------------------------
DEFAULT_KEY_PATTERNS = (
    "password", "passwd", "passphrase", "pwd", "secret", "token", "key", "credential", "credentials", "private",
    "apikey", "api-key", "client-secret", "client_secret", "auth", "authorization", "session-id", "session_id",
)  # fmt: skip
# sharpit widening: ``pass`` as a whole name segment (DB_PASS, PASS), never inside a word (bypass, compass)
_PASS_SEGMENT = re.compile(r"(?:^|[_.-])pass(?:$|[_.-])")


def is_sensitive_key(name: str) -> bool:
    """Case-insensitive substring match on the default key patterns (KeywordPatternMasker.isSecret)."""
    if not name.strip():
        return False
    lowered = name.lower()
    return any(p in lowered for p in DEFAULT_KEY_PATTERNS) or bool(_PASS_SEGMENT.search(lowered))


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
