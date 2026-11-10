"""Machine values collector and leak gate feeder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def collect_machine_values(env: dict[str, str] | None = None) -> list[str]:
    """Stub returning wrong value for red test."""
    return []


def write_machine_values(
    out_path: Path | str,
    values: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    """Stub returning wrong value for red test."""
    return Path(out_path)


def main(argv: Any = None) -> int:
    return 0
