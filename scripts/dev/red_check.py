"""Wrong-value stub: replaced by the implementation in the next commit."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def check(nodeids: Sequence[str], cwd: Path | None = None) -> dict[str, str]:
    return dict.fromkeys(nodeids, "unclassified")


def main(argv: Sequence[str] | None = None) -> int:
    return 0
