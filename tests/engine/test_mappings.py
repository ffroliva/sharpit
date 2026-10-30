from conftest import SideEffectGuard
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.mappings import mappings_flat
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.settings import SharpitSettings

ROUTES = [
    RouteInfo(("POST",), "/owners", "app.create", None, "application/json", "application/json", "create"),
    RouteInfo(("GET",), "/owners/{id}", "app.show", None, "application/json", None, "show"),
    RouteInfo(("GET", "POST"), "/both", "app.both", "example.com", None, None, None),
    RouteInfo((), "/static/{path}", "StaticFiles", None, None, None, "static"),
]
ROW_KEYS = {"method", "pattern", "handler", "produces", "consumes"}


class FakeIntrospector:
    def app_info(self) -> AppInfo:
        return AppInfo(None, "FastAPI", None, None)

    def routes(self) -> list[RouteInfo]:
        return ROUTES

    def providers(self) -> list[ProviderInfo]:
        return []


def _ctx() -> SharpitContext:
    return SharpitContext(SharpitSettings(), ActivationStatus(True, True, "on", ()), FakeIntrospector())


def test_shape_matches_contract_keys(no_side_effects: SideEffectGuard):
    # golden mappings.json is the raw Actuator descriptor (dropped); the flat shape is contract section 4
    report = mappings_flat(_ctx(), None, None, None)
    assert set(report) == {"total", "mappings", "page"}
    assert all(set(row) == ROW_KEYS for row in report["mappings"])
    assert set(report["page"]) == {"total", "matched", "offset", "limit", "returned", "hasMore"}


def test_one_row_per_method_empty_is_any_sorted():
    rows = [(r["method"], r["pattern"]) for r in mappings_flat(_ctx(), None, None, None)["mappings"]]
    assert rows == [
        ("GET", "/both"),
        ("POST", "/both"),
        ("POST", "/owners"),
        ("GET", "/owners/{id}"),
        ("ANY", "/static/{path}"),
    ]
    assert mappings_flat(_ctx(), None, None, None)["total"] == 5


def test_row_values_and_paging_and_q():
    report = mappings_flat(_ctx(), "app.show", 0, 10)
    assert report["mappings"] == [
        {
            "method": "GET",
            "pattern": "/owners/{id}",
            "handler": "app.show",
            "produces": "application/json",
            "consumes": None,
        }
    ]
    assert report["page"]["total"] == 5 and report["page"]["matched"] == 1
    assert mappings_flat(_ctx(), "get", 0, 1)["page"]["hasMore"] is True  # method matches case-insensitively
