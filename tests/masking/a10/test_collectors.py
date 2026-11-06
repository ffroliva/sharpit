from __future__ import annotations

from pathlib import Path

from tests.masking.a10.conftest import plant_fails, scratch_package

from sharpit.engine.collectors.postgresql.querytext import query_text
from sharpit.engine.masking import MASK, Exposure, Masker

MASKER = Masker(Exposure.MASKED, True)
NODE = "tests/masking/a10/test_collectors.py::test_postgresql_catalog_hides_unicode_space_before_dollar_quote"
MODULE = "engine/collectors/postgresql/querytext.py"
ANCHOR = 'if any(ord(char) > 127 and char.isspace() for char in sql) and "$" in sql:\n        return MASK'


def test_postgresql_catalog_hides_unicode_space_before_dollar_quote() -> None:
    secret = "A10" + "QUERY" + "SECRET"
    assert query_text(MASKER, f"SELECT\u2003$tag${secret}$tag$") == MASK


def test_postgresql_catalog_rule_fails_when_planted(tmp_path: Path) -> None:
    package = scratch_package(tmp_path)
    plant_fails(package, NODE, MODULE, ANCHOR, "if False:\n        return MASK")
