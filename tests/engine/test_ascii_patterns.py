"""Patterns for ASCII-only values reject non-ASCII digits and letters (``\\d`` and ``\\w`` need ``re.ASCII``)."""

import re

import pytest

from sharpit.engine.advisors import retention
from sharpit.engine.collectors import alembic
from sharpit.engine.collectors.vulns import epss

ARABIC_INDIC_ONE = "١"
FULLWIDTH_ONE = "１"


@pytest.mark.parametrize(
    ("pattern", "ascii_value", "non_ascii_value"),
    [
        (retention._INTEGER, "-12", f"-1{ARABIC_INDIC_ONE}"),
        (epss._CVE_ID, "CVE-2024-12345", f"CVE-2024-1234{FULLWIDTH_ONE}"),
        (alembic._IDENTIFIER, "rev_1a", "rev_é"),
    ],
)
def test_pattern_accepts_ascii_only(pattern: re.Pattern[str], ascii_value: str, non_ascii_value: str) -> None:
    assert pattern.fullmatch(ascii_value)
    assert pattern.fullmatch(non_ascii_value) is None
