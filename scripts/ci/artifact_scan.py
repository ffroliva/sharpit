"""Scan CI artifacts for planted canary values before upload (B8).

A public scanner that runs before every actions/upload-artifact step in CI. Fails naming the file,
line, and form (raw, URL-encoded, JSON-escaped, base64) of any hit. Prints values never, only their
index. With no values file, prints "no planted values in this job" and passes unless --require.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple


class Hit(NamedTuple):
    path: Path
    line: int
    form: str
    value_index: int

    @property
    def file(self) -> Path:
        return self.path


def scan(
    paths: Sequence[Path | str] | Path | str,
    values: Sequence[str] | None = None,
    *,
    values_file: Path | str | None = None,
) -> list[Hit]:
    """Scan given paths for planted canary values in any of four forms."""
    # Stub: returns no hits so tests see reds first
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan artifacts for planted canary values.")
    parser.add_argument("--values-file", help="Path to canary values file (one per line).")
    parser.add_argument("--require", action="store_true", help="Fail if values file is missing or empty.")
    parser.add_argument("files", nargs="*", help="Files or directories to scan.")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # Stub: returns 0 without values or no hits
    if not args.values_file:
        if args.require:
            return 1
        print("no planted values in this job")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
