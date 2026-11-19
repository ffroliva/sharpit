"""Command tree and CLI dispatch for sharpit (BootUI's CommandTree and BootUiCli)."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TextIO

__all__ = ["main", "run"]


def run(
    argv: Sequence[str],
    environment: Mapping[str, str],
    terminal: bool,
    out: TextIO,
    err: TextIO,
    client_factory: Callable[[Any], Any] | None = None,
) -> int:
    return 999


def main(argv: Sequence[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    terminal = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False
    return run(args, os.environ, terminal, sys.stdout, sys.stderr)
