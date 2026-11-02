"""Sanitise raw BootUI captures into committed test fixtures.

Usage: python scripts/sanitize_golden.py <replica/evidence src_dir> <tests/fixtures/bootui dst_dir>

Two layouts: flat ``<panel>.json`` files (BootUI 1.17.0) and, for 2.2.0, ``<sharpit-id>/captured.json`` or
``<sharpit-id>/<name>.captured.json`` folders. An optional ``uncaptured.json`` in the 2.2.0 source
(``{"<sharpit-id>": "<reason>"}``) is copied into ``meta.json``; ``nullable.json`` files are never written.

The flat 1.17.0 layout keeps every item (no truncation, so ``page`` stays consistent). The 2.2.0 folders are shape
goldens: each list keeps one item per DISTINCT SHAPE (key set + per-key JSON kind, null its own kind), so real nulls and
type variants survive, and a list of scalars keeps its first 3. Epoch/duration fields are normalised only when set.
The 2.2.0 layout also refuses an error body at the root (any ``error`` key) and checks secrets before and after shaping.
Both layouts replace only an enumerated list of volatile values, then abort on anything that looks like a secret.

Layout: nested when the source folder is named ``2.2.0``, else flat; force it with a third argument. Regenerate:
    python scripts/sanitize_golden.py replica/evidence/2.2.0 tests/fixtures/bootui/2.2.0 nested
meta.json keeps its existing ``provisional`` list and takes ``uncaptured`` from ``<src>/uncaptured.json``.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

SKIP = {"mcp.json", "beans_view_graph.json"}  # empty / duplicate of beans.json
META_2_2_0 = {"bootuiVersion": "2.2.0", "app": "tiny-ledger", "profile": "full", "captured": "2026-11-02"}
META = {"bootui": "1.17.0", "app": "bootui-spring-sample-app", "profile": "dev", "captured": "2026-10-30"}

VOLATILE_KEYS: dict[str, Any] = {
    "bootUiVersion": "x",
    "frameworkVersion": "x",
    "javaVersion": "x",
    "startupTimeMillis": 0,
    "scannedAt": 0,
    "path": "/path",  # health diskSpace.path
    "hostname": "localhost",
    "host": "localhost",
    "instanceId": "00000000",
    "runId": "00000000",
    "clientAddress": "127.0.0.1",
}
# BootUI 2.2.0 epoch-millisecond fields that change on every capture.
VOLATILE_TIMES = (
    "startedAt",
    "checkedAt",
    "oldestTimestamp",
    "newestTimestamp",
    "readAt",
    "readStartedAt",
    "capturedAt",
    "timestamp",
    "firstSeen",
    "lastSeen",
    "generatedAt",
    "startTimestamp",
    "endTimestamp",
    "epochMillis",
    "oldestRetainedAt",
)
VOLATILE_NUMBERS = {"durationMicros": 1000}
FIXED_TIME = 1700000000000
# Config properties read from the capturing machine's environment or JVM: all machine-specific.
MACHINE_SOURCES = {"systemEnvironment", "systemProperties"}
ABS_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\Users\\|/(?:Users|home)/)")
# Absolute paths inside longer strings. `http://`, `jdbc:postgresql://`, `classpath:/` and `?d=e:/f` stay intact:
# a backslash path may follow most chars, a forward-slash drive path only whitespace, a bracket or a quote. Paths with
# spaces are only taken inside brackets or quotes.
EMBEDDED_PATHS = (
    re.compile(r"(?<=[\[(\"'])[A-Za-z]:[\\/][^\])\"']*(?=[\])\"'])"),
    re.compile(r"(?<![A-Za-z0-9+.\-:/?&#])[A-Za-z]:\\[^\s\])\"']*"),
    re.compile(r"(?<![^\s\[(\"'])[A-Za-z]:/(?!/)[^\s\])\"']*"),
    re.compile(r"(?<![\w.\-])/(?:Users|home)/[^\s\])\"']*"),
)

SECRET_VALUE = re.compile(
    r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]+"  # JWT
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"  # PEM private key
    r"|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"  # AWS access key id
    r"|://(?!user:password@)[^/\s:@]+:[^/\s@]+@"  # URL userinfo (docs placeholder user:password allowed)
)
SENSITIVE_NAME = re.compile(r"(?:passw(?:or)?d|secret|token|api[-_.]?key|credential|private[-_.]?key)", re.IGNORECASE)
MASK = "******"
NL = chr(10)


_KEEP: Any = object()


def _replacement(key: str, value: Any, nested: bool, machine: bool) -> Any:
    """The fixed stand-in for a volatile ``key``/``value``, or ``_KEEP`` when the value is recursed into unchanged."""
    is_number = isinstance(value, int | float) and not isinstance(value, bool)
    if key in VOLATILE_KEYS and not isinstance(value, (dict, list)) and value is not None:
        return VOLATILE_KEYS[key]
    if key in VOLATILE_TIMES and isinstance(value, int) and not isinstance(value, bool):
        return FIXED_TIME
    if key in VOLATILE_NUMBERS and is_number:
        return VOLATILE_NUMBERS[key]
    if key in ("startupTimeMillis", "scannedAt") and not nested:
        return 0
    if key == "value" and machine:
        return "x"
    if isinstance(value, str) and ABS_PATH.match(value):
        return "/path"
    return _KEEP


def sanitise(node: Any, nested: bool = False) -> Any:
    """``nested`` is the 2.2.0 layout: epoch/duration fields are normalised only when set, real nulls stay null."""
    if isinstance(node, str):
        for pattern in EMBEDDED_PATHS:
            node = pattern.sub("/path", node)
        return node
    if isinstance(node, list):
        return [sanitise(v, nested) for v in node]  # pyright: ignore[reportUnknownVariableType]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    machine = node.get("source") in MACHINE_SOURCES and node.get("masked") is False  # pyright: ignore[reportUnknownMemberType]
    for key, value in node.items():  # pyright: ignore[reportUnknownVariableType]
        replacement = _replacement(key, value, nested, machine)
        out[key] = sanitise(value, nested) if replacement is _KEEP else replacement
    return out


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    return {str: "string", list: "array", dict: "object"}.get(type(value), "other")


def _signature(item: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((k, _kind(v)) for k, v in item.items()))


def _reduce(items: list[Any]) -> list[Any]:
    if items and all(isinstance(i, dict) for i in items):  # pyright: ignore[reportUnknownVariableType]
        seen: dict[tuple[tuple[str, str], ...], dict[str, Any]] = {}
        for item in items:
            seen.setdefault(_signature(item), item)
        return list(seen.values())
    return items[:3]


def shape_golden(node: Any) -> Any:
    """Keep one item per distinct shape (key set + per-key JSON kind, null its own kind) in every list; real nulls and
    every type variant survive. Lists of scalars keep their first 3. Scalars and keys are untouched."""
    if isinstance(node, dict):
        return {k: shape_golden(v) for k, v in node.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(node, list):
        return _reduce([shape_golden(i) for i in node])  # pyright: ignore[reportUnknownVariableType]
    return node


def is_error_envelope(body: Any) -> bool:
    """A guard or framework error, not a panel payload: a root object whose ``error`` is set (covers Spring's
    ``{timestamp,status,error,path}``). A null ``error`` is a DTO field (the http-probe response carries one)."""
    return isinstance(body, dict) and body.get("error") is not None


def find_secrets(node: Any, where: str = "$", key: str = "") -> list[str]:
    """Report every non-masked value that matches a secret pattern or sits under a sensitive key name."""
    found: list[str] = []
    if isinstance(node, dict):
        name = node.get("name")  # pyright: ignore[reportUnknownMemberType]
        pair_sensitive = isinstance(name, str) and SENSITIVE_NAME.search(name) is not None
        for k, v in node.items():  # pyright: ignore[reportUnknownVariableType]
            sensitive = SENSITIVE_NAME.search(k) is not None or (pair_sensitive and k == "value")
            found += find_secrets(v, f"{where}.{k}", k if sensitive else "")
    elif isinstance(node, list):
        for i, v in enumerate(node):  # pyright: ignore[reportUnknownVariableType]
            found += find_secrets(v, f"{where}[{i}]", key)
    elif isinstance(node, str):
        if SECRET_VALUE.search(node) or (key and node not in (MASK, "")):
            found.append(where)
    elif key and node is not None and not isinstance(node, bool):
        found.append(where)
    return found


def _nested_meta(src: Path, dst: Path) -> dict[str, Any]:
    uncaptured_path = src / "uncaptured.json"
    uncaptured = json.loads(uncaptured_path.read_text(encoding="utf-8")) if uncaptured_path.is_file() else {}
    old_meta = dst / "meta.json"
    provisional = json.loads(old_meta.read_text(encoding="utf-8")).get("provisional", []) if old_meta.is_file() else []
    return {**META_2_2_0, "uncaptured": uncaptured, "provisional": provisional}


def _resolve(src: Path, dst: Path, repo: Path, layout: str | None) -> tuple[Path, Path, bool]:
    src = src.resolve()
    dst = dst.resolve()
    allowed_src = (repo / "replica" / "evidence").resolve()
    allowed_dst = (repo / "tests" / "fixtures" / "bootui").resolve()
    if not src.is_relative_to(allowed_src) or not dst.is_relative_to(allowed_dst):
        raise ValueError("source must be under replica/evidence and destination under tests/fixtures/bootui")
    layout = layout or ("nested" if src.name == "2.2.0" else "flat")
    if layout not in ("nested", "flat"):
        raise ValueError(f"layout must be 'nested' or 'flat', got {layout!r}")
    return src, dst, layout == "nested"


def main(src: Path, dst: Path, repo: Path | None = None, layout: str | None = None) -> None:
    """``layout`` is ``"nested"`` (2.2.0: ``<id>/captured.json`` folders) or ``"flat"`` (1.17.0).
    Default: nested when the source folder is named ``2.2.0``, else flat.
    ``repo`` is the root holding ``replica/evidence`` and ``tests/fixtures/bootui``
    (default: this repository; tests pass a temporary one)."""
    src, dst, nested = _resolve(src, dst, repo or Path(__file__).resolve().parents[1], layout)
    dst.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def emit(path: Path, target: Path) -> None:
        name = str(path.relative_to(src))
        data = sanitise(json.loads(path.read_text(encoding="utf-8")), nested)
        if nested and is_error_envelope(data):
            sys.exit(f"refusing to write {name}: an error body, not a panel payload")
        leaks = find_secrets(data, name)  # before shaping: shaping can split a name from its value
        if nested:
            data = shape_golden(data)
            leaks += find_secrets(data, name)
        if leaks:
            sys.exit(f"refusing to write {name}: possible secret at {', '.join(leaks[:5])}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + NL, encoding="utf-8", newline=NL)
        written.append(name)

    if nested:
        for folder in sorted(p for p in src.iterdir() if p.is_dir()):
            for path in sorted(folder.glob("*captured.json")):
                emit(path, dst / folder.name / path.name)
        meta = _nested_meta(src, dst)
    else:
        for path in sorted(src.glob("*.json")):
            if path.name not in SKIP:
                emit(path, dst / path.name)
        meta = META
    (dst / "meta.json").write_text(json.dumps(meta, indent=2) + NL, encoding="utf-8", newline=NL)
    print("written:", ", ".join(written), "+ meta")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]), layout=sys.argv[3] if len(sys.argv) == 4 else None)
