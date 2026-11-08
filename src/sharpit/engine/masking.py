"""Secret masking.

Port of BootUI's ``KeywordPatternMasker``, ``SecretValueDetector``, ``ValueExposure`` and ``SecretMasker``.
Regexes are kept verbatim (sharpit widenings are marked); they use ``re.ASCII`` because Java's ``\\s``/``\\b`` are
ASCII-only by default.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Sequence
from enum import StrEnum
from urllib.parse import unquote_plus

from sharpit.engine.sqltext import MASK


class Exposure(StrEnum):
    MASKED = "MASKED"
    METADATA_ONLY = "METADATA_ONLY"
    FULL = "FULL"


# ---- SecretValueDetector -------------------------------------------------------------------------------------------
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+")  # used with fullmatch
_PEM_LABEL = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "
_PEM_MARKER = "PRIVATE KEY"
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


_VENDOR_PREFIXES = (
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
)  # fmt: skip: keep in step with _VENDOR_TOKEN
_SECRET_HINT = re.compile(
    "|".join(re.escape(hint) for hint in ("=", "://", "eyJ", _PEM_MARKER, "AKIA", "ASIA", *_VENDOR_PREFIXES))
)


def _has_vendor_token(value: str) -> bool:
    return any(prefix in value for prefix in _VENDOR_PREFIXES) and _VENDOR_TOKEN.search(value) is not None


def _has_pem_private_key(value: str) -> bool:
    """``BEGIN[A-Z0-9 ]*PRIVATE KEY``, by finds: each search starts past the last match, so it stays linear."""
    start = 0
    while (key := value.find(_PEM_MARKER, start)) >= 0:
        begin = value.rfind("BEGIN", start, key)
        if begin >= 0 and not value[begin + len("BEGIN") : key].strip(_PEM_LABEL):
            return True
        start = key + len(_PEM_MARKER)
    return False


def is_secret_value(value: str) -> bool:
    """True when the value matches a high-confidence secret pattern (SecretValueDetector)."""
    if _SECRET_HINT.search(value) is None:  # fast path: every pattern below needs one of them
        return False
    return bool(
        _JWT.fullmatch(value.strip())
        or _has_pem_private_key(value)
        or _AWS_ACCESS_KEY.search(value)
        or _URL_USERINFO.search(value)
        or _URL_USER_ONLY.search(value)
        or _CONNECTION_STRING_CREDENTIAL.search(value)
        or _URL_QUERY_CREDENTIAL.search(value)
        or _has_vendor_token(value)
    )


# ---- KeywordPatternMasker -----------------------------------------------------------------------------------------
DEFAULT_KEY_PATTERNS = (
    "password", "passwd", "passphrase", "pwd", "secret", "token", "key", "credential", "credentials", "private",
    "apikey", "api-key", "client-secret", "client_secret", "auth", "authorization", "session-id", "session_id",
    "pgpass",  # sharpit widening: libpq PGPASS / PGPASSFILE
)  # fmt: skip
# sharpit widening: ``pass`` and ``pw`` as a whole name segment (DB_PASS, user_pw), never inside a word (bypass, PWM)
_PASS_SEGMENT = re.compile(r"(?:^|[_.-])(?:pass|pw)(?:$|[_.-])")


@functools.lru_cache(maxsize=1024)  # names repeat (headers, config keys) and are never secret themselves
def is_sensitive_key(name: str) -> bool:
    """Case-insensitive substring match on the default key patterns (KeywordPatternMasker.isSecret)."""
    if not name.strip():
        return False
    lowered = name.lower()
    return any(p in lowered for p in DEFAULT_KEY_PATTERNS) or bool(_PASS_SEGMENT.search(lowered))


def _may_hold_sensitive_key(text: str) -> bool:
    """False only when no name in ``text`` can be a sensitive key: each one needs one of these substrings."""
    lowered = text.lower()
    return any(p in lowered for p in DEFAULT_KEY_PATTERNS) or any(p in lowered for p in ("pass", "pw", "cookie"))


# ---- text masking (0.2.0, spec §11) --------------------------------------------------------------------------------
# userinfo (user:password@ or a bare key@) is replaced whole, before the token pass can swallow the URL
_TEXT_USERINFO = re.compile(r"://[^/?#\s@]+@", re.ASCII)
# "key": value (JSON), 'key': value (a Python dict repr), key=value and key: value. Only the key is matched: where a
# value ends is a guess (quotes, brackets, spaces in a password), so a sensitive value is masked to the end of its line
_TEXT_QUOTED_PAIR = re.compile(r"""(["'])([^"'\\\n]*)\1\s*:\s*""")
_TEXT_PAIR = re.compile(r"(?<![\w.-])([\w.-]+)\s*[=:]\s*", re.ASCII)
# 0.4.0's pair patterns, kept as they shipped so masking stays a superset of 0.4.0 by construction: the quoted values
# span lines, and a value is consumed whole, so a pair inside a secret token cannot split it. The one edit is the bound
# on a bracketed value: an unclosed ``[`` would scan to the end of its line from every key. Past the bound the value
# falls to the bare alternative, and the strict pass masks a sensitive one to the end of its line anyway
_TEXT_QUOTED_PAIR_V04 = re.compile(
    r"""(["'])([^"'\\\n]*)\1(\s*:\s*)"""
    r"""(?:(["'])(?:(?!\4)[^\\]|\\.)*\4|\[[^\]\n]{0,256}+\]|\([^)\n]{0,256}+\)|[^\s,}\]{\[]+)"""
)
_TEXT_PAIR_V04 = re.compile(
    r"(?<![\w.-])([\w.-]+)(\s*[=:]\s*)"
    r"(\"[^\"]*\"|'[^']*'|\[[^\]\n]{0,256}+\]|\([^)\n]{0,256}+\)|(?:(?:Bearer|Basic|Digest|Token)\s+)?[^\s,;&'\"]+)",
    re.ASCII,
)
# no credential after ``token``: an ordinary word (``Token expired``, ``FROM Token WHERE``), a plain, Capitalised or
# UPPER run of 16 letters at most between punctuation, or an ASCII operator (``token >= 5``). Anything else is masked.
# The opening run is possessive: both punctuation classes hold quotes, so backtracking between them is quadratic
_ENGLISH_AFTER_TOKEN = (
    r"""(?:[(\["'{<]*+(?:[A-Za-z]?[a-z]{0,15}|[A-Z]{1,16})[)\]"'}>,;.:!?]*|[!-/:-@\[-`{-~]+)(?:\s|$)"""
)
# sharpit widening: a scheme's credential with no key before it; schemes match in any case (RFC 9110) and may name the
# word ``token`` (``bearer token abc``). The word checked after ``token`` is not consumed: it can open the next match
_TEXT_AUTH_SCHEME = re.compile(
    r"(?<![\w-])((?i:Bearer|Basic)(?:\s++(?i:Token))?"
    rf"|(?i:Token)(?=\s++(?!{_ENGLISH_AFTER_TOKEN})))\s+\S+",
    re.ASCII,
)
# the JWT segments in free text. A run with no later segment is consumed too and left as it is: a restart at each
# ``eyJ`` inside it is quadratic and would fail on the same segments
_TEXT_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}+(\.[A-Za-z0-9_-]{8,}+\.[A-Za-z0-9_-]++)?")
_TEXT_TOKEN = re.compile(r"\S+")
_TOKEN_LEAD = "\"'([{<"
_TOKEN_TRAIL = "\"')]}>,;.:!?"
# SQLAlchemy StatementError: "[parameters: ...]" runs to the last "]" on its line (bind tuples nest brackets), or to
# the end of the line when a length cap cut the closing "]" off (the class stops at the newline: no "$" anchor)
_SQL_PARAMETERS = re.compile(r"\[parameters: (?:[^\n]*\]|[^\n]*)", re.MULTILINE)
_SQL_PARAMETERS_MASKED = f"[parameters: {MASK}]"
_AUTH_SCHEME_MASKED = rf"\1 {MASK}"
_QUOTED_PAIR_MASKED = rf"\g<0>\1{MASK}\1"
_PAIR_MASKED = rf"\g<0>{MASK}"
_PAIR_TOKEN = re.compile(r"[^\s,;&'\"]+")  # 0.4.0's bare value: where a statement's value ends
# a statement's ``name = name`` is SQL (0.4.0 shows it); a colon after a name is no operator SQL puts before a value
_TEXT_COLON_PAIR = re.compile(r"(?<![\w.-])([\w.-]+)\s*:=?\s*", re.ASCII)


def _shared_ends(old: str, new: str) -> tuple[int, int]:
    """How many characters ``old`` and ``new`` share at each end. A ``*`` is never shared: it may be a value's own."""
    limit = min(len(old), len(new))
    head = 0
    while head < limit and old[head] == new[head] and old[head] != "*":
        head += 1
    tail = 0
    while tail < limit - head and old[-1 - tail] == new[-1 - tail] and old[-1 - tail] != "*":
        tail += 1
    return head, tail


def _unedited(text: str, edits: Sequence[tuple[int, int, str]]) -> list[tuple[int, int, int]]:
    """The ``(start, end, shift)`` runs of ``text`` that ``edits`` leave in place, ascending."""
    runs: list[tuple[int, int, int]] = []
    cursor = shift = 0
    for start, end, replacement in edits:
        old = text[start:end]
        if old != replacement:
            head, tail = _shared_ends(old, replacement)
            runs.append((cursor, start + head, shift))
            shift += len(replacement) - len(old)
            cursor = end - tail
    runs.append((cursor, len(text), shift))
    return runs


def _kept_in(kept: list[tuple[int, int, int]], runs: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """``kept`` cut down to ``runs``. Both ascend, so a segment behind a run is never read again: one walk."""
    survivors: list[tuple[int, int, int]] = []
    first = 0
    for start, end, shift in runs:
        while first < len(kept) and kept[first][0] + kept[first][2] <= start:
            first += 1
        index = first
        while start < end and index < len(kept) and kept[index][0] < end:
            output, raw, length = kept[index]
            low, high = max(output, start), min(output + length, end)
            survivors.append((low + shift, raw + low - output, high - low))
            index += 1
    return survivors


class Tracked:
    """Text under rewrite that can say which raw characters survived. Each pass reads what the last one wrote.

    ``track=False`` keeps no positions: the same passes at the cost of the passes, which is how free text runs.
    """

    def __init__(self, text: str, track: bool = True) -> None:
        self.text = text
        self._track = track
        self._raw_length = len(text)
        self._kept = [(0, 0, len(text))] if text else []  # (output start, raw start, length), ascending in both

    def apply(self, edits: Sequence[tuple[int, int, str]]) -> None:
        """Replace each ``(start, end, replacement)``, ascending and disjoint, in the current text."""
        if not edits:
            return
        text = self.text
        if self._track:
            self._kept = _kept_in(self._kept, _unedited(text, edits))
        parts: list[str] = []
        cursor = 0
        for start, end, replacement in edits:
            parts += (text[cursor:start], replacement)
            cursor = end
        parts.append(text[cursor:])
        self.text = "".join(parts)

    def sub(self, pattern: re.Pattern[str], repl: str | Callable[[re.Match[str]], str]) -> None:
        """``pattern.sub(repl, text)``, tracked."""
        if not self._track:
            self.text = pattern.sub(repl, self.text)
            return
        edits: list[tuple[int, int, str]] = []
        for found in pattern.finditer(self.text):
            replacement = repl(found) if callable(repl) else found.expand(repl)
            if replacement != found[0]:  # most tokens: a pass that changes nothing costs its read alone
                edits.append((found.start(), found.end(), replacement))
        self.apply(edits)

    def hidden(self) -> list[tuple[int, int]]:
        """The raw ``(start, end)`` runs that did not survive, ascending. With no positions, all of it: fail closed."""
        if not self._track:
            return [(0, self._raw_length)]
        spans: list[tuple[int, int]] = []
        at = 0
        for _, raw, length in self._kept:
            if raw > at:
                spans.append((at, raw))
            at = raw + length
        if at < self._raw_length:
            spans.append((at, self._raw_length))
        return spans


def _mask_segments(path: str) -> str:
    return "/".join(MASK if is_secret_value(seg) else seg for seg in path.split("/"))


def _mask_pairs(pattern: re.Pattern[str], masked: str, tracked: Tracked, value: re.Pattern[str] | None = None) -> None:
    """Mask the value of each sensitive key in ``tracked``, to the end of its line, or to the end of ``value`` there.

    The pattern matches a key and its separator alone, so a key inside another pair's value is still read as a key.
    """
    text = tracked.text
    edits: list[tuple[int, int, str]] = []
    position = 0
    while found := pattern.search(text, position):
        position = found.end()
        name = found.group(found.lastindex or 0)
        if is_sensitive_key(name) or _is_secret_header(name):  # Cookie: session=abc
            if value is None:
                line_end = text.find("\n", position)
                end = len(text) if line_end < 0 else line_end
            elif bounded := value.match(text, position):
                end = bounded.end()
            else:  # no value after the key: nothing to hide
                continue
            edits.append((found.start(), end, found.expand(masked)))
            position = end
    tracked.apply(edits)


def _mask_pair_v04(m: re.Match[str]) -> str:
    if not (is_sensitive_key(m.group(1)) or _is_secret_header(m.group(1))):  # Cookie: session=abc
        return m.group(0)
    value = m.group(3)
    quote = value[0] if value[:1] in ("'", '"') else ""
    return f"{m.group(1)}{m.group(2)}{quote}{MASK}{quote}"


def _mask_quoted_pair_v04(m: re.Match[str]) -> str:
    if not is_sensitive_key(m.group(2)):
        return m.group(0)
    quote = m.group(4) or m.group(1)  # a bare value takes the key's quote
    return f"{m.group(1)}{m.group(2)}{m.group(1)}{m.group(3)}{quote}{MASK}{quote}"


def _mask_jwt(m: re.Match[str]) -> str:
    return MASK if m.group(1) else m.group(0)


def _mask_token(m: re.Match[str]) -> str:
    token = m.group(0)
    if _SECRET_HINT.search(token) is None:  # what ``is_secret_value`` reads first: below, no other answer is possible
        return token
    stripped = token.lstrip(_TOKEN_LEAD)
    core = stripped.rstrip(_TOKEN_TRAIL)
    lead, trail = token[: len(token) - len(stripped)], stripped[len(core) :]
    if not core or MASK in core:  # already masked by an earlier rule (userinfo, key=value)
        return token
    if is_secret_value(core):
        return f"{lead}{MASK}{trail}"
    if "/" in core:  # a path such as an access-log "GET /reset/<jwt>"
        return f"{lead}{_mask_segments(core)}{trail}"
    return token


def _mask_glued(m: re.Match[str]) -> str:
    """A mask vouches for nothing glued to it. The last pass only: it can remove a key an earlier pass must read."""
    token = m.group(0)
    if MASK not in token:
        return token
    return MASK.join(MASK if is_secret_value(part.strip(_GLUED_EDGES)) else part for part in token.split(MASK))


def _mask_tokens(tracked: Tracked) -> None:
    """The token pass. A text with no hint holds no token with one, and this pass is a Python call per word."""
    if _SECRET_HINT.search(tracked.text):
        tracked.sub(_TEXT_TOKEN, _mask_token)


_GLUED_EDGES = f"{_TOKEN_LEAD}{_TOKEN_TRAIL}="  # a key's ``=`` beside a mask is no connection-string credential
_SECRET_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"})


def _is_secret_header(name: str) -> bool:
    """A secret header's name, alone or as the last segment of a dotted name (``request.Cookie``): the text pair
    patterns read dots as name characters, so ``do.Cookie: session=x`` is the Cookie header with a prefix."""
    return name.rpartition(".")[2].lower() in _SECRET_HEADERS


def _key_text(key: bytes | None) -> str:
    """What the key looks like in a text. A generated key is random bytes and has no such form: nothing can show it."""
    try:
        return key.decode("utf-8") if key else ""
    except UnicodeDecodeError:
        return ""


# ---- SecretMasker --------------------------------------------------------------------------------------------------
class Masker:
    """Decides what the UI sees for a (name, value) pair under the live exposure policy."""

    def __init__(
        self,
        exposure: Exposure,
        mask_secrets: bool,
        token: str | None = None,
        capture_parameters: bool = False,
        identity_key: bytes | None = None,
    ) -> None:
        self._exposure = exposure
        self._mask_secrets = mask_secrets
        self._token = (token or "").strip()
        # SQL bind values are never shown under METADATA_ONLY, whatever the capture setting
        self.capture_parameters = capture_parameters and exposure is not Exposure.METADATA_ONLY
        self.identity_key = identity_key

    @property
    def identity_key(self) -> bytes | None:
        return self._identity_key

    @identity_key.setter
    def identity_key(self, key: bytes | None) -> None:
        self._identity_key = key
        self._never_shown = tuple(secret for secret in (self._token, _key_text(key)) if secret)

    def mask(self, name: str, value: object) -> tuple[object | None, bool]:
        """Return ``(display_value, masked)``."""
        # sharpit's own token and identity key are never shown, whatever the mask setting or exposure: one grants the
        # whole console, the other lets a guess at a hidden name be checked. Any value that contains one is masked whole
        # (a URL or padded copy would leak it otherwise).
        if self._never_shown and value is not None and self._exposure is not Exposure.METADATA_ONLY:
            text = str(value)
            if any(secret in text for secret in self._never_shown):
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

    def _run_passes(self, tracked: Tracked, strict: bool) -> None:
        """The one pass chain. ``strict`` adds the two passes that guess a value runs to the end of its line."""
        for secret in self._never_shown:
            tracked.sub(re.compile(re.escape(secret)), MASK)
        if self._exposure is Exposure.FULL:
            return
        if not self.capture_parameters:
            tracked.sub(_SQL_PARAMETERS, _SQL_PARAMETERS_MASKED)
        if not self._mask_secrets:
            return
        tracked.sub(_TEXT_USERINFO, f"://{MASK}@")
        # 0.4.0's text pipeline, in its order; its JWT and token passes are the linear forms below, same output
        tracked.sub(_TEXT_QUOTED_PAIR_V04, _mask_quoted_pair_v04)
        tracked.sub(_TEXT_PAIR_V04, _mask_pair_v04)
        tracked.sub(_TEXT_JWT, _mask_jwt)
        _mask_tokens(tracked)
        # the strict pass over that output: whatever either masks stays masked
        tracked.sub(_TEXT_USERINFO, f"://{MASK}@")
        if strict:
            _mask_pairs(_TEXT_QUOTED_PAIR, _QUOTED_PAIR_MASKED, tracked)
            _mask_pairs(_TEXT_PAIR, _PAIR_MASKED, tracked)
        tracked.sub(_TEXT_AUTH_SCHEME, _AUTH_SCHEME_MASKED)
        if not strict and _may_hold_sensitive_key(tracked.text):
            # a statement: each colon key is still re-read, its value bounded to one token (``x = pwd:=v`` hides ``v``).
            # After the scheme pass: a value that opens with ``Token`` would hide the word and leave the credential
            _mask_pairs(_TEXT_COLON_PAIR, _PAIR_MASKED, tracked, _PAIR_TOKEN)
        tracked.sub(_TEXT_JWT, _mask_jwt)
        _mask_tokens(tracked)
        if MASK in tracked.text:
            tracked.sub(_TEXT_TOKEN, _mask_glued)  # last: every pass above that reads a key has read it

    def mask_text(self, text: str | None) -> str | None:
        """Mask secrets inside free text: log lines, exception messages, SQL errors (spec §11)."""
        if text is None or self._exposure is Exposure.METADATA_ONLY:
            return None
        tracked = Tracked(text, track=False)
        self._run_passes(tracked, strict=True)
        return tracked.text

    def mask_spans(self, text: str, strict: bool = True, view: Tracked | None = None) -> list[tuple[int, int]] | None:
        """The raw ``(start, end)`` runs the passes hide in ``text``; ``view``, a tracked text over it, is read instead.

        ``None`` under ``METADATA_ONLY``, where nothing is shown: ``[]`` would read as nothing to hide.
        """
        if self._exposure is Exposure.METADATA_ONLY:
            return None
        tracked = Tracked(text) if view is None else view
        self._run_passes(tracked, strict)
        return tracked.hidden()

    def mask_statement(self, text: str) -> str | None:
        """``mask_text`` for a statement: its literals are gone, so no value's end is left to guess (spec §3)."""
        if self._exposure is Exposure.METADATA_ONLY:
            return None
        tracked = Tracked(text, track=False)
        self._run_passes(tracked, strict=False)
        return tracked.text

    def mask_path(self, path: str) -> str:
        """Replace each URL path segment that looks like a secret (a JWT in ``/reset/<jwt>``) with the mask."""
        if self._never_shown:
            path = "/".join(
                MASK if any(secret in seg for secret in self._never_shown) else seg for seg in path.split("/")
            )
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
