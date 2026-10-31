"""Sanitise raw BootUI captures into committed test fixtures.

Usage: python scripts/sanitize_golden.py <src_dir> <dst_dir>

Keeps every item (no truncation, so ``page`` stays consistent), replaces only an enumerated list of
volatile values, then aborts if anything that looks like a secret is left.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

SKIP = {"mcp.json", "beans_view_graph.json"}  # empty / duplicate of beans.json
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
}
# Config properties read from the capturing machine's environment or JVM: all machine-specific.
MACHINE_SOURCES = {"systemEnvironment", "systemProperties"}
ABS_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\Users\\|/(?:Users|home)/)")

SECRET_VALUE = re.compile(
    r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]+"  # JWT
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"  # PEM private key
    r"|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"  # AWS access key id
    r"|://(?!user:password@)[^/\s:@]+:[^/\s@]+@"  # URL userinfo (docs placeholder user:password allowed)
)
SENSITIVE_NAME = re.compile(r"passw(?:or)?d|passwd|secret|token|api[-_.]?key|credential|private[-_.]?key", re.I)
MASK = "******"


def sanitise(node: Any) -> Any:
    if isinstance(node, list):
        return [sanitise(v) for v in node]  # pyright: ignore[reportUnknownVariableType]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    machine = node.get("source") in MACHINE_SOURCES and node.get("masked") is False  # pyright: ignore[reportUnknownMemberType]
    for key, value in node.items():  # pyright: ignore[reportUnknownVariableType]
        if key in VOLATILE_KEYS and not isinstance(value, (dict, list)) and value is not None:
            out[key] = VOLATILE_KEYS[key]
        elif key in ("startupTimeMillis", "scannedAt"):
            out[key] = 0
        elif key == "value" and machine:
            out[key] = "x"
        elif isinstance(value, str) and ABS_PATH.match(value):
            out[key] = "/path"
        else:
            out[key] = sanitise(value)
    return out


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
    dst.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for path in sorted(src.glob("*.json")):
        if path.name in SKIP:
            continue
        data = sanitise(json.loads(path.read_text(encoding="utf-8")))
        if leaks := find_secrets(data, path.name):
            sys.exit(f"refusing to write {path.name}: possible secret at {', '.join(leaks[:5])}")
        (dst / path.name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        written.append(path.stem)
    (dst / "meta.json").write_text(json.dumps(META, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("written:", ", ".join(written), "+ meta")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
