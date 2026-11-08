"""Task 35 council M3: the masker reads the scan window and a margin, not the whole statement.

Nothing past the scan's 20,000 characters is shown, so the masker's input is bounded there. A secret that starts inside
the window and runs across its end must still be read whole and hidden; these rows put one across the cut.
"""

from __future__ import annotations

import pytest

from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect, statement_shape, statement_text
from sharpit.engine.sqltext.lexer import _MAX_SCAN_LENGTH  # pyright: ignore[reportPrivateUsage]

MASKER = Masker(Exposure.MASKED, True)
JWT = "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" * 40 + ".c2lnbmF0dXJlLXNpZ25hdHVyZQ"
SECRETS = {
    "vendor_token": "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "aws_key": "AKIAIOSFODNN7EXAMPLE",
    "jwt": JWT,
    "key_value": "hunter2plain" * 30,
}
LEADS = {"vendor_token": "k = ", "aws_key": "k = ", "jwt": "k = ", "key_value": "password = "}
TAIL = " AND " + " AND ".join(f"c{i} = 1" for i in range(20_000))  # the statement goes on far past the margin


def _straddling(name: str) -> str:
    """A statement whose secret starts 12 characters before the scan's end, in code position."""
    lead = f"SELECT 1 FROM t WHERE {LEADS[name]}"
    head = lead + "x" * (_MAX_SCAN_LENGTH - 12 - len(lead) - len(LEADS[name])) + " " + LEADS[name][:-1]
    sql = f"{head} {SECRETS[name]}{TAIL}"
    assert sql.index(SECRETS[name]) < _MAX_SCAN_LENGTH < sql.index(SECRETS[name]) + len(SECRETS[name])
    return sql


@pytest.mark.parametrize("name", sorted(SECRETS))
@pytest.mark.parametrize("dialect", [Dialect.POSTGRESQL, Dialect.MYSQL_FAMILY, Dialect.SQLITE])
def test_a_secret_across_the_scan_end_stays_hidden_in_the_shape(dialect: Dialect, name: str) -> None:
    text = statement_shape(MASKER, _straddling(name), dialect).text
    assert SECRETS[name][:10] not in text


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_a_secret_across_the_scan_end_stays_hidden_in_the_statement_text(name: str) -> None:
    text = statement_text(MASKER, _straddling(name), Dialect.POSTGRESQL)
    assert text is not None
    assert SECRETS[name][:10] not in text
