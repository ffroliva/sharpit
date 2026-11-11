"""Tests for the runtime configuration overrides layer and overrides file store."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette

from sharpit.engine.collectors.config.overrides import (
    ConfigOverrideService,
    ConfigOverridesFileStore,
)
from sharpit.fastapi.install import install
from sharpit.settings import load_settings


def test_put_registers_property_source_and_persists_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: ConfigOverrideServiceTests.putRegistersPropertySourceAndPersistsToDisk
    overrides_file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=overrides_file)
    result = service.put("server.port", "9090")
    assert result.name == "server.port"
    assert result.value == "9090"
    assert result.persisted is True
    assert result.previous_value is None
    assert "restart" in result.message
    assert os.environ.get("server.port") == "9090"  # noqa: SIM112
    assert overrides_file.exists()
    assert service.has_override("server.port") is True


def test_put_returns_previous_displayed_value(tmp_path: Path) -> None:
    # ported: ConfigOverrideServiceTests.putReturnsPreviousDisplayedValue
    overrides_file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=overrides_file)
    service.put("server.port", "9090")
    result = service.put("server.port", "9091")
    assert result.previous_value == "9090"
    assert result.value == "9091"


def test_put_masks_secret_values_in_result(tmp_path: Path) -> None:
    # ported: ConfigOverrideServiceTests.putMasksSecretValuesInResult
    overrides_file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=overrides_file)
    result = service.put("spring.datasource.password", "hunter2")
    assert result.value == "******"
    assert os.environ.get("spring.datasource.password") == "hunter2"  # noqa: SIM112


def test_put_does_not_mask_when_masking_disabled(tmp_path: Path) -> None:
    # ported: ConfigOverrideServiceTests.putDoesNotMaskWhenMaskingDisabled
    overrides_file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=overrides_file, mask_secrets=False)
    result = service.put("api.token", "abc")
    assert result.value == "abc"


def test_put_hides_values_under_metadata_only_exposure(tmp_path: Path) -> None:
    # ported: ConfigOverrideServiceTests.putHidesValuesUnderMetadataOnlyExposure
    overrides_file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=overrides_file, expose_values="METADATA_ONLY")
    result = service.put("server.port", "9090")
    assert result.value is None


def test_put_exposes_secret_values_under_full_exposure(tmp_path: Path) -> None:
    # ported: ConfigOverrideServiceTests.putExposesSecretValuesUnderFullExposure
    overrides_file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=overrides_file, expose_values="FULL")
    result = service.put("api.token", "abc")
    assert result.value == "abc"


def test_put_blank_name_throws(tmp_path: Path) -> None:
    # ported: ConfigOverrideServiceTests.putBlankNameThrows
    service = ConfigOverrideService(overrides_file=tmp_path / "overrides.env")
    with pytest.raises(ValueError, match="Property name must not be blank"):
        service.put("  ", "x")
    with pytest.raises(ValueError, match="Property name must not be blank"):
        service.put("", "x")


def test_remove_returns_previous_value_and_clears_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: ConfigOverrideServiceTests.removeReturnsPreviousValueAndClearsOverride
    overrides_file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=overrides_file)
    service.put("server.port", "9090")
    result = service.remove("server.port")
    assert result.previous_value == "9090"
    assert result.value is None
    assert service.has_override("server.port") is False
    assert "server.port" not in os.environ


def test_remove_returns_null_previous_when_not_set(tmp_path: Path) -> None:
    # ported: ConfigOverrideServiceTests.removeReturnsNullPreviousWhenNotSet
    service = ConfigOverrideService(overrides_file=tmp_path / "overrides.env")
    result = service.remove("never.set")
    assert result.previous_value is None
    assert result.value is None
    assert result.persisted is True


def test_overrides_returns_defensive_copy(tmp_path: Path) -> None:
    # ported: ConfigOverrideServiceTests.overridesReturnsDefensiveCopy
    service = ConfigOverrideService(overrides_file=tmp_path / "overrides.env")
    service.put("a", "1")
    snapshot = service.overrides()
    snapshot["a"] = "tampered"
    assert os.environ.get("a") == "1"  # noqa: SIM112
    assert service.overrides()["a"] == "1"


def test_blank_overrides_file_falls_back_to_default_path() -> None:
    # ported: ConfigOverrideServiceTests.blankOverridesFileFallsBackToDefaultPath
    service = ConfigOverrideService(overrides_file="   ")
    assert service.overrides_file == Path(".sharpit/overrides.env")


def test_load_returns_empty_map_when_file_missing(tmp_path: Path) -> None:
    # ported: ConfigOverridesFileStoreTests.loadReturnsEmptyMapWhenFileMissing
    store = ConfigOverridesFileStore(tmp_path / "missing.env")
    assert store.load() == {}


def test_save_creates_parent_directories_and_roundtrips(tmp_path: Path) -> None:
    # ported: ConfigOverridesFileStoreTests.saveCreatesParentDirectoriesAndRoundtrips
    file = tmp_path / "nested" / "dir" / "overrides.env"
    store = ConfigOverridesFileStore(file)
    values = {"server.port": "9090", "sample.greeting": "Bonjour"}
    store.save(values)
    assert file.exists()
    reloaded = ConfigOverridesFileStore(file).load()
    assert reloaded == values


def test_null_values_are_stored_as_empty_strings(tmp_path: Path) -> None:
    # ported: ConfigOverridesFileStoreTests.nullValuesAreStoredAsEmptyStrings
    file = tmp_path / "overrides.env"
    store = ConfigOverridesFileStore(file)
    store.save({"nullable": None})
    reloaded = store.load()
    assert reloaded == {"nullable": ""}


def test_save_overwrites_previous_contents(tmp_path: Path) -> None:
    # ported: ConfigOverridesFileStoreTests.saveOverwritesPreviousContents
    file = tmp_path / "overrides.env"
    store = ConfigOverridesFileStore(file)
    store.save({"a": "1", "b": "2"})
    store.save({"a": "11"})
    reloaded = store.load()
    assert reloaded == {"a": "11"}


def test_delete_removes_file_and_is_idempotent(tmp_path: Path) -> None:
    # ported: ConfigOverridesFileStoreTests.deleteRemovesFileAndIsIdempotent
    file = tmp_path / "overrides.env"
    store = ConfigOverridesFileStore(file)
    store.save({"a": "1"})
    assert file.exists()
    store.delete()
    assert not file.exists()
    store.delete()


def test_loading_malformed_file_surfaces_error(tmp_path: Path) -> None:
    # ported: ConfigOverridesFileStoreTests.loadingMalformedFileSurfacesError
    file = tmp_path / "bad.env"
    file.write_text("invalid_line_without_equals\n", encoding="utf-8")
    store = ConfigOverridesFileStore(file)
    with pytest.raises((ValueError, RuntimeError)):
        store.load()


def test_override_refuses_sharpit_keys(tmp_path: Path) -> None:
    service = ConfigOverrideService(overrides_file=tmp_path / "overrides.env")
    for key in ("SHARPIT_ENABLED", "sharpit.exposure", "Sharpit_Token"):
        with pytest.raises(ValueError, match="sharpit settings cannot be overridden at runtime."):
            service.put(key, "val")


def test_override_refuses_loader_names(tmp_path: Path) -> None:
    service = ConfigOverrideService(overrides_file=tmp_path / "overrides.env")
    for key in (
        "PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
    ):
        with pytest.raises(ValueError):
            service.put(key, "val")


def test_override_newline_cannot_inject_a_key(tmp_path: Path) -> None:
    file = tmp_path / "overrides.env"
    file.write_text("# initial\n", encoding="utf-8")
    service = ConfigOverrideService(overrides_file=file)
    service.put("safe.key", "val")
    original_content = file.read_text(encoding="utf-8")
    for bad_name in ("evil\nname", "evil\rname", "evil\0name"):
        with pytest.raises(ValueError):
            service.put(bad_name, "val")
    for bad_val in ("evil\nval", "evil\rval", "evil\0val"):
        with pytest.raises(ValueError):
            service.put("another.key", bad_val)
    assert file.read_text(encoding="utf-8") == original_content


def test_overrides_file_never_read_by_load_settings(tmp_path: Path) -> None:
    file = tmp_path / "overrides.env"
    store = ConfigOverridesFileStore(file)
    store.save({"SHARPIT_READ_ONLY": "false"})
    assert "SHARPIT_READ_ONLY" in store.load()
    settings = load_settings({"overrides_file": str(file), "read_only": True}, {})
    assert settings.read_only is True


def test_overrides_file_applied_only_when_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "overrides.env"
    store = ConfigOverridesFileStore(file)
    store.save({"APP_CUSTOM_KEY": "from_file"})
    monkeypatch.delenv("APP_CUSTOM_KEY", raising=False)

    app = Starlette()
    install(app, overrides_file=str(file), enabled="OFF")
    assert "APP_CUSTOM_KEY" not in os.environ

    app2 = Starlette()
    install(app2, overrides_file=str(file), enabled="ON")
    assert os.environ.get("APP_CUSTOM_KEY") == "from_file"


def test_overrides_file_cannot_set_sharpit_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "overrides.env"
    file.write_text(
        "# sharpit local runtime overrides - do not commit.\n"
        'SHARPIT_ENABLED="OFF"\n'
        'sharpit.exposure="FULL"\n'
        'PYTHONPATH="/evil"\n'
        'LEGIT_KEY="legit_val"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("LEGIT_KEY", raising=False)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    app = Starlette()
    handle = install(app, overrides_file=str(file), enabled="ON")
    assert os.environ.get("LEGIT_KEY") == "legit_val"
    assert os.environ.get("PYTHONPATH") != "/evil"
    assert handle.activation.enabled is True


def test_malformed_overrides_file_applies_nothing_and_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "bad.env"
    file.write_text("corrupted file without equals sign\n", encoding="utf-8")
    monkeypatch.delenv("ANY_KEY", raising=False)
    app = Starlette()
    handle = install(app, overrides_file=str(file), enabled="ON")
    assert any("overrides" in w.lower() for w in handle.settings.warnings)


def test_override_delete_restores_original_env_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=file)
    monkeypatch.setenv("EXISTING_VAR", "initial")
    monkeypatch.delenv("UNSET_VAR", raising=False)

    service.put("EXISTING_VAR", "changed")
    assert os.environ["EXISTING_VAR"] == "changed"
    service.remove("EXISTING_VAR")
    assert os.environ["EXISTING_VAR"] == "initial"

    service.put("UNSET_VAR", "created")
    assert os.environ["UNSET_VAR"] == "created"
    service.remove("UNSET_VAR")
    assert "UNSET_VAR" not in os.environ


def test_override_write_failure_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=file)
    monkeypatch.setenv("TEST_VAR", "original")

    def failing_save(data: Any) -> None:
        raise OSError("Permission denied")

    monkeypatch.setattr(service.store, "save", failing_save)
    with pytest.raises(RuntimeError, match="Unable to write sharpit overrides file"):
        service.put("TEST_VAR", "new_val")

    assert os.environ["TEST_VAR"] == "original"
    assert "TEST_VAR" not in service.overrides()


def test_overrides_file_is_user_only(tmp_path: Path) -> None:
    file = tmp_path / "overrides.env"
    store = ConfigOverridesFileStore(file)
    store.save({"a": "1"})
    if os.name == "nt":
        assert file.exists(), "File should be created"
        pytest.skip("ACLs are user-only on Windows")
    else:
        import stat

        mode = stat.S_IMODE(file.stat().st_mode)
        assert mode == 0o600


def test_read_never_creates_overrides_file(tmp_path: Path) -> None:
    file = tmp_path / "nonexistent" / "overrides.env"
    store = ConfigOverridesFileStore(file)
    assert store.load() == {}
    assert not file.exists()

    service = ConfigOverrideService(overrides_file=file)
    assert service.overrides() == {}
    assert not service.has_override("some.key")
    assert not file.exists()
