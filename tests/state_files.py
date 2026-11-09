"""What a "nothing written" check compares: names alone miss a file rewritten in place, such as the identity key."""

from __future__ import annotations

from pathlib import Path


def state_files(root: Path) -> dict[Path, tuple[int, bytes | None]]:
    """Every entry under ``root`` with its mtime and, for a file, its bytes; a directory has no bytes."""
    return {p: (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None) for p in root.rglob("*")}
