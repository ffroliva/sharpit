"""A ``Dialect`` is chosen by ``is None``, never by its truth: a falsy member must read the same.

derived: Task 12 review: ``x or dialect`` worked only because Enum members are truthy.
"""

from __future__ import annotations

import types

import pytest

from sharpit.engine.capture import traces
from sharpit.engine.capture.errortext import mask_error
from sharpit.engine.capture.sqlscan import normalize
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqla import orm
from sharpit.engine.sqltext import Dialect

MASKER = Masker(Exposure.MASKED, True)
SECRET = "hunter2"


def _false(_self: Dialect) -> bool:
    return False


@pytest.fixture
def falsy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Dialect, "__bool__", _false, raising=False)
    assert not Dialect.SQLITE


@pytest.mark.usefixtures("falsy")
def test_a_named_driver_reads_its_block_whatever_the_dialect_is() -> None:
    text = f"(pymysql.err.ProgrammingError) (1064, 'x')\n[SQL: select 1 # password {SECRET}\nfrom t]"
    assert SECRET not in (mask_error(MASKER, text, Dialect.UNSUPPORTED, known=True) or "")


@pytest.mark.usefixtures("falsy")
def test_an_orm_owner_names_its_dialect() -> None:
    owner = types.SimpleNamespace(dialect=types.SimpleNamespace(name="sqlite"))
    assert orm._dialect_of(owner) is Dialect.SQLITE  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


@pytest.mark.usefixtures("falsy")
def test_a_span_names_its_dialect() -> None:
    source = traces.SpanDialectSource()
    assert source.dialect_of({"db.system": "sqlite"}, traces.DialectContext(None)) is Dialect.SQLITE


@pytest.mark.parametrize("sql", ["", "select 1"])
def test_a_bool_is_no_dialect_for_empty_text_either(sql: str) -> None:
    with pytest.raises(KeyError):
        normalize(sql, True)  # pyright: ignore[reportArgumentType]
