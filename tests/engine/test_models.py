"""The mapper walk lives in the engine (``engine/models.py``), so an ORM reader never imports the data collector."""

from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")
import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship  # noqa: E402

from data_support import spy_on_configure  # noqa: E402
from sharpit.engine import models  # noqa: E402
from sharpit.engine.collectors import data  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy


@pytest.fixture
def configure_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return spy_on_configure(monkeypatch)


def owner_pet() -> tuple[type[DeclarativeBase], type, type]:
    """A fresh declarative base with ``Owner`` (one-to-many to ``Pet``) and ``Pet``; nothing is configured."""

    class Base(DeclarativeBase):
        pass

    owner = type(
        "Owner",
        (Base,),
        {"__tablename__": "owners", "id": mapped_column(sa.Integer, primary_key=True), "pets": relationship("Pet")},
    )
    pet = type(
        "Pet",
        (Base,),
        {
            "__tablename__": "pets",
            "id": mapped_column(sa.Integer, primary_key=True),
            "owner_id": mapped_column(sa.ForeignKey("owners.id")),
        },
    )
    return Base, owner, pet


def test_mapper_walk_in_engine_never_configures(configure_spy: list[str]) -> None:
    # derived: 0.5.0 spec §4.4 (council H6): the walk and its configured-gate move to the engine, unchanged
    base, owner, _pet = owner_pet()

    found, warnings = models.registries((base, owner, base.registry, object()))
    configured = models.mappers_configured(base.registry, list(base.registry.mappers))

    assert found == [base.registry]
    assert len(warnings) == 1
    assert configured is False
    assert configure_spy == []
    assert data.registries is models.registries
