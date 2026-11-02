"""The data collector: one row per mapped class, read without ever configuring a mapper (spec §7, §4)."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
import sqlalchemy as sa  # noqa: E402
from sqlalchemy import exc, orm  # noqa: E402
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship  # noqa: E402

from data_support import spy_on_configure  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.activation import ActivationStatus  # noqa: E402
from sharpit.engine.collectors import data  # noqa: E402
from sharpit.engine.context import SharpitContext  # noqa: E402
from sharpit.settings import SharpitSettings  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

# RepositoryDto keys (BOOTUI-CONTRACT-0.4-WAVE-A.md §1); sharpit adds ``table`` and ``relationships``.
DTO_KEYS = {
    "beanName",
    "repositoryInterface",
    "domainType",
    "idType",
    "storeModule",
    "customImplementation",
    "queryMethodCount",
    "fragmentCount",
}
EXTRA_KEYS = {"table", "relationships"}


def make_ctx(*models: object) -> SharpitContext:
    ctx = SharpitContext(SharpitSettings(), ActivationStatus(True, True, "on", ()), None)  # pyright: ignore[reportArgumentType]
    ctx.models = models
    return ctx


def owner_pet(module: str = __name__, other: str = "Pet", prefix: str = "") -> tuple[type[DeclarativeBase], type, type]:
    """A fresh declarative base with ``Owner`` (one-to-many to ``other``) and ``Pet``; nothing is configured."""

    class Base(DeclarativeBase):
        pass

    owner = type(
        "Owner",
        (Base,),
        {
            "__module__": module,
            "__tablename__": f"{prefix}owners",
            "id": mapped_column(sa.Integer, primary_key=True),
            "pets": relationship(other),
        },
    )
    pet = type(
        "Pet",
        (Base,),
        {
            "__module__": module,
            "__tablename__": f"{prefix}pets",
            "id": mapped_column(sa.Integer, primary_key=True),
            "owner_id": mapped_column(sa.ForeignKey(f"{prefix}owners.id")),
        },
    )
    return Base, owner, pet


@pytest.fixture
def configure_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return spy_on_configure(monkeypatch)


def test_lists_one_row_per_mapped_class() -> None:
    # ported: DataControllerTests.repositoriesReturnsSummaryForDiscoveredRepository
    base, _owner, _pet = owner_pet()

    report = data.repositories_report(make_ctx(base))

    assert report["total"] == 2
    assert report["springDataPresent"] is True
    assert [row["beanName"] for row in report["repositories"]] == ["Owner", "Pet"]
    row = report["repositories"][0]
    assert set(row) == DTO_KEYS | EXTRA_KEYS
    assert row["repositoryInterface"] == f"{__name__}.Owner"
    assert row["domainType"] == f"{__name__}.Owner"
    assert row["storeModule"] == "SQLAlchemy"
    assert row["idType"] == "Integer"
    assert row["table"] == "owners"
    assert row["customImplementation"] is None
    assert row["queryMethodCount"] is None
    assert row["fragmentCount"] is None


def test_no_models_is_unavailable() -> None:
    # ported: DataControllerTests.repositoriesReturnsEmptyReportWhenNoBeanFactory
    report = data.repositories_report(make_ctx())

    assert report["springDataPresent"] is False
    assert report["unavailableReason"] == data.NO_MODELS
    assert report["repositories"] == []
    assert report["total"] == 0


def test_empty_registry() -> None:
    # ported: DataControllerTests.repositoriesReturnsEmptyReportWhenNoRepositoryBeans
    class Base(DeclarativeBase):
        pass

    report = data.repositories_report(make_ctx(Base))

    assert report["springDataPresent"] is True
    assert report["repositories"] == []
    assert report["total"] == 0
    assert report["unavailableReason"] is None


def test_unconfigured_mapper_is_not_configured(configure_spy: list[str]) -> None:
    # derived: spec §7/§4 and PLAN Review Focus 1: a GET must never configure mappers (user code, may raise)
    base, _owner, _pet = owner_pet()

    report = data.repositories_report(make_ctx(base))

    assert report["total"] == 2
    assert configure_spy == []
    assert [row["relationships"] for row in report["repositories"]] == [None, None]
    assert data.UNCONFIGURED in report["warnings"]
    assert report["unavailableReason"] == data.UNCONFIGURED


def test_configured_mapper_lists_relationships() -> None:
    # derived: control for the guard above: once the app has queried, the relationships appear
    base, owner, _pet = owner_pet()
    sa.inspect(owner).relationships  # noqa: B018 - what the app's first query does

    report = data.repositories_report(make_ctx(base))

    assert report["total"] == 2
    assert report["repositories"][0]["relationships"] == [
        {"name": "pets", "target": f"{__name__}.Pet", "lazy": "select"}
    ]
    assert report["repositories"][1]["relationships"] == []
    assert report["unavailableReason"] is None
    assert report["warnings"] == []


def test_a_mapper_added_after_configure_is_not_configured(configure_spy: list[str]) -> None:
    # derived: a configured mapper in a registry with a pending one would configure it on ``.relationships``
    base, owner, _pet = owner_pet()
    sa.inspect(owner).relationships  # noqa: B018
    _late = type(  # held: a registry keeps its classes weakly
        "Late",
        (base,),
        {"__module__": __name__, "__tablename__": "late", "id": mapped_column(sa.Integer, primary_key=True)},
    )
    configure_spy.clear()

    report = data.repositories_report(make_ctx(base))

    assert report["total"] == 3
    assert configure_spy == []
    assert {row["beanName"]: row["relationships"] for row in report["repositories"]} == {
        "Late": None,
        "Owner": None,
        "Pet": None,
    }


def test_broken_registry_degrades(configure_spy: list[str]) -> None:
    # derived: PLAN Review Focus 2: a relationship to a missing class never raises out of the GET
    base, owner, _pet = owner_pet(other="Missing")

    report = data.repositories_report(make_ctx(base))

    assert report["total"] == 2
    assert configure_spy == []
    with pytest.raises(exc.InvalidRequestError):  # the app's own first query fails the same way
        sa.inspect(owner).relationships  # noqa: B018
    configure_spy.clear()

    after = data.repositories_report(make_ctx(base))

    assert after["total"] == 2
    assert configure_spy == []
    assert [row["relationships"] for row in after["repositories"]] == [None, None]
    assert data.UNCONFIGURED in after["warnings"]


def test_models_forms_dedupe() -> None:
    # derived: PLAN Review Focus 3: a base, its registry, the same base again and a stranger
    base, owner, _pet = owner_pet()
    sa.inspect(owner).relationships  # noqa: B018 - configured, so the only warning left is the stranger's
    stranger = object()

    found, warnings = data.registries((base, base.registry, base, stranger))
    report = data.repositories_report(make_ctx(base, base.registry, base, stranger))

    assert len(found) == 1
    assert len(warnings) == 1
    assert "object" in warnings[0]
    assert report["total"] == 2
    assert [row["beanName"] for row in report["repositories"]] == ["Owner", "Pet"]
    assert len(report["warnings"]) == 1


def test_a_registry_alone_is_accepted() -> None:
    # derived: spec §7: ``models=`` may be a declarative base, a ``registry``, or a list of them
    base, _owner, _pet = owner_pet()

    found, warnings = data.registries((base.registry,))

    assert found == [base.registry]
    assert warnings == []


def test_only_strangers_is_unavailable() -> None:
    # derived: nothing usable in models=: say so, never raise
    report = data.repositories_report(make_ctx(object(), "Base"))

    assert report["springDataPresent"] is False
    assert report["unavailableReason"] == data.NO_REGISTRY
    assert len(report["warnings"]) == 2


def test_one_bad_mapper_drops_only_its_row() -> None:
    # derived: every attribute read is guarded, so one broken mapper costs one row
    class Broken:
        configured = True
        local_table = SimpleNamespace(fullname="broken")

        @property
        def class_(self) -> type:
            raise RuntimeError("boom")

        primary_key = ()

    good = SimpleNamespace(
        class_=type("Good", (), {"__module__": "app.models"}),
        configured=True,
        primary_key=(),
        local_table=None,
        relationships=[],
    )
    registry = SimpleNamespace(mappers=[Broken(), good])

    report = data.repositories_report(make_ctx(registry))

    assert report["total"] == 1
    assert report["repositories"][0]["repositoryInterface"] == "app.models.Good"
    assert report["repositories"][0]["idType"] is None
    assert report["repositories"][0]["table"] is None
    assert len(report["warnings"]) == 1
    assert "boom" in report["warnings"][0]


def test_sqlalchemy_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # derived: PLAN Review Focus 5: SQLAlchemy not imported
    base, _owner, _pet = owner_pet()
    monkeypatch.delitem(sys.modules, "sqlalchemy")

    report = data.repositories_report(make_ctx(base))

    assert report["springDataPresent"] is False
    assert report["unavailableReason"] == sqla.UNAVAILABLE
    assert report["repositories"] == []
    assert report["total"] == 0


def test_sqlalchemy_older_than_two(monkeypatch: pytest.MonkeyPatch) -> None:
    # derived: PLAN Review Focus 5: SQLAlchemy 1.4 is imported but unsupported
    base, _owner, _pet = owner_pet()
    monkeypatch.setattr(sa, "__version__", "1.4.50")

    report = data.repositories_report(make_ctx(base))

    assert report["springDataPresent"] is False
    assert report["unavailableReason"] == sqla.unavailable_reason()
    assert "1.4.50" in report["unavailableReason"]
    assert report["total"] == 0


DETAIL_KEYS = {
    "beanName",
    "repositoryInterface",
    "domainType",
    "idType",
    "storeModule",
    "customImplementation",
    "methods",
    "fragments",
}
OWNER_PETS = {
    "name": "pets",
    "signature": "pets -> Pet",
    "origin": "APPLICATION",
    "query": None,
    "nativeQuery": False,
    "namedQuery": None,
}


def configured_owner_pet() -> tuple[type[DeclarativeBase], type, type]:
    """The models of ``owner_pet`` after the app's first query; callers hold all three (a registry holds weakly)."""
    models = owner_pet()
    sa.inspect(models[1]).relationships  # noqa: B018
    return models


def user_base(module: str, table: str) -> tuple[type[DeclarativeBase], type]:
    class Base(DeclarativeBase):
        pass

    user = type(
        "User",
        (Base,),
        {"__module__": module, "__tablename__": table, "id": mapped_column(sa.Integer, primary_key=True)},
    )
    return Base, user


def test_detail_by_bean_name() -> None:
    # ported: DataControllerTests.repositoryDetailLooksUpByBeanName
    base, _owner, _pet = configured_owner_pet()
    detail = data.repository_detail(make_ctx(base), "Owner")

    assert detail is not None
    assert set(detail) == DETAIL_KEYS | {"table", "unavailableReason"}
    assert detail["beanName"] == "Owner"
    assert detail["repositoryInterface"] == f"{__name__}.Owner"
    assert detail["domainType"] == f"{__name__}.Owner"
    assert detail["idType"] == "Integer"
    assert detail["storeModule"] == "SQLAlchemy"
    assert detail["table"] == "owners"
    assert detail["methods"] == [OWNER_PETS]
    assert detail["fragments"] == []
    assert detail["unavailableReason"] is None


def test_detail_by_fq_name() -> None:
    # ported: DataControllerTests.repositoryDetailLooksUpByFullyQualifiedInterfaceName
    base, _owner, _pet = configured_owner_pet()
    detail = data.repository_detail(make_ctx(base), f"{__name__}.Pet")

    assert detail is not None
    assert detail["beanName"] == "Pet"
    assert detail["methods"] == []


def test_detail_by_simple_name() -> None:
    # ported: DataControllerTests.repositoryDetailLooksUpBySimpleInterfaceName
    class Base(DeclarativeBase):
        pass

    _inner = type(  # held: a registry keeps its classes weakly
        "Inner",
        (Base,),
        {
            "__module__": "app.models",
            "__qualname__": "Outer.Inner",
            "__tablename__": "inner",
            "id": mapped_column(sa.Integer, primary_key=True),
        },
    )

    detail = data.repository_detail(make_ctx(Base), "Inner")

    assert detail is not None
    assert detail["beanName"] == "Outer.Inner"
    assert detail["repositoryInterface"] == "app.models.Outer.Inner"


def test_detail_unknown_is_none() -> None:
    # ported: DataControllerTests.repositoryDetailReturnsNotFoundForUnknownRepository
    base, _owner, _pet = configured_owner_pet()
    ctx = make_ctx(base)

    assert data.repository_detail(ctx, "Owner") is not None
    assert data.repository_detail(ctx, "Nope") is None
    assert data.repository_detail(make_ctx(), "Owner") is None


def test_detail_simple_name_collision() -> None:
    # derived: PLAN Review Focus 4: two ``User`` classes in two modules; FQ names tell them apart, a simple name
    # answers the first in sorted order whatever the order of models=
    base_b, _user_b = user_base("app_b.models", "users_b")
    base_a, _user_a = user_base("app_a.models", "users_a")
    ctx = make_ctx(base_b, base_a)

    first = data.repository_detail(ctx, "app_a.models.User")
    second = data.repository_detail(ctx, "app_b.models.User")
    simple = data.repository_detail(ctx, "User")

    assert first is not None
    assert second is not None
    assert simple is not None
    assert first["table"] == "users_a"
    assert second["table"] == "users_b"
    assert simple["repositoryInterface"] == "app_a.models.User"


def test_detail_unconfigured_has_no_methods(configure_spy: list[str]) -> None:
    # derived: an unconfigured registry gives no methods and says why; the lookup configures nothing
    base, _owner, _pet = owner_pet()

    detail = data.repository_detail(make_ctx(base), "Owner")

    assert detail is not None
    assert configure_spy == []
    assert detail["methods"] == []
    assert detail["unavailableReason"] == data.UNCONFIGURED


def test_cross_registry_new_mapper_is_not_configured(configure_spy: list[str]) -> None:
    # derived: spec §4: a new mapper in a registry that another registry depends on flags the dependent too
    class BaseB(DeclarativeBase):
        pass

    class Pet(BaseB):
        __tablename__ = "x_pets"
        id = mapped_column(sa.Integer, primary_key=True)
        owner_id = mapped_column(sa.ForeignKey("x_owners.id"))

    class BaseA(DeclarativeBase):
        metadata = BaseB.metadata

    class Owner(BaseA):
        __tablename__ = "x_owners"
        id = mapped_column(sa.Integer, primary_key=True)
        pets = relationship(Pet)

    sa.inspect(Owner)._check_configure()  # pyright: ignore[reportPrivateUsage] - configures both registries
    fired: list[object] = []
    sa.event.listen(orm.Mapper, "before_configured", lambda: fired.append(1))

    class Toy(BaseB):
        __tablename__ = "x_toys"
        id = mapped_column(sa.Integer, primary_key=True)
        broken = relationship("Missing")

    configure_spy.clear()
    report = data.repositories_report(make_ctx(BaseA))

    assert Toy is not None
    assert configure_spy == []
    assert fired == []
    assert report["total"] == 1
    assert report["repositories"][0]["relationships"] is None


def test_join_mapped_class_keeps_its_row() -> None:
    # derived: a class mapped to a Join has no ``fullname``; the row stays with table null
    meta = sa.MetaData()
    left = sa.Table("j_left", meta, sa.Column("id", sa.Integer, primary_key=True))
    right = sa.Table(
        "j_right", meta, sa.Column("id", sa.Integer, primary_key=True), sa.Column("l", sa.ForeignKey("j_left.id"))
    )
    registry = orm.registry()
    joined = type("Joined", (), {"__module__": "app.models"})
    registry.map_imperatively(
        joined,
        sa.join(left, right),
        properties={"lid": left.c.id, "rid": right.c.id},
        primary_key=[left.c.id, right.c.id],
    )

    report = data.repositories_report(make_ctx(registry))

    assert report["total"] == 1
    assert report["repositories"][0]["table"] is None
    assert report["repositories"][0]["idType"] == "Integer, Integer"


def test_failing_field_drops_only_that_field() -> None:
    # derived: a per-field failure nulls the field with a warning, never the row
    class Odd:
        configured = True
        local_table = None
        class_ = type("Odd", (), {"__module__": "app.models"})
        relationships = ()

        @property
        def primary_key(self) -> tuple[()]:
            raise RuntimeError("no pk")

    report = data.repositories_report(make_ctx(SimpleNamespace(mappers=[Odd()])))

    assert report["total"] == 1
    assert report["repositories"][0]["idType"] is None
    assert any("no pk" in warning for warning in report["warnings"])


def test_warnings_mask_exception_text() -> None:
    # derived: user-code exception text may quote a DSN; warnings go through the masker
    class Broken:
        configured = True

        @property
        def class_(self) -> type:
            raise RuntimeError("cannot connect postgresql://app:hunter2secret@db.local/prod")

    report = data.repositories_report(make_ctx(SimpleNamespace(mappers=[Broken()])))

    assert report["warnings"]
    assert "hunter2secret" not in " ".join(report["warnings"])


def test_mapped_class_with_a_mappers_column_is_accepted() -> None:
    # derived: a model may have a column named ``mappers``; entries are resolved through ``.registry``
    base, owner, _pet = owner_pet()
    owner.mappers = mapped_column(sa.Integer)  # pyright: ignore[reportAttributeAccessIssue]

    report = data.repositories_report(make_ctx(owner))

    assert report["total"] == 2
    assert base.registry is not None


def test_registry_lookup_never_runs_class_descriptors() -> None:
    # derived: spec §4: no user code (a hybrid property) runs while resolving ``models=``
    seen: list[str] = []

    class Probe:
        def __get__(self, instance: object, owner: type | None = None) -> list[object]:
            seen.append("run")
            return []

    base, owner, _pet = owner_pet()
    owner.mappers = Probe()  # pyright: ignore[reportAttributeAccessIssue]

    data.repositories_report(make_ctx(owner))

    assert base is not None
    assert seen == []


@pytest.mark.parametrize(
    ("lazy", "name"),
    [(None, "noload"), (True, "select"), (False, "joined"), ("dynamic", "dynamic"), ("selectin", "selectin")],
)
def test_lazy_is_a_strategy_name(lazy: object, name: str) -> None:
    # derived: relationship(lazy=...) accepts legacy None/True/False; report the strategy name
    pet = type("Pet", (), {"__module__": "app.models"})
    rel = SimpleNamespace(key="pets", mapper=SimpleNamespace(class_=pet), lazy=lazy)
    mapper = SimpleNamespace(
        class_=type("Owner", (), {"__module__": "app.models"}),
        configured=True,
        primary_key=(),
        local_table=None,
        relationships=[rel],
    )

    report = data.repositories_report(make_ctx(SimpleNamespace(mappers=[mapper])))

    assert report["repositories"][0]["relationships"] == [{"name": "pets", "target": "app.models.Pet", "lazy": name}]


def test_registry_subclass_new_mapper_is_not_configured(configure_spy: list[str]) -> None:
    # derived: spec §4: an app-defined subclass of ``registry`` gets the same ``_new_mappers`` check as the original
    class AppRegistry(orm.registry):
        pass

    class BaseB(DeclarativeBase):
        registry = AppRegistry()

    class Pet(BaseB):
        __tablename__ = "s_pets"
        id = mapped_column(sa.Integer, primary_key=True)
        owner_id = mapped_column(sa.ForeignKey("s_owners.id"))

    class BaseA(DeclarativeBase):
        metadata = BaseB.metadata
        registry = AppRegistry()

    class Owner(BaseA):
        __tablename__ = "s_owners"
        id = mapped_column(sa.Integer, primary_key=True)
        pets = relationship(Pet)

    sa.inspect(Owner)._check_configure()  # pyright: ignore[reportPrivateUsage] - configures both registries

    class Toy(BaseB):
        __tablename__ = "s_toys"
        id = mapped_column(sa.Integer, primary_key=True)
        broken = relationship("Missing")

    configure_spy.clear()
    report = data.repositories_report(make_ctx(BaseA))

    assert Toy is not None
    assert configure_spy == []
    assert report["repositories"][0]["relationships"] is None
    assert not any("Missing" in warning for warning in report["warnings"])
