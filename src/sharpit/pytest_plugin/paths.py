"""Render pytest finding locations relative to the session root."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from sharpit.engine.testsession.facts import TestFacts
from sharpit.engine.testsession.gates import LAZY_LOAD_OUTSIDE_APP


def relative_location(filename: str, root: Path | str) -> str:
    try:
        path = os.path.relpath(filename, root)
    except ValueError:  # another drive (Windows)
        path = filename
    if path.startswith(".."):  # outside the root: keep it absolute
        path = filename
    return Path(path).as_posix()


def _relative_site(site: str | None, root: Path) -> str | None:
    if site is None:
        return None
    prefix, separator = "", ""
    if site.startswith(LAZY_LOAD_OUTSIDE_APP):
        prefix, separator, site = site.partition(" declared at ")
    filename, line = site.rsplit(":", 1)
    return f"{prefix}{separator}{relative_location(filename, root)}:{line}"


def relativize_sql_locations(test: TestFacts, root: Path) -> None:
    """Normalize SQL sites before gate messages and worker facts are generated."""
    call = test.phases.get("call")
    if call is None:
        return
    for key, site in call.relationship_sites.items():
        call.relationship_sites[key] = _relative_site(site, root)
    for key, (site, hint) in call.statement_sites.items():
        call.statement_sites[key] = (_relative_site(site, root), hint)
    call.unbounded_reads = [
        replace(fact, location=_relative_site(fact.location, root)) for fact in call.unbounded_reads
    ]
