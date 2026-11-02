import platform
import re
import time

import pytest

from conftest import golden
from sharpit import __version__
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.overview import overview_dto
from sharpit.engine.context import SharpitContext
from sharpit.engine.panels import panels_report
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.settings import SharpitSettings

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())


class FakeIntrospector:
    def __init__(self, info: AppInfo) -> None:
        self.info = info

    def app_info(self) -> AppInfo:
        return self.info

    def routes(self) -> list[RouteInfo]:
        return []

    def providers(self) -> list[ProviderInfo]:
        return []


PETCLINIC = AppInfo("petclinic", "FastAPI", "0.115.0", "/docs")


def _ctx(info: AppInfo = PETCLINIC) -> SharpitContext:
    return SharpitContext(SharpitSettings(), ACTIVATION, FakeIntrospector(info), profiles=("dev",))


def test_overview_every_key_and_values():
    ctx = _ctx()
    ctx.startup_time_ms = 42
    dto = overview_dto(ctx, {"server": ("127.0.0.1", 8000), "app_root_path": "/host", "root_path": "/host/sharpit"})
    assert set(dto) == {*golden("overview"), "run"}  # BootUI 2.2.0 OverviewDto adds run (drift contract §2.2)
    assert dto == {
        "bootUiVersion": __version__,
        "applicationName": "petclinic",
        "frameworkName": "FastAPI",
        "frameworkVersion": "0.115.0",
        "javaVersion": platform.python_version(),
        "javaVendor": dto["javaVendor"],
        "activeProfiles": ["dev"],
        "defaultProfiles": [],
        "webApplicationType": "ASGI",
        "serverPort": 8000,
        "managementPort": None,
        "contextPath": "/host",
        "startupTimeMillis": 42,
        "activation": ACTIVATION.to_dto(),
        "openApiUrl": "/docs",
        "run": dto["run"],
    }
    assert dto["javaVendor"].startswith(platform.python_implementation())


def test_overview_unknowns_are_null():
    dto = overview_dto(_ctx(AppInfo(None, "FastAPI", None, None)), {})
    assert dto["applicationName"] == "application"
    assert dto["serverPort"] is None
    assert dto["contextPath"] is None
    assert dto["startupTimeMillis"] is None
    assert dto["frameworkVersion"] is None
    assert dto["openApiUrl"] is None


def test_lazy_is_memoised():
    ctx = _ctx()
    calls: list[int] = []

    def factory() -> int:
        calls.append(1)
        return len(calls)

    assert ctx.lazy("k", factory) == 1
    assert ctx.lazy("k", factory) == 1
    assert calls == [1]


HEX8 = re.compile(r"[0-9a-f]{8}")


# BootUI 2.2.0 OverviewDto.run / ApplicationRunDto (drift contract §2.2); the Scorecard title is pinned in test_panels
def test_overview_emits_run_metadata_and_scorecard_panel_title():
    before = int(time.time() * 1000)
    first, second = overview_dto(_ctx(), {})["run"], overview_dto(_ctx(), {})["run"]
    assert set(first) == {"instanceId", "runId", "ordinal", "startedAt"}
    assert HEX8.fullmatch(first["instanceId"])
    assert second["instanceId"] == first["instanceId"]  # one Python process is one instance
    assert HEX8.fullmatch(first["runId"])
    assert second["runId"] != first["runId"]
    assert first["ordinal"] >= 1
    assert second["ordinal"] == first["ordinal"] + 1
    assert first["startedAt"] >= before
    assert first["startedAt"] <= int(time.time() * 1000)
    assert titles_by_id()["overview"] == "Scorecard"


def titles_by_id() -> dict[str, str]:
    return {panel["id"]: panel["title"] for panel in panels_report(True, {}, {})["panels"]}


def test_overview_golden_parity():
    from golden import ROOT, assert_parity

    if not any(
        (ROOT / "overview").glob("*.json")
    ):  # shortcut: G0a writes the 2.2.0 capture; until then, nothing to compare
        pytest.skip("no BootUI 2.2.0 overview fixture yet (G0a)")
    assert_parity("overview", "default", overview_dto(_ctx(), {"server": ("127.0.0.1", 8000)}))
