"""Hand-written parser for the python-dotenv grammar (single-line values only)."""

import os
import re
from collections.abc import Mapping

_LINE = re.compile(r"^\s*(?:export\s+)?([^=#\s]+)\s*=\s*(.*)$")
_SINGLE = re.compile(r"^'([^']*)'\s*(?:#.*)?$")
_DOUBLE = re.compile(r'^"((?:\\.|[^"\\])*)"\s*(?:#.*)?$')
_EOL = re.compile(r"\r\n|\r|\n")
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def _unescape(inner: str) -> str:
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(0)), inner)


def parse_dotenv(text: str, environ: Mapping[str, str] = os.environ) -> dict[str, str]:
    """Parse ``text``; ``${VAR}`` expands from earlier keys, then ``environ`` (never mutated)."""
    result: dict[str, str] = {}

    def expand(value: str) -> str:
        def sub(m: re.Match[str]) -> str:
            name, default = m.group(1), m.group(2)
            return result.get(name, environ.get(name, default or ""))

        return _VAR.sub(sub, value)

    for line in _EOL.split(text):
        m = _LINE.match(line)
        if m is None:
            continue
        key, raw = m.group(1), m.group(2)
        if raw[:1] in ("'", '"'):
            q = (_SINGLE if raw[0] == "'" else _DOUBLE).match(raw)
            if q is None:
                continue
            value = q.group(1) if raw[0] == "'" else expand(_unescape(q.group(1)))
        else:
            value = expand(re.split(r"\s+#", raw, maxsplit=1)[0].strip())
        result[key] = value
    return result
