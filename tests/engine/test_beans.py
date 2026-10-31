from conftest import SideEffectGuard, golden
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.beans import beans_report
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.settings import SharpitSettings

PROVIDERS = [
    ProviderInfo(
        "app.deps:get_repo", "app.deps:get_repo", "request", "deps.py:3", ("app.deps:get_db",), "APPLICATION", None
    ),
    ProviderInfo("app.deps:get_db", "app.deps:get_db", "request", "deps.py:1", (), "APPLICATION", "app.tests:fake_db"),
    ProviderInfo("app.tests:fake_db", "app.tests:fake_db", "request", None, (), "APPLICATION", None),
    ProviderInfo("sharpit.x:probe", "sharpit.x:probe", "request", None, (), "BOOTUI", None),
    ProviderInfo("asyncio.locks:Lock", "asyncio.locks:Lock", "request", None, (), "PLATFORM", None),
]


class FakeIntrospector:
    def app_info(self) -> AppInfo:
        return AppInfo(None, "FastAPI", None, None)

    def routes(self) -> list[RouteInfo]:
        return []

    def providers(self) -> list[ProviderInfo]:
        return PROVIDERS


def _ctx() -> SharpitContext:
    return SharpitContext(SharpitSettings(), ActivationStatus(True, True, "on", ()), FakeIntrospector())


def test_shape_matches_golden_keys(no_side_effects: SideEffectGuard):
    gold = golden("beans")
    report = beans_report(_ctx(), None, None, None, None)
    assert set(report) == set(gold)
    bean_keys = set(gold["beans"][0])
    assert all(set(b) == bean_keys for b in report["beans"])
    assert set(report["page"]) == set(gold["page"])
    assert all(b["aliases"] == [] for b in report["beans"])


def test_sorted_by_name_with_overridden_by_in_resource():
    report = beans_report(_ctx(), None, None, None, None)
    assert [b["name"] for b in report["beans"]] == sorted(p.name for p in PROVIDERS)
    db = next(b for b in report["beans"] if b["name"] == "app.deps:get_db")
    assert db["resource"] == "deps.py:1 (overridden by app.tests:fake_db)"
    assert db["dependencies"] == []
    assert db["scope"] == "request"
    assert db["type"] == "app.deps:get_db"


def test_classification_bootui_filter():
    # the UI probes api/beans?classification=BOOTUI&offset=0&limit=1; BootUI trims and upper-cases the filter
    report = beans_report(_ctx(), None, " bootui ", 0, 1)
    assert [b["name"] for b in report["beans"]] == ["sharpit.x:probe"]
    assert report["total"] == 5
    assert report["page"] == {"total": 5, "matched": 1, "offset": 0, "limit": 1, "returned": 1, "hasMore": False}


def test_q_matches_name_or_type_combined_with_classification():
    report = beans_report(_ctx(), "APP.DEPS", "APPLICATION", None, None)
    assert [b["name"] for b in report["beans"]] == ["app.deps:get_db", "app.deps:get_repo"]
    assert report["page"]["total"] == 5
    assert report["page"]["matched"] == 2
