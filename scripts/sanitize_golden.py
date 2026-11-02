"""Sanitise raw BootUI captures into committed test fixtures.

Usage: python scripts/sanitize_golden.py <replica/evidence src_dir> <tests/fixtures/bootui dst_dir>

Two layouts: flat ``<panel>.json`` files (BootUI 1.17.0) and, for 2.2.0, ``<sharpit-id>/captured.json`` or
``<sharpit-id>/<name>.captured.json`` folders. An optional ``uncaptured.json`` in the 2.2.0 source
(``{"<sharpit-id>": "<reason>"}``) is copied into ``meta.json``; ``nullable.json`` files are never written.

The flat 1.17.0 layout keeps every item (no truncation, so ``page`` stays consistent). The 2.2.0 folders are shape
goldens: ``tests/golden.py`` compares every payload list item with the golden's first item only, so each list of
objects is reduced to ONE representative item (first non-null value per key across all items) and a list of scalars to
its first 3. That makes the golden independent of item order and keeps the fixtures small.
Both layouts replace only an enumerated list of volatile values, then abort on anything that looks like a secret.
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
}
# BootUI 2.2.0 epoch-millisecond fields that change on every capture.
VOLATILE_TIMES = ("startedAt", "checkedAt", "oldestTimestamp", "newestTimestamp", "readAt", "readStartedAt")
FIXED_TIME = 1700000000000
# Config properties read from the capturing machine's environment or JVM: all machine-specific.
MACHINE_SOURCES = {"systemEnvironment", "systemProperties"}
ABS_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\Users\\|/(?:Users|home)/)")

EMBEDDED_PATH = re.compile(r"[A-Za-z]:[\\/][^\]\s\"']*")  # a Windows path inside a longer string, e.g. file [C:\x]

SECRET_VALUE = re.compile(
    r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]+"  # JWT
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"  # PEM private key
    r"|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"  # AWS access key id
    r"|://(?!user:password@)[^/\s:@]+:[^/\s@]+@"  # URL userinfo (docs placeholder user:password allowed)
)
SENSITIVE_NAME = re.compile(r"(?:passw(?:or)?d|secret|token|api[-_.]?key|credential|private[-_.]?key)", re.IGNORECASE)
MASK = "******"


def sanitise(node: Any) -> Any:
    if isinstance(node, str):
        return EMBEDDED_PATH.sub("/path", node)
    if isinstance(node, list):
        return [sanitise(v) for v in node]  # pyright: ignore[reportUnknownVariableType]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    machine = node.get("source") in MACHINE_SOURCES and node.get("masked") is False  # pyright: ignore[reportUnknownMemberType]
    for key, value in node.items():  # pyright: ignore[reportUnknownVariableType]
        if key in VOLATILE_KEYS and not isinstance(value, (dict, list)) and value is not None:
            out[key] = VOLATILE_KEYS[key]
        elif key in VOLATILE_TIMES and isinstance(value, int) and not isinstance(value, bool):
            out[key] = FIXED_TIME
        elif key in ("startupTimeMillis", "scannedAt"):
            out[key] = 0
        elif key == "value" and machine:
            out[key] = "x"
        elif isinstance(value, str) and ABS_PATH.match(value):
            out[key] = "/path"
        else:
            out[key] = sanitise(value)
    return out


def _merge(a: Any, b: Any) -> Any:
    if a is None:
        return b
    if b is None:
        return a
    if isinstance(a, dict) and isinstance(b, dict):
        out: dict[str, Any] = dict(a)  # pyright: ignore[reportUnknownArgumentType]
        for key, value in b.items():  # pyright: ignore[reportUnknownVariableType]
            out[key] = _merge(out.get(key), value)
        return out
    if isinstance(a, list) and isinstance(b, list):
        return _reduce([*a, *b])  # pyright: ignore[reportUnknownArgumentType]
    return a


def _reduce(items: list[Any]) -> list[Any]:
    if items and all(isinstance(i, dict) for i in items):  # pyright: ignore[reportUnknownVariableType]
        merged = items[0]
        for item in items[1:]:
            merged = _merge(merged, item)
        return [{k: shape_golden(v) for k, v in merged.items()}]
    return items[:3]


def shape_golden(node: Any) -> Any:
    """Reduce every list to a representative sample (see the module docstring); scalars and keys are untouched."""
    if isinstance(node, dict):
        return {k: shape_golden(v) for k, v in node.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(node, list):
        return _reduce([shape_golden(i) for i in node])  # pyright: ignore[reportUnknownVariableType]
    return node


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


def main(src: Path, dst: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    src = src.resolve()
    dst = dst.resolve()
    allowed_src = (repo / "replica" / "evidence").resolve()
    allowed_dst = (repo / "tests" / "fixtures" / "bootui").resolve()
    if not src.is_relative_to(allowed_src) or not dst.is_relative_to(allowed_dst):
        raise ValueError("source must be under replica/evidence and destination under tests/fixtures/bootui")
    dst.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def emit(path: Path, target: Path, shape: bool = False) -> None:
        data = sanitise(json.loads(path.read_text(encoding="utf-8")))
        data = shape_golden(data) if shape else data
        if leaks := find_secrets(data, str(path.relative_to(src))):
            sys.exit(f"refusing to write {path.relative_to(src)}: possible secret at {', '.join(leaks[:5])}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        written.append(str(path.relative_to(src)))

    folders = sorted(p for p in src.iterdir() if p.is_dir())
    for path in sorted(src.glob("*.json")):
        if path.name not in SKIP and path.name != "uncaptured.json":
            emit(path, dst / path.name)
    for folder in folders:
        for path in sorted(folder.glob("*captured.json")):
            emit(path, dst / folder.name / path.name, shape=True)
    if folders:
        uncaptured_path = src / "uncaptured.json"
        uncaptured = json.loads(uncaptured_path.read_text(encoding="utf-8")) if uncaptured_path.is_file() else {}
        meta: dict[str, Any] = {**META_2_2_0, "uncaptured": uncaptured, "provisional": []}
    else:
        meta = META
    (dst / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("written:", ", ".join(written), "+ meta")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
