"""Statements and what real servers did with them (2026-11-05 design section 8, Task 6).

``rows(kind)`` reads ``rows.jsonl.gz`` beside this file once, or the file named by ``SHARPIT_SERVER_CORPUS``.
``real_leak`` rows are statements a server printed back in a shape that leaked; ``reading`` rows are one server and one
session setting reading one statement, ``returned`` saying whether it handed the marker back. ``d6`` marks the owner's
SQLite double-quote rows.
"""

from __future__ import annotations

import gzip
import json
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

KINDS = ("real_leak", "reading")
ENV = "SHARPIT_SERVER_CORPUS"


@dataclass(frozen=True)
class ServerRow:
    text: str
    server: str
    session: str
    marker: str
    returned: bool | None
    seed: int
    d6: bool = False


def path() -> Path:
    return Path(os.environ.get(ENV) or Path(__file__).with_name("rows.jsonl.gz"))


@cache
def _load(source: str) -> dict[str, list[ServerRow]]:
    out: dict[str, list[ServerRow]] = {k: [] for k in KINDS}
    with gzip.open(source, "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            out[d.pop("kind")].append(ServerRow(**d))
    return out


def rows(kind: str) -> list[ServerRow]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
    return list(_load(str(path()))[kind])
