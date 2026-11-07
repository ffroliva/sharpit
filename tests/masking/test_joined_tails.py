"""Joined secret tails share their scan even when many secret spans overlap it."""

from __future__ import annotations

from typing import SupportsIndex

import pytest

from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import _hide_joined_tails


class CountedSql(str):
    reads = 0

    def __getitem__(self, key: SupportsIndex | slice) -> str:
        self.reads += 1
        return super().__getitem__(key)


def test_overlapping_secret_tails_scan_each_character_once() -> None:
    sql = CountedSql("select " + "password='x';" * 32)
    spans = Masker(Exposure.MASKED, True).mask_spans(sql, False)
    assert spans is not None
    assert len(spans) == 32
    sql.reads = 0

    _hide_joined_tails(sql, spans)

    assert sql.reads <= 2 * len(sql)
    assert all(end == len(sql) for _, end in spans)


@pytest.mark.parametrize("closer", ")]}")
def test_a_closing_bracket_hides_adjacent_token_parts_but_still_bounds_the_tail(closer: str) -> None:
    prefix = "password='x'"
    sql = prefix + closer + "9f8e7d6c5b" + closer + "4a3f2e1d0c" + closer + " name"
    spans = [(0, len(prefix))]

    _hide_joined_tails(sql, spans)

    assert spans == [(0, sql.rindex(closer))]
