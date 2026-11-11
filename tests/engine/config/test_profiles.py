"""Tests for the profile diff collector (spec §8 Config, BootUI ProfileDiffController)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.config import config_report
from sharpit.engine.collectors.config.profiles import parse_env_lines, profiles_report
from sharpit.engine.context import SharpitContext
from sharpit.engine.masking import Exposure
from sharpit.engine.tool_dispatch import call_tool
from sharpit.engine.tools import CallContext
from sharpit.settings import SharpitSettings

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "bootui" / "2.3.0"


def _ctx(
    exposure: Exposure = Exposure.MASKED,
    mask: bool = True,
    settings: tuple[object, ...] = (),
    profiles: tuple[str, ...] = (),
) -> SharpitContext:
    sharpit_settings = SharpitSettings(expose_values=exposure, mask_secrets=mask)
    return SharpitContext(sharpit_settings, ACTIVATION, None, profiles=profiles, app_settings=settings)


# ported: ProfileDiffControllerTests.profilesMaskSecretValuesByDefault
def test_profiles_mask_secret_values_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.dev").write_text("sample.name=demo\nsample.password=secret\n", encoding="utf-8")

    class DevSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.dev")

    ctx = _ctx(profiles=("dev",), settings=(DevSettings(),))
    report = profiles_report(ctx)

    assert report["activeProfiles"] == ["dev"]
    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    assert source["profile"] == "dev"
    pwd = next(p for p in source["properties"] if p["name"] == "sample.password")
    assert pwd["masked"] is True
    assert pwd["value"] == "******"
    name = next(p for p in source["properties"] if p["name"] == "sample.name")
    assert name["masked"] is False
    assert name["value"] == "demo"


# ported: ProfileDiffControllerTests.profilesHideValuesUnderMetadataOnlyExposure
def test_profiles_hide_values_under_metadata_only_exposure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.dev").write_text("sample.name=demo\nsample.password=secret\n", encoding="utf-8")

    class DevSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.dev")

    ctx = _ctx(exposure=Exposure.METADATA_ONLY, profiles=("dev",), settings=(DevSettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    pwd = next(p for p in source["properties"] if p["name"] == "sample.password")
    assert pwd["value"] is None
    assert pwd["masked"] is False
    name = next(p for p in source["properties"] if p["name"] == "sample.name")
    assert name["value"] is None
    assert name["masked"] is False


# ported: ProfileDiffControllerTests.profilesExposeSecretValuesUnderFullExposure
def test_profiles_expose_secret_values_under_full_exposure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.dev").write_text("sample.name=demo\nsample.password=secret\n", encoding="utf-8")

    class DevSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.dev")

    ctx = _ctx(exposure=Exposure.FULL, profiles=("dev",), settings=(DevSettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    pwd = next(p for p in source["properties"] if p["name"] == "sample.password")
    assert pwd["masked"] is False
    assert pwd["value"] == "secret"


# ported: ProfileDiffMaskingTests.secretKeyInSingleProfileSourceIsMasked
def test_secret_key_in_single_profile_source_is_masked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.staging").write_text(
        "db.password=secret\ndb.url=postgres://localhost:5432/staging\n", encoding="utf-8"
    )

    class StagingSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.staging")

    ctx = _ctx(profiles=("staging",), settings=(StagingSettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    assert source["profile"] == "staging"
    pwd = next(p for p in source["properties"] if p["name"] == "db.password")
    assert pwd["masked"] is True
    assert pwd["value"] == "******"
    url = next(p for p in source["properties"] if p["name"] == "db.url")
    assert url["masked"] is False
    assert url["value"] == "postgres://localhost:5432/staging"


# ported: ProfileDiffMaskingTests.sameSecretKeyInTwoProfileSourcesBothMasked
def test_same_secret_key_in_two_profile_sources_both_masked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.dev").write_text("spring.datasource.password=dev-pass\n", encoding="utf-8")
    (tmp_path / ".env.prod").write_text("spring.datasource.password=prod-pass-different\n", encoding="utf-8")

    class AppSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=[".env.dev", ".env.prod"])

    ctx = _ctx(profiles=("dev", "prod"), settings=(AppSettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 2
    dev_src = next(s for s in report["profileSources"] if s["profile"] == "dev")
    prod_src = next(s for s in report["profileSources"] if s["profile"] == "prod")

    dev_pwd = next(p for p in dev_src["properties"] if p["name"] == "spring.datasource.password")
    assert dev_pwd["masked"] is True
    assert dev_pwd["value"] == "******"

    prod_pwd = next(p for p in prod_src["properties"] if p["name"] == "spring.datasource.password")
    assert prod_pwd["masked"] is True
    assert prod_pwd["value"] == "******"


# ported: ProfileDiffMaskingTests.integerPropertyValueStringifiedInDto
def test_integer_property_value_stringified_in_dto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.test").write_text("server.port=8080\napp.secret.count=42\n", encoding="utf-8")

    class TestSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.test")

    ctx = _ctx(profiles=("test",), settings=(TestSettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    port = next(p for p in source["properties"] if p["name"] == "server.port")
    assert port["value"] == "8080"
    assert port["masked"] is False
    cnt = next(p for p in source["properties"] if p["name"] == "app.secret.count")
    assert cnt["value"] == "******"
    assert cnt["masked"] is True


# ported: ProfileDiffMaskingTests.maskSecretsDisabledExposesSecretNamedKeyInPlainText
def test_mask_secrets_disabled_exposes_secret_named_key_in_plain_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.ci").write_text("api.token=plaintext-token\n", encoding="utf-8")

    class CiSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.ci")

    ctx = _ctx(mask=False, profiles=("ci",), settings=(CiSettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    tok = next(p for p in source["properties"] if p["name"] == "api.token")
    assert tok["masked"] is False
    assert tok["value"] == "plaintext-token"


# ported: ProfileDiffMaskingTests.nonSecretKeyIsNeverMaskedRegardlessOfValue
def test_non_secret_key_is_never_masked_regardless_of_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.perf").write_text("spring.application.name=boot-ui-perf\n", encoding="utf-8")

    class PerfSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.perf")

    ctx = _ctx(profiles=("perf",), settings=(PerfSettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    app_name = next(p for p in source["properties"] if p["name"] == "spring.application.name")
    assert app_name["masked"] is False
    assert app_name["value"] == "boot-ui-perf"


# ported: ProfileDiffMaskingTests.nullPropertyValueKeptAsNullInDto
def test_null_property_value_kept_as_null_in_dto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.nulltest").write_text("nullable.key=\n", encoding="utf-8")

    class NullSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.nulltest")

    ctx = _ctx(profiles=("nulltest",), settings=(NullSettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    entry = next(p for p in source["properties"] if p["name"] == "nullable.key")
    assert entry["value"] is None
    assert entry["masked"] is False


def test_profile_env_values_are_never_interpolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SECRET_FROM_ENVIRON", "super-secret-pw")
    (tmp_path / ".env.prod").write_text(
        "DATABASE_URL=postgresql://user:hunter2@db/prod\nINDIRECT=${SECRET_FROM_ENVIRON}\n", encoding="utf-8"
    )

    class ProdSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.prod")

    ctx = _ctx(profiles=("prod",), settings=(ProdSettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    indirect = next(p for p in source["properties"] if p["name"] == "INDIRECT")
    assert indirect["value"] == "${SECRET_FROM_ENVIRON}"
    assert "super-secret-pw" not in str(report)
    db = next(p for p in source["properties"] if p["name"] == "DATABASE_URL")
    assert db["masked"] is True
    assert "hunter2" not in str(db["value"])


def test_profile_diff_canary_secrets_masked_under_innocent_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    content = (
        "PUBLIC_ENDPOINT=https://user:secretpass@api.service.internal/v1\n"
        "CACHE_KEY_HEADER=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjYW5hcnkifQ.c2lnbmF0dXJlLWJ5dGVz\n"
        "EXTERNAL_ID=AKIAIOSFODNN7EXAMPLE\n"
        "PLAIN_NUMBER=12345\n"
    )
    (tmp_path / ".env.canary").write_text(content, encoding="utf-8")

    class CanarySettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.canary")

    ctx = _ctx(profiles=("canary",), settings=(CanarySettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    url_prop = next(p for p in source["properties"] if p["name"] == "PUBLIC_ENDPOINT")
    assert url_prop["masked"] is True
    assert "secretpass" not in str(url_prop["value"])

    jwt_prop = next(p for p in source["properties"] if p["name"] == "CACHE_KEY_HEADER")
    assert jwt_prop["masked"] is True
    assert jwt_prop["value"] == "******"

    aws_prop = next(p for p in source["properties"] if p["name"] == "EXTERNAL_ID")
    assert aws_prop["masked"] is True
    assert aws_prop["value"] == "******"

    plain_prop = next(p for p in source["properties"] if p["name"] == "PLAIN_NUMBER")
    assert plain_prop["masked"] is False
    assert plain_prop["value"] == "12345"


def test_profile_sources_are_confined_and_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)

    # 1. Oversized file (> 256 KiB)
    oversized = project_root / ".env.large"
    oversized.write_text("LARGE_KEY=" + "A" * (260 * 1024) + "\n", encoding="utf-8")

    # 2. Undecodable file
    undecodable = project_root / ".env.bad"
    undecodable.write_bytes(b"KEY=\xff\xfe\x00\x00bad\n")

    # 3. .. path escaping root
    escaped_dir = tmp_path / "escaped"
    escaped_dir.mkdir()
    (escaped_dir / ".env.esc").write_text("ESC_KEY=val\n", encoding="utf-8")

    # 4. Legitimate file
    (project_root / ".env.valid").write_text("VALID_KEY=valid_val\n", encoding="utf-8")

    declared = [".env.large", ".env.bad", "../escaped/.env.esc", ".env.valid"]

    class ConfinedSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=declared)

    ctx = _ctx(profiles=("valid",), settings=(ConfinedSettings.__new__(ConfinedSettings),))
    report = profiles_report(ctx)

    profiles = [s["profile"] for s in report["profileSources"]]
    assert "valid" in profiles
    assert "large" not in profiles
    assert "bad" not in profiles
    assert "esc" not in profiles


def test_profile_sources_confined_symlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(project_root)

    outside_file = outside / ".env.symoutside"
    outside_file.write_text("OUTSIDE_KEY=val\n", encoding="utf-8")
    symlink_outside = project_root / ".env.symoutside"

    inside_file = project_root / ".env.reallocal"
    inside_file.write_text("LOCAL_KEY=val\n", encoding="utf-8")
    symlink_inside = project_root / ".env.symlocal"

    try:
        symlink_outside.symlink_to(outside_file)
        symlink_inside.symlink_to(inside_file)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not supported or permitted on this platform: {exc}")

    class SymlinkSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=[".env.symoutside", ".env.symlocal"])

    ctx = _ctx(profiles=("symoutside", "symlocal"), settings=(SymlinkSettings.__new__(SymlinkSettings),))
    report = profiles_report(ctx)

    profiles = [s["profile"] for s in report["profileSources"]]
    assert "symoutside" not in profiles
    assert "symlocal" in profiles


def test_profile_sources_absolute_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)

    abs_file = project_root / ".env.abs"
    abs_file.write_text("ABS_KEY=abs_val\n", encoding="utf-8")

    class AbsSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=abs_file.resolve())

    ctx = _ctx(profiles=("abs",), settings=(AbsSettings.__new__(AbsSettings),))
    report = profiles_report(ctx)

    profiles = [s["profile"] for s in report["profileSources"]]
    assert "abs" in profiles


def test_profile_sources_follow_the_apps_env_file_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    pkg_dir = project_root / "src" / "myapp"
    pkg_dir.mkdir(parents=True)

    # .env.prod beside pyproject.toml
    (project_root / "pyproject.toml").write_text("[project]\nname='myapp'\n", encoding="utf-8")
    (project_root / ".env.prod").write_text("APP_MODE=production\n", encoding="utf-8")

    monkeypatch.chdir(project_root)

    class AppSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.prod")

    ctx = _ctx(profiles=("prod",), settings=(AppSettings(),))
    report = profiles_report(ctx)

    assert len(report["profileSources"]) == 1
    source = report["profileSources"][0]
    assert source["profile"] == "prod"
    mode = next(p for p in source["properties"] if p["name"] == "APP_MODE")
    assert mode["value"] == "production"


def test_profile_env_parser_edge_cases() -> None:
    content = (
        "\ufeff# Leading comment with BOM\n"
        "export KEY1=value1\r\n"
        "KEY2='single quoted with # inside'\n"
        'KEY3="double quoted with # inside and \\"escaped\\""\r\n'
        "# Another comment line\n"
        "KEY4=unquoted_val # inline comment\n"
        'KEY5=""\n'
        "KEY6=\n"
        "KEY7=bare value with spaces\n"
        "KEY8=\"nested 'single'\"\n"
        "KEY9='nested \"double\"'\n"
    )
    parsed = dict(parse_env_lines(content))
    expected = {
        "KEY1": "value1",
        "KEY2": "single quoted with # inside",
        "KEY3": 'double quoted with # inside and "escaped"',
        "KEY4": "unquoted_val",
        "KEY5": "",
        "KEY6": None,
        "KEY7": "bare value with spaces",
        "KEY8": "nested 'single'",
        "KEY9": 'nested "double"',
    }
    assert parsed == expected


def test_profile_diff_golden_shape_23(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.full").write_text("ledger.tenant.claim=tenant_id\n", encoding="utf-8")

    class FullSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.full")

    ctx = _ctx(profiles=("full",), settings=(FullSettings(),))
    report = profiles_report(ctx)

    golden_path = FIXTURES / "profile-diff" / "captured.json"
    golden_doc = json.loads(golden_path.read_text(encoding="utf-8"))

    assert set(report.keys()) == set(golden_doc.keys())
    assert report["activeProfiles"] == golden_doc["activeProfiles"]
    assert len(report["profileSources"]) >= 1
    src = report["profileSources"][0]
    golden_src = golden_doc["profileSources"][0]
    assert set(src.keys()) == set(golden_src.keys())
    assert src["profile"] == golden_src["profile"]
    prop = src["properties"][0]
    golden_prop = golden_src["properties"][0]
    assert set(prop.keys()) == set(golden_prop.keys())
    assert prop["name"] == golden_prop["name"]
    assert prop["value"] == golden_prop["value"]
    assert prop["masked"] == golden_prop["masked"]
    assert prop["override"] == golden_prop["override"]
    assert prop["description"] == golden_prop["description"]
    assert prop["defaultValue"] == golden_prop["defaultValue"]
    assert prop["origin"] == golden_prop["origin"]
    assert prop["source"] == src["sourceName"]


def test_profile_diff_has_no_side_effects(no_side_effects: SideEffectGuard, tmp_state_dir: Path) -> None:
    class DevSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.dev")

    app = FastAPI()
    install(
        app,
        show_banner=False,
        config_scan=False,
        enabled="ON",
        state_dir=str(tmp_state_dir),
        settings=DevSettings(),
    )
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    no_side_effects.unblock_network()
    with client:
        no_side_effects.block_network()
        no_side_effects.rebaseline()
        response = client.get("/sharpit/api/profile-diff")
        assert response.status_code == 200
        report = response.json()
        assert "profileSources" in report
    no_side_effects.verify()


def test_secret_str_innocent_name_masked_get_and_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHARPIT_PROFILES", "prod")
    (tmp_path / ".env.prod").write_text("SIGNING=plainsecretvalue123\n", encoding="utf-8")

    class S(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.prod")
        signing: SecretStr

    settings_inst = S(signing="plainsecretvalue123")

    app = FastAPI()
    handle = install(
        app,
        show_banner=False,
        config_scan=False,
        enabled="ON",
        settings=settings_inst,
    )
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    # 1. GET route
    resp = client.get("/sharpit/api/profile-diff")
    assert resp.status_code == 200
    report = resp.json()
    assert len(report["profileSources"]) == 1
    src = report["profileSources"][0]
    prop = next(p for p in src["properties"] if p["name"] == "SIGNING")
    assert prop["masked"] is True
    assert prop["value"] == "******"

    # 2. MCP tool
    mcp_report = call_tool(CallContext(handle.context, {}), "get_profile_diff", {}, via="mcp")
    assert len(mcp_report["profileSources"]) == 1
    mcp_src = mcp_report["profileSources"][0]
    mcp_prop = next(p for p in mcp_src["properties"] if p["name"] == "SIGNING")
    assert mcp_prop["masked"] is True
    assert mcp_prop["value"] == "******"

    # 3. Configuration parity check
    cfg = config_report(handle.context, None, None, False, None, None)
    cfg_prop = next(p for p in cfg["properties"] if p["name"] == "SIGNING")
    assert cfg_prop["masked"] is True
    assert cfg_prop["value"] == "******"


def test_multiline_private_key_env_parsing_get_and_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHARPIT_PROFILES", "prod")
    content = 'CERT="-----BEGIN RSA PRIVATE KEY-----\n...gunV==\npassword=hunter2\n-----END RSA PRIVATE KEY-----"\n'
    (tmp_path / ".env.prod").write_text(content, encoding="utf-8")

    class KeySettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.prod")

    app = FastAPI()
    handle = install(
        app,
        show_banner=False,
        config_scan=False,
        enabled="ON",
        settings=KeySettings(),
    )
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    # 1. GET route
    resp = client.get("/sharpit/api/profile-diff")
    assert resp.status_code == 200
    report = resp.json()
    assert len(report["profileSources"]) == 1
    src = report["profileSources"][0]
    names = [p["name"] for p in src["properties"]]
    assert names == ["CERT"]
    cert_prop = src["properties"][0]
    assert cert_prop["masked"] is True
    assert "hunter2" not in str(cert_prop["value"])
    assert "gunV" not in str(cert_prop["value"])
    assert all(p["name"] != "password" for p in src["properties"])
    assert all("gunV" not in p["name"] for p in src["properties"])

    # 2. MCP tool
    mcp_report = call_tool(CallContext(handle.context, {}), "get_profile_diff", {}, via="mcp")
    assert len(mcp_report["profileSources"]) == 1
    mcp_src = mcp_report["profileSources"][0]
    mcp_names = [p["name"] for p in mcp_src["properties"]]
    assert mcp_names == ["CERT"]
    mcp_cert = mcp_src["properties"][0]
    assert mcp_cert["masked"] is True
    assert "hunter2" not in str(mcp_cert["value"])
    assert all(p["name"] != "password" for p in mcp_src["properties"])


def test_env_file_encoding_honoured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHARPIT_PROFILES", "latin,badutf")
    (tmp_path / ".env.latin").write_bytes("SPECIAL_KEY=café\n".encode("latin-1"))
    (tmp_path / ".env.badutf").write_bytes(b"BAD=\xff\xfe\x00\x00\n")

    class LatinSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.latin", env_file_encoding="latin-1")

    class BadUtfSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.badutf")

    app = FastAPI()
    handle = install(
        app,
        show_banner=False,
        config_scan=False,
        enabled="ON",
        settings=(LatinSettings.__new__(LatinSettings), BadUtfSettings.__new__(BadUtfSettings)),
    )
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    # 1. GET route
    resp = client.get("/sharpit/api/profile-diff")
    assert resp.status_code == 200
    report = resp.json()
    profiles = [s["profile"] for s in report["profileSources"]]
    assert "latin" in profiles
    assert "badutf" not in profiles
    latin_src = next(s for s in report["profileSources"] if s["profile"] == "latin")
    prop = next(p for p in latin_src["properties"] if p["name"] == "SPECIAL_KEY")
    assert prop["value"] == "café"

    # 2. MCP tool
    mcp_report = call_tool(CallContext(handle.context, {}), "get_profile_diff", {}, via="mcp")
    mcp_profiles = [s["profile"] for s in mcp_report["profileSources"]]
    assert "latin" in mcp_profiles
    assert "badutf" not in mcp_profiles
    mcp_latin_src = next(s for s in mcp_report["profileSources"] if s["profile"] == "latin")
    mcp_prop = next(p for p in mcp_latin_src["properties"] if p["name"] == "SPECIAL_KEY")
    assert mcp_prop["value"] == "café"
