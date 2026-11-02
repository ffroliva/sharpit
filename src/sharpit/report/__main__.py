"""``python -m sharpit.report summary <report.json>``."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from sharpit.report.summary import render_summary


def _fail(message: str) -> int:
    print(f"sharpit.report: {message}", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "summary":
        return _fail("usage: python -m sharpit.report summary <report.json>")
    try:
        report = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _fail(f"cannot read report: {exc}")
    if not isinstance(report, Mapping):
        return _fail("report is not a JSON object")
    sys.stdout.write(render_summary(report))  # pyright: ignore[reportUnknownArgumentType]
    return 0


if __name__ == "__main__":
    sys.exit(main())
