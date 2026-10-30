from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import AnyUrl, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

import sharpit.engine.collectors.config as config_module
from conftest import SideEffectGuard, golden
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.config import config_report
from sharpit.engine.context import SharpitContext
from sharpit.engine.masking import MASK, Exposure
from sharpit.settings import SharpitSettings

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "getenv_corpus"


def _ctx(
    exposure: Exposure = Exposure.MASKED,
    mask: bool = True,
    settings: tuple[object, ...] = (),
    scan: tuple[str, ...] | bool = False,
    profiles: tuple[str, ...] = (),
) -> SharpitContext:
    sharpit_settings = SharpitSettings(expose_values=exposure, mask_secrets=mask, config_scan=scan)
    return SharpitContext(sharpit_settings, ACTIVATION, None, profiles=profiles, app_settings=settings)  # pyright: ignore[reportArgumentType]


def _report(
    ctx: SharpitContext,
    q: str | None = None,
    source: str | None = None,
    overrides_only: bool = False,
    offset: int | None = None,
    limit: int | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return config_report(ctx, q, source, overrides_only, offset, limit, environ=environ or {})


def _names(report: dict[str, Any]) -> list[str]:
    return [p["name"] for p in report["properties"]]


def _by_name(report: dict[str, Any], name: str) -> dict[str, Any]:
    return next(p for p in report["properties"] if p["name"] == name)


def _suggestion(report: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in report["propertySuggestions"] if s["name"] == name)


def _package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, source: str) -> None:
    pkg = tmp_path / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "conf.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))


# ---- ported ConfigServiceTests -------------------------------------------------------------------------------------


# ported: ConfigServiceTests.masksSecretValuesAndCountsOverridesAcrossFullSet
def test_masks_secret_values_and_counts_overrides_across_full_set():
    env = {"app.name": "demo", "app.password": "s3cr3t", "server.port": "8080"}
    report = _report(_ctx(profiles=("dev",)), environ=env)
    password = _by_name(report, "app.password")
    assert password["masked"] is True
    assert password["value"] == MASK
    assert _by_name(report, "app.name")["value"] == "demo"
    assert _by_name(report, "server.port")["override"] is False  # no override source in the MVP
    assert report["overrideCount"] == 0
    assert report["activeProfiles"] == ["dev"]


# ported: ConfigServiceTests.overrideCountReflectsFullSetNotPage
def test_override_count_reflects_full_set_not_page():
    env = {f"k{i}": "v" for i in range(5)}
    report = _report(_ctx(Exposure.FULL), offset=0, limit=2, environ=env)
    assert len(report["properties"]) == 2
    assert report["overrideCount"] == 0
    assert report["page"] == {"total": 5, "matched": 5, "offset": 0, "limit": 2, "returned": 2, "hasMore": True}


# ported: ConfigServiceTests.queryMatchesMaskedValueNeverRevealingSecret
def test_query_matches_masked_value_never_revealing_secret():
    env = {"app.password": "s3cr3t"}
    assert _report(_ctx(), q="s3cr3t", environ=env)["properties"] == []
    assert len(_report(_ctx(), q="app.password", environ=env)["properties"]) == 1


# ported: ConfigServiceTests.dottedQueryFindsAnEnvironmentVariableStyleName
def test_dotted_query_finds_an_environment_variable_style_name():
    report = _report(_ctx(Exposure.FULL), q="bootui.mcp.enabled", environ={"BOOTUI_MCP_ENABLED": "true"})
    assert len(report["properties"]) == 1
    assert report["properties"][0]["name"] == "BOOTUI_MCP_ENABLED"
    assert report["properties"][0]["source"] == "systemEnvironment"


# ported: ConfigServiceTests.environmentVariableStyleQueryFindsADottedName
def test_environment_variable_style_query_finds_a_dotted_name():
    report = _report(_ctx(Exposure.FULL), q="BOOTUI_MCP_ENABLED", environ={"bootui.mcp.enabled": "true"})
    assert _names(report) == ["bootui.mcp.enabled"]


# ported: ConfigServiceTests.kebabAndDottedSeparatorsAreInterchangeableInNameSearch
def test_kebab_and_dotted_separators_are_interchangeable_in_name_search():
    env = {"bootui.conformance.api-token": "x"}
    ctx = _ctx(Exposure.FULL, mask=False)
    assert len(_report(ctx, q="bootui.conformance.api.token", environ=env)["properties"]) == 1
    assert len(_report(ctx, q="bootui.conformance.api-token", environ=env)["properties"]) == 1


# ported: ConfigServiceTests.relaxedNameMatchingDoesNotWidenValueOrMetadataMatching
def test_relaxed_name_matching_does_not_widen_value_or_metadata_matching():
    class App(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="APP_")
        name: str = Field("demo_default", description="The app_name shown in the header.")

    ctx = _ctx(Exposure.FULL, mask=False, settings=(App(name="demo_value"),))
    for q in ("demo_value", "app_name shown", "demo_default"):
        assert len(_report(ctx, q=q)["properties"]) == 1, q
    for q in ("demo.value", "app.name shown", "demo.default"):
        assert _report(ctx, q=q)["properties"] == [], q


# ported: ConfigServiceTests.metadataOnlyExposureHidesAllValues
def test_metadata_only_exposure_hides_all_values():
    dto = _by_name(_report(_ctx(Exposure.METADATA_ONLY), environ={"app.name": "demo"}), "app.name")
    assert dto["value"] is None
    assert dto["masked"] is False


# ported: ConfigServiceTests.groupsProfileSourcesAndMasksValues
# Profile diff is deferred (spec 14); the masking expectation is pinned on the config report instead.
def test_groups_profile_sources_and_masks_values():
    report = _report(_ctx(profiles=("dev",)), environ={"db.secret": "x"})
    assert report["activeProfiles"] == ["dev"]
    assert _by_name(report, "db.secret")["value"] == MASK


# ---- sharpit additions ---------------------------------------------------------------------------------------------


def test_secret_default_masked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _package(tmp_path, monkeypatch, "jwtapp", 'import os\nJWT = os.getenv("JWT_SECRET", "dev-secret")\n')
    report = _report(_ctx(scan=("jwtapp",)))
    suggestion = _suggestion(report, "JWT_SECRET")
    assert suggestion["defaultValue"] == MASK
    assert suggestion["description"] == "jwtapp/conf.py:2"
    assert "dev-secret" not in str(report)


def test_q_cannot_probe_masked_value():
    assert _report(_ctx(), q="abc1", environ={"API_TOKEN": "abc123"})["page"]["matched"] == 0


def test_empty_user_url_password_masked_and_not_probeable():
    env = {"REDIS_URL": "redis://:redispw@localhost:6379/0"}
    assert _by_name(_report(_ctx(), environ=env), "REDIS_URL")["value"] == MASK
    assert _report(_ctx(), q="redispw", environ=env)["page"]["matched"] == 0


def test_masked_flag_describes_the_value_only():
    class App(BaseSettings):
        upstream: str = "postgres://user:hunter2@db/x"

    prop = _by_name(_report(_ctx(settings=(App(upstream="plain"),))), "UPSTREAM")
    assert (prop["value"], prop["defaultValue"], prop["masked"]) == ("plain", MASK, False)


def test_relaxed_q():
    assert _names(_report(_ctx(), q="my-prop", environ={"MY_PROP": "v"})) == ["MY_PROP"]


def test_source_filter_exact():
    class App(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="APP_")
        port: int = 80

    ctx = _ctx(settings=(App(),))
    env = {"OTHER": "1"}
    assert _names(_report(ctx, source="systemEnvironment", environ=env)) == ["OTHER"]
    assert _names(_report(ctx, source=" default (App) ", environ=env)) == ["APP_PORT"]
    assert _report(ctx, source="systemenvironment", environ=env)["properties"] == []
    assert _report(ctx, source="default", environ=env)["page"] == {
        "total": 2,
        "matched": 0,
        "offset": 0,
        "limit": 0,
        "returned": 0,
        "hasMore": False,
    }


def test_shape_matches_golden_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _package(tmp_path, monkeypatch, "shapeapp", 'import os\nX = os.getenv("SHAPE_UNSET")\n')
    expected = golden("config")
    report = _report(_ctx(scan=("shapeapp",)), environ={"A": "1"})
    assert set(report) == set(expected)
    assert set(report["properties"][0]) == set(expected["properties"][0])
    assert set(report["propertySuggestions"][0]) == set(expected["propertySuggestions"][0])
    assert set(report["page"]) == set(expected["page"])
    assert report["properties"][0]["origin"] is None
    assert report["sources"] == ["systemEnvironment"]


def test_overrides_only_is_empty():
    report = _report(_ctx(), overrides_only=True, environ={"A": "1"})
    assert report["properties"] == []
    assert report["page"]["total"] == 1


def test_properties_sorted_by_name():
    assert _names(_report(_ctx(), environ={"b": "1", "C": "1", "a": "1"})) == ["C", "a", "b"]


def test_settings_provenance_and_sources_order(monkeypatch: pytest.MonkeyPatch):
    class App(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="APP_")
        name: str = Field("n", description="The name")
        port: int = 80

    monkeypatch.setenv("APP_NAME", "x")
    report = _report(_ctx(settings=(App(port=81),)), environ={"APP_NAME": "x", "HOME": "/h"})
    assert report["sources"] == ["systemEnvironment", "init (App)"]
    name = _by_name(report, "APP_NAME")
    assert (name["value"], name["source"], name["description"], name["defaultValue"]) == (
        "x",
        "systemEnvironment",
        "The name",
        "n",
    )
    assert _by_name(report, "APP_PORT")["source"] == "init (App)"
    assert _by_name(report, "HOME")["source"] == "systemEnvironment"


def test_secret_typed_value_and_default_always_masked():
    class App(BaseSettings):
        signing: SecretStr = SecretStr("plain-default")
        hint: SecretStr = "plain-str-default"  # pyright: ignore[reportAssignmentType]  # pydantic does not validate defaults

    ctx = _ctx(mask=False, settings=(App(),))
    report = _report(ctx)
    for name in ("SIGNING", "HINT"):
        prop = _by_name(report, name)
        assert (prop["value"], prop["defaultValue"], prop["masked"]) == (MASK, MASK, True), name
    assert "plain" not in str(report)
    full = _report(_ctx(Exposure.FULL, settings=(App(),)))
    # FULL renders a SecretStr with str(): pydantic's placeholder, never the secret
    assert "plain-default" not in str(full)
    assert _by_name(full, "SIGNING")["value"] == "**********"


def test_sensitive_default_masked_and_hidden_under_metadata_only():
    class App(BaseSettings):
        db_password: str = "pw-default"

    assert _by_name(_report(_ctx(settings=(App(),))), "DB_PASSWORD")["defaultValue"] == MASK
    prop = _by_name(_report(_ctx(Exposure.METADATA_ONLY, settings=(App(),))), "DB_PASSWORD")
    assert (prop["value"], prop["defaultValue"]) == (None, None)


def test_non_string_values_are_stringified_before_masking():
    class Db(BaseModel):
        host: str = "h"
        password: str = "hunter2"

    class App(BaseSettings):
        database_url: AnyUrl = AnyUrl("postgres://user:hunter2@db/x")
        db: Db = Db()
        retries: int = 3

    report = _report(_ctx(settings=(App(),)))
    assert _by_name(report, "DATABASE_URL")["value"] == MASK
    assert _by_name(report, "DB")["value"] == MASK
    assert _by_name(report, "RETRIES")["value"] == 3
    assert "hunter2" not in str(report)


def test_getenv_suggestions_and_metadata_on_set_keys(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(CORPUS))
    report = _report(_ctx(scan=("pkg",)), environ={"FORM_B": "set"})
    names = [s["name"] for s in report["propertySuggestions"]]
    assert names == ["FORM_A", "FORM_C", "FORM_D", "FORM_E", "FORM_F"]
    assert _suggestion(report, "FORM_A") == {
        "name": "FORM_A",
        "type": None,
        "description": "pkg/forms.py:4",
        "defaultValue": "default-a",
    }
    form_b = _by_name(report, "FORM_B")
    assert (form_b["value"], form_b["description"], form_b["defaultValue"]) == ("set", "pkg/forms.py:5", None)


def test_suggestions_filtered_by_relaxed_name_or_description(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(CORPUS))
    ctx = _ctx(scan=("pkg",))
    assert [s["name"] for s in _report(ctx, q="form-a")["propertySuggestions"]] == ["FORM_A"]
    assert [s["name"] for s in _report(ctx, q="forms.py:7")["propertySuggestions"]] == ["FORM_D"]
    assert _report(ctx, q="default-a")["propertySuggestions"] == []  # defaults are values, not searchable


def test_unset_settings_field_is_a_suggestion():
    class App(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="APP_")
        api_url: str | None = Field(None, description="Upstream API")

    report = _report(_ctx(settings=(App(),)))
    assert report["properties"] == []
    assert report["propertySuggestions"] == [
        {"name": "APP_API_URL", "type": None, "description": "Upstream API", "defaultValue": None}
    ]


def test_scan_is_lazy_and_runs_once(monkeypatch: pytest.MonkeyPatch):
    calls: list[object] = []
    real = config_module.scan_packages

    def counting(roots: Any) -> Any:
        calls.append(roots)
        return real(roots)

    monkeypatch.setattr(config_module, "scan_packages", counting)
    monkeypatch.syspath_prepend(str(CORPUS))
    ctx = _ctx(scan=("pkg",))
    assert calls == []
    _report(ctx)
    _report(ctx, q="x")
    assert len(calls) == 1


def test_scan_disabled_and_unresolvable_roots(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(CORPUS))
    assert _report(_ctx(scan=False))["propertySuggestions"] == []
    assert _report(_ctx(scan=("no_such_package_xyz", "__main__", "sharpit")))["propertySuggestions"] == []


# ---- route ---------------------------------------------------------------------------------------------------------


def _client(**options: Any) -> TestClient:
    app = FastAPI()
    install(app, **{"enabled": "ON", "show_banner": False, **options})
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def test_install_captures_the_calling_module():
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    assert handle.context.caller_module == __name__


def test_route_shape_and_query_params(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SHARPIT_ROUTE_PROBE", "visible")
    monkeypatch.setenv("SHARPIT_ROUTE_TOKEN", "abc123")
    client = _client(config_scan=False)
    resp = client.get("/sharpit/api/config", params={"q": "sharpit-route", "limit": "1"})
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store, must-revalidate"
    body = resp.json()
    assert set(body) == set(golden("config"))
    assert body["page"]["matched"] == 2
    assert body["properties"][0]["name"] == "SHARPIT_ROUTE_PROBE"
    token = client.get("/sharpit/api/config", params={"q": "SHARPIT_ROUTE_TOKEN"}).json()["properties"][0]
    assert token["value"] == MASK
    assert client.get("/sharpit/api/config", params={"q": "abc12"}).json()["properties"] == []
    assert client.get("/sharpit/api/config", params={"overridesOnly": "true"}).json()["properties"] == []


def test_route_reports_installed_settings(monkeypatch: pytest.MonkeyPatch):
    class RouteApp(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="ROUTEAPP_")
        name: str = "n"
        signing: SecretStr = SecretStr("route-secret")

    monkeypatch.setenv("ROUTEAPP_NAME", "x")
    body = _client(config_scan=False, settings=[RouteApp()]).get("/sharpit/api/config", params={"q": "routeapp"}).json()
    props = {p["name"]: p for p in body["properties"]}
    assert (props["ROUTEAPP_NAME"]["value"], props["ROUTEAPP_NAME"]["source"]) == ("x", "systemEnvironment")
    assert props["ROUTEAPP_SIGNING"]["value"] == MASK
    assert "route-secret" not in str(body)


def test_route_bad_paging_is_400():
    resp = _client(config_scan=False).get("/sharpit/api/config", params={"offset": "x"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "Invalid 'offset' parameter"}


def test_route_disabled_panel_is_403():
    resp = _client(config_scan=False, panels={"config": {"enabled": False}}).get("/sharpit/api/config")
    assert resp.status_code == 403


def test_dotenv_in_cwd_not_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".env").write_text("SHARPIT_DOTENV_ONLY=leak\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    body = _client().get("/sharpit/api/config").json()
    assert "SHARPIT_DOTENV_ONLY" not in [p["name"] for p in body["properties"]]
    assert "SHARPIT_DOTENV_ONLY" not in [s["name"] for s in body["propertySuggestions"]]
    assert not any(s.startswith("dotenv") for s in body["sources"])


def test_config_get_no_side_effects(no_side_effects: SideEffectGuard, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(CORPUS))
    client = _client(config_scan=("pkg",))
    no_side_effects.unblock_network()  # the Windows Proactor loop TestClient starts connects a self-pipe socketpair
    with client:
        no_side_effects.block_network()
        for _ in range(2):
            body = client.get("/sharpit/api/config").json()
            assert "FORM_A" in [s["name"] for s in body["propertySuggestions"]]
    no_side_effects.verify()
