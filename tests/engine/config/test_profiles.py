"""Tests for the profile diff collector (spec §8 Config, BootUI ProfileDiffController)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

from conftest import SideEffectGuard
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.config.profiles import parse_env_lines, profiles_report
from sharpit.engine.context import SharpitContext
from sharpit.engine.masking import Exposure
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


def test_profile_sources_are_confined_and_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(project_root)

    # 1. Symlink pointing outside project root
    (outside / ".env.sym").write_text("OUTSIDE_KEY=val\n", encoding="utf-8")
    symlink_path = project_root / ".env.sym"
    try:
        symlink_path.symlink_to(outside / ".env.sym")
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    # 2. Oversized file (> 256 KiB)
    oversized = project_root / ".env.large"
    oversized.write_text("LARGE_KEY=" + "A" * (260 * 1024) + "\n", encoding="utf-8")

    # 3. Undecodable file
    undecodable = project_root / ".env.bad"
    undecodable.write_bytes(b"KEY=\xff\xfe\x00\x00bad\n")

    # 4. .. path escaping root
    escaped_dir = tmp_path / "escaped"
    escaped_dir.mkdir()
    (escaped_dir / ".env.esc").write_text("ESC_KEY=val\n", encoding="utf-8")

    # 5. Legitimate file
    (project_root / ".env.valid").write_text("VALID_KEY=valid_val\n", encoding="utf-8")

    declared = [".env.large", ".env.bad", "../escaped/.env.esc", ".env.valid"]
    if has_symlink:
        declared.insert(0, ".env.sym")

    class ConfinedSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=declared)

    ctx = _ctx(profiles=("valid",), settings=(ConfinedSettings.__new__(ConfinedSettings),))
    report = profiles_report(ctx)

    profiles = [s["profile"] for s in report["profileSources"]]
    assert "valid" in profiles
    assert "large" not in profiles
    assert "bad" not in profiles
    assert "esc" not in profiles
    if has_symlink:
        assert "sym" not in profiles


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
    assert len(report["profileSources"]) >= 1
    src = report["profileSources"][0]
    golden_src = golden_doc["profileSources"][0]
    assert set(src.keys()) == set(golden_src.keys())
    prop = src["properties"][0]
    golden_prop = golden_src["properties"][0]
    assert set(prop.keys()) == set(golden_prop.keys())


def test_profile_diff_has_no_side_effects(
    no_side_effects: SideEffectGuard, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.dev").write_text("app.name=sample\n", encoding="utf-8")

    class DevSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="allow", env_file=".env.dev")

    ctx = _ctx(profiles=("dev",), settings=(DevSettings(),))
    no_side_effects.rebaseline()
    report = profiles_report(ctx)
    assert report["profileSources"]
    assert no_side_effects.violations == []
