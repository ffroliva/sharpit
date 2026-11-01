"""Secret masking.

Port of BootUI's ``KeywordPatternMasker``, ``SecretValueDetector``, ``ValueExposure`` and ``SecretMasker``.
Regexes are kept verbatim (sharpit widenings are marked); they use ``re.ASCII`` because Java's ``\\s``/``\\b`` are
ASCII-only by default.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Sequence
from enum import StrEnum
from urllib.parse import unquote_plus

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
# sharpit widening (0.3.0 spec §14): vendor token prefixes for positional values
_VENDOR_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:sk_live_|sk_test_|rk_live_|pk_live_|ghp_|gho_|ghs_|ghu_|github_pat_|glpat-|xoxb-|xoxp-|xoxa-|AIza|sk-ant-|sk-proj-)[A-Za-z0-9_-]{16,}"
)


_SECRET_MARKERS = ("=", "://", "eyJ", "PRIVATE KEY", "AKIA", "ASIA")


def is_secret_value(value: str) -> bool:
    """True when the value matches a high-confidence secret pattern (SecretValueDetector)."""
    if not value.strip():
        return False
    if not any(marker in value for marker in _SECRET_MARKERS):  # fast path: every pattern needs one of them
        # sharpit widening (0.3.0 spec §14): vendor token prefixes for positional values
        return bool(_VENDOR_TOKEN.search(value))
    return bool(
        _JWT.fullmatch(value.strip())
        or _PEM_PRIVATE_KEY.search(value)
        or _AWS_ACCESS_KEY.search(value)
        or _URL_USERINFO.search(value)
        or _URL_USER_ONLY.search(value)
        or _CONNECTION_STRING_CREDENTIAL.search(value)
        or _URL_QUERY_CREDENTIAL.search(value)
        or _VENDOR_TOKEN.search(value)
    )


# ---- KeywordPatternMasker -----------------------------------------------------------------------------------------
DEFAULT_KEY_PATTERNS = (
    "password", "passwd", "passphrase", "pwd", "secret", "token", "key", "credential", "credentials", "private",
    "apikey", "api-key", "client-secret", "client_secret", "auth", "authorization", "session-id", "session_id",
    "pgpass",  # sharpit widening: libpq PGPASS / PGPASSFILE
)  # fmt: skip
# sharpit widening: ``pass`` as a whole name segment (DB_PASS, PASS), never inside a word (bypass, compass)
_PASS_SEGMENT = re.compile(r"(?:^|[_.-])pass(?:$|[_.-])")


@functools.lru_cache(maxsize=1024)  # names repeat (headers, config keys) and are never secret themselves
def is_sensitive_key(name: str) -> bool:
    """Case-insensitive substring match on the default key patterns (KeywordPatternMasker.isSecret)."""
    if not name.strip():
        return False
    lowered = name.lower()
    return any(p in lowered for p in DEFAULT_KEY_PATTERNS) or bool(_PASS_SEGMENT.search(lowered))


# ---- text masking (0.2.0, spec §11) --------------------------------------------------------------------------------
# userinfo (user:password@ or a bare key@) is replaced whole, before the token pass can swallow the URL
_TEXT_USERINFO = re.compile(r"://[^/?#\s@]+@", re.ASCII)
# "key": value (JSON) or 'key': value (a Python dict repr). A quoted value keeps its quotes; a bare value (12345,
# true, None, a [list]) becomes a quoted mask, so JSON stays valid.
_TEXT_QUOTED_PAIR = re.compile(
    r"""(["'])([^"'\\\n]*)\1(\s*:\s*)"""
    r"""(?:(["'])(?:(?!\4)[^\\]|\\.)*\4|\[[^\]\n]*\]|\([^)\n]*\)|[^\s,}\]{\[]+)"""
)
# key=value / key: value; an auth scheme word (Bearer abc) belongs to the value, quoted values keep their quotes,
# a bracketed value ([1, 2]) is one value
_TEXT_PAIR = re.compile(
    r"(?<![\w.-])([\w.-]+)(\s*[=:]\s*)"
    r"(\"[^\"]*\"|'[^']*'|\[[^\]\n]*\]|\([^)\n]*\)|(?:(?:Bearer|Basic|Digest|Token)\s+)?[^\s,;&'\"]+)",
    re.ASCII,
)
_TEXT_TOKEN = re.compile(r"\S+")
_TOKEN_EDGES = re.compile(r"^([\"'(\[{<]*)(.*?)([\"')\]}>,;.:!?]*)$", re.DOTALL)
# SQLAlchemy StatementError: "[parameters: ...]" runs to the last "]" on its line (bind tuples nest brackets), or to
# the end of the line when a length cap cut the closing "]" off (the class stops at the newline: no "$" anchor)
_SQL_PARAMETERS = re.compile(r"\[parameters: (?:[^\n]*\]|[^\n]*)", re.MULTILINE)
_SQL_PARAMETERS_MASKED = f"[parameters: {MASK}]"


def _mask_segments(path: str) -> str:
    return "/".join(MASK if is_secret_value(seg) else seg for seg in path.split("/"))


def _mask_pair(m: re.Match[str]) -> str:
    if not (is_sensitive_key(m.group(1)) or m.group(1).lower() in _SECRET_HEADERS):  # Cookie: session=abc
        return m.group(0)
    value = m.group(3)
    quote = value[0] if value[:1] in ("'", '"') else ""
    return f"{m.group(1)}{m.group(2)}{quote}{MASK}{quote}"


def _mask_quoted_pair(m: re.Match[str]) -> str:
    if not is_sensitive_key(m.group(2)):
        return m.group(0)
    quote = m.group(4) or m.group(1)  # a bare value takes the key's quote
    return f"{m.group(1)}{m.group(2)}{m.group(1)}{m.group(3)}{quote}{MASK}{quote}"


def _mask_token(m: re.Match[str]) -> str:
    edges = _TOKEN_EDGES.match(m.group(0))
    assert edges is not None  # the pattern matches any string
    lead, core, trail = edges.groups()
    if not core or MASK in core:  # already masked by an earlier rule (userinfo, key=value)
        return m.group(0)
    if is_secret_value(core):
        return f"{lead}{MASK}{trail}"
    if "/" in core:  # a path such as an access-log "GET /reset/<jwt>"
        return f"{lead}{_mask_segments(core)}{trail}"
    return m.group(0)


_SECRET_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"})


# ---- SecretMasker --------------------------------------------------------------------------------------------------
class Masker:
    """Decides what the UI sees for a (name, value) pair under the live exposure policy."""

    def __init__(
        self, exposure: Exposure, mask_secrets: bool, token: str | None = None, capture_parameters: bool = False
    ) -> None:
        self._exposure = exposure
        self._mask_secrets = mask_secrets
        self._token = (token or "").strip()
        # SQL bind values are never shown under METADATA_ONLY, whatever the capture setting
        self.capture_parameters = capture_parameters and exposure is not Exposure.METADATA_ONLY

    def mask(self, name: str, value: object) -> tuple[object | None, bool]:
        """Return ``(display_value, masked)``."""
        # sharpit's own token is never shown, whatever the mask setting or exposure: it grants the whole console.
        # Any value that contains it is masked whole (a URL or padded copy would leak it otherwise).
        if (
            self._token
            and value is not None
            and self._token in str(value)
            and self._exposure is not Exposure.METADATA_ONLY
        ):
            return MASK, True
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

    def mask_text(self, text: str | None) -> str | None:
        """Mask secrets inside free text: log lines, exception messages, SQL errors (spec §11)."""
        if text is None or self._exposure is Exposure.METADATA_ONLY:
            return None
        if self._token:
            text = text.replace(self._token, MASK)
        if self._exposure is Exposure.FULL:
            return text
        if not self.capture_parameters:
            text = _SQL_PARAMETERS.sub(_SQL_PARAMETERS_MASKED, text)
        if not self._mask_secrets:
            return text
        text = _TEXT_USERINFO.sub(f"://{MASK}@", text)
        text = _TEXT_QUOTED_PAIR.sub(_mask_quoted_pair, text)
        text = _TEXT_PAIR.sub(_mask_pair, text)
        text = _JWT.sub(MASK, text)
        return _TEXT_TOKEN.sub(_mask_token, text)

    def mask_path(self, path: str) -> str:
        """Replace each URL path segment that looks like a secret (a JWT in ``/reset/<jwt>``) with the mask."""
        if self._token:
            path = "/".join(MASK if self._token in seg else seg for seg in path.split("/"))
        if self._exposure is Exposure.FULL or not self._mask_secrets:
            return path
        return _mask_segments(path)

    def mask_query(self, query: str) -> str | None:
        """Mask each ``name=value`` pair of a raw query string by name and by value; the raw name is kept.

        Port of BootUI ``UriMasking.maskQueryString``: ``%70assword=hunter2&page=2`` -> ``%70assword=******&page=2``.
        """
        if self._exposure is Exposure.METADATA_ONLY:
            return None
        pairs = query.split("&")
        for i, pair in enumerate(pairs):
            raw_name, sep, raw_value = pair.partition("=")
            if not sep:  # a bare part (``?<token>``) is a value with no name: masked whole by value
                if self.mask("", unquote_plus(raw_name))[1]:
                    pairs[i] = MASK
            elif raw_value and self.mask(unquote_plus(raw_name), unquote_plus(raw_value))[1]:
                pairs[i] = f"{raw_name}={MASK}"
        return "&".join(pairs)

    def mask_header(self, name: str, values: Sequence[str]) -> tuple[list[str], bool]:
        """Return ``(display_values, masked)`` for one HTTP header; credentials headers are masked by name."""
        if self._exposure is Exposure.METADATA_ONLY:
            return [], False
        key = "authorization" if name.lower() in _SECRET_HEADERS else name  # mask() treats it as a sensitive key
        shown = [self.mask(key, v) for v in values]
        return [str(v) for v, _ in shown], any(masked for _, masked in shown)
