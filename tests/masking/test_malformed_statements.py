"""Task 33 (D1), the residue: free text inside a ``[SQL: ...]`` block that the lexer reads cleanly, on the MySQL family.

Each row is an A2 hit at 200,000 rows (``masking_gate.py a2 --seed 11|12``, build ``132c5277``): the masker hides the
whole token, and ``render._release_name`` gave back the part before ``=<literal>`` as a column name. v0.4.0 hid the
token whole. The rule: a hit is the hidden runs joined across whitespace, and only a hit that is exactly ``name=`` and
its literal releases the name. The values are the gate generator's random draws, not real credentials.
"""

from __future__ import annotations

import pytest

from sharpit.engine.capture import sqltrace
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect

MASKER = Masker(Exposure.MASKED, True)
HEAD = "sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) x\n[SQL: UPDATE t SET "

# (block body, the value shown at 132c5277)
PAST_THE_LITERAL = [  # the hit runs on past the literal: ``<v>='k'=<url>``
    (
        "pmgpm1aeueqkb4kz2r3z=\"session_id\"='https://api.x.io/p?token=wX69ds6SbX6u7my77CFI'"
        '\t"X-Api-Key"=Basic WGGJe0EP726LKKRJyyxI@a b c',
        "pmgpm1aeueqkb4kz2r3z",
    ),
    (
        "host:\n  WjzqE3ewXmrpFgv1P5uG auR8z3KH4n8qNIIopuXo='api_key'=https://api.x.io/p?token=9VQuOiXJxXSMjtae78VK",
        "auR8z3KH4n8qNIIopuXo",
    ),
    (
        "'DB_PASS': jpbWpskNV4ujz9VUgppJ='url':\n  \"nKoUbhwEyFCuWujWDSkm\\nIcTAopFN0agO2N431iqg\", 'x' = "
        '"aecolALgQGT3z7eXmsGq\r\nHEbbdy4cTRj9xfKWNn09" secret=\n46vtBPcPyb5IAf1A2sxt&A6IedrZLpTqxkc5eJOFV',
        "jpbWpskNV4ujz9VUgppJ",
    ),
    (
        "Server=x;Password=MheiFhocn93lbnjxcdl7\n'auth':\n  zPEfb7tIID7baspvhFoD='set-cookie'=\n"
        "'RJGFLRrz9wJ9NLJRIt5m Eac7I9NPMNf0JHwmxyh3'=curl -H 'Authorization: Bearer AKIAPR8301Q2OXRVNIU2'",
        "zPEfb7tIID7baspvhFoD",
    ),
]
JOINED_BEFORE = [  # another hidden run reaches the name across whitespace: ``Bearer <v>="..."``
    (
        "'DB_PASS'='azlahJA23FbxZsWcfiQe'=/reset/eyJRog1Z0K5rLPn9q.uoxgLsuuGGP86a.7tWNvxkfxl4IQx/apikey:\n"
        "  pcl1xP3dfaLYeRQCZPqb='Cookie' = \"NMvlP6T1NuLsDuIzdJTj\nuDcjUeFvVMvG3wWYOSoM\"",
        "pcl1xP3dfaLYeRQCZPqb",
    ),
    (
        "2apyzzr87p1xnnntxebb 'x-api-key':Bearer k0BOg84k231WBSs8fuNeset-cookie=\"ghp_Fxc4AylAzvuYMv6A0m40Ti6D\"",
        "k0BOg84k231WBSs8fuNe",
    ),
]


@pytest.mark.parametrize(
    ("body", "value"),
    [pytest.param(*row, id=f"past-the-literal-{i}") for i, row in enumerate(PAST_THE_LITERAL)]
    + [pytest.param(*row, id=f"joined-before-{i}") for i, row in enumerate(JOINED_BEFORE)],
)
def test_a_value_before_a_literal_is_no_column_name_on_mysql(body: str, value: str) -> None:
    out = sqltrace.mask_error(MASKER, f"{HEAD}{body}]", Dialect.MYSQL_FAMILY)
    assert out is not None
    assert value not in out


def test_a_name_whose_hit_is_only_its_literal_is_still_shown() -> None:
    """The release the rule keeps: ``bio="sk_live_..."`` on its own is a column and a literal (spec A3)."""
    vendor = "sk_live_" + "1234567890abcdefghijkl"
    out = sqltrace.mask_error(MASKER, f'{HEAD}bio="{vendor}" WHERE id=1]', Dialect.MYSQL_FAMILY)
    assert out is not None
    assert "SET bio=? WHERE" in out
