"""Stub: reports a commit exactly when it has a Signed-off-by line, so every check of the rules is wrong."""

from __future__ import annotations

import re
import sys
from typing import Any, NamedTuple


class Failure(NamedTuple):
    sha: str
    subject: str
    reason: str


def check_commits(commits: list[dict[str, Any]]) -> list[Failure]:
    return [
        Failure(c["sha"], c["commit"]["message"].splitlines()[0], "missing Signed-off-by")
        for c in commits
        if re.search(r"^Signed-off-by:", c["commit"]["message"], re.MULTILINE)
    ]


def main() -> int:
    return 3


if __name__ == "__main__":
    sys.exit(main())
