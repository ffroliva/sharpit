"""The call site a SQL-kind finding row names: the most frequent one, first-seen on ties, read in one pass.

The row is rebuilt on every runtime-insights read, so a request with thousands of identical statements must not cost
quadratic time (release council, 0.7.0: 10k executions took 3.3 s per row).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import overload

from sharpit.engine.collectors.insights.text import primary_call_site


class _CountingSites(Sequence[str]):
    """A sequence that counts element reads, so a test can tell one pass from one pass per element."""

    def __init__(self, sites: list[str]) -> None:
        self._sites = sites
        self.reads = 0

    def __len__(self) -> int:
        return len(self._sites)

    @overload
    def __getitem__(self, index: int) -> str: ...
    @overload
    def __getitem__(self, index: slice) -> Sequence[str]: ...
    def __getitem__(self, index: int | slice) -> str | Sequence[str]:
        self.reads += 1
        return self._sites[index]


def test_the_most_frequent_call_site_wins() -> None:
    assert primary_call_site(["a.py:1", "b.py:2", "b.py:2"]) == "b.py:2"


def test_a_tie_goes_to_the_site_seen_first() -> None:
    assert primary_call_site(["b.py:2", "a.py:1", "a.py:1", "b.py:2"]) == "b.py:2"


def test_no_sites_gives_an_empty_call_site() -> None:
    assert primary_call_site([]) == ""


def test_the_sites_are_read_in_one_pass() -> None:
    sites = _CountingSites([f"site{i % 7}.py:{i % 7}" for i in range(2_000)])
    primary_call_site(sites)
    assert sites.reads <= 2 * len(sites)
