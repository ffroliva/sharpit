"""Hand-written parser for the python-dotenv grammar (single-line values only)."""

import os
import re
from collections.abc import Mapping

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*)$")
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def _double_quoted(rest: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(rest) and rest[i] != '"':
        if rest[i] == "\\" and i + 1 < len(rest):
            nxt = rest[i + 1]
            out.append(_ESCAPES.get(nxt, "\\" + nxt))
            i += 2
        else:
            out.append(rest[i])
            i += 1
    return "".join(out)


def parse_dotenv(text: str, environ: Mapping[str, str] = os.environ) -> dict[str, str]:
    """Parse ``text``; ``${VAR}`` expands from earlier keys, then ``environ`` (never mutated)."""
    result: dict[str, str] = {}

    def expand(value: str) -> str:
        def sub(m: re.Match[str]) -> str:
            name, default = m.group(1), m.group(2)
            return result.get(name, environ.get(name, default or ""))

        return _VAR.sub(sub, value)

    for line in text.splitlines():
        m = _LINE.match(line)
        if m is None:
            continue
        key, raw = m.group(1), m.group(2)
        if raw.startswith("'"):
            value = raw[1:].split("'", 1)[0]
        elif raw.startswith('"'):
            value = expand(_double_quoted(raw[1:]))
        else:
            value = expand(re.split(r"\s+#", raw, maxsplit=1)[0].strip())
        result[key] = value
    return result
