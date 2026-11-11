"""Tests for the runtime configuration overrides layer and overrides file store."""

from __future__ import annotations

import builtins
import os
import stat
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette

from sharpit.engine.collectors.config import overrides as overrides_mod
from sharpit.engine.collectors.config.overrides import (
    ConfigOverrideService,
    ConfigOverridesFileStore,
)
from sharpit.fastapi.install import install
from sharpit.settings import load_settings

_TOUCHED = (
    "server.port",
    "spring.datasource.password",
    "api.token",
    "a",
    "never.set",
    "safe.key",
    "another.key",
    "APP_CUSTOM_KEY",
    "LEGIT_KEY",
    "ANY_KEY",
    "EXISTING_VAR",
    "UNSET_VAR",
    "TEST_VAR",
    "FOO",
    "BAR",
    "STALE_VAR",
    "CASEVAR",
    "V",
    "GOOD1",
    "good1",
    "E1",
    "E2",
)


@pytest.fixture(autouse=True)
def _isolated_environ(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test leaks env or the module's saved originals into another."""
    saved = dict(os.environ)
    monkeypatch.setattr(overrides_mod, "_ORIGINAL_ENVIRON", {})
    for name in _TOUCHED:
        monkeypatch.delenv(name, raising=False)
    yield
    os.environ.clear()
    os.environ.update(saved)


def _raised(call: Callable[[], object]) -> Exception | None:
    """The exception a call raised, or None: a red then fails on an assertion, never on a crash."""
    try:
        call()
    except Exception as e:
        return e
    return None


def _install(file: Path) -> Any:
    return install(Starlette(), overrides_file=str(file), enabled="ON")


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


_REFUSED = (
    "PATH",
    "Path",
    "path",
    "PATHEXT",
    "ComSpec",
    "SystemRoot",
    "BASH_ENV",
    "ENV",
    "NODE_OPTIONS",
    "JAVA_TOOL_OPTIONS",
    "_JAVA_OPTIONS",
    "HTTP_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "GITHUB_TOKEN",
    "gh_token",
    "PYTHONPATH",
    "pythonpath",
    "PYTHONWARNINGS",
    "PythonFoo",
    "LD_PRELOAD",
    "ld_preload",
    "LD_LIBRARY_PATH",
    "LD_Anything",
    "DYLD_LIBRARY_PATH",
    "Dyld_Anything",
    "APP_ENV",
    "app_env",
    "Environment",
)


@pytest.mark.parametrize("key", _REFUSED)
def test_override_refuses_loader_names(tmp_path: Path, key: str) -> None:
    service = ConfigOverrideService(overrides_file=tmp_path / "overrides.env")
    before = dict(os.environ)
    error = _raised(lambda: service.put(key, "val"))
    assert isinstance(error, ValueError)
    assert "cannot be overridden" in str(error)
    assert dict(os.environ) == before
    assert service.overrides() == {}


def test_override_refuses_a_configured_profile_var(tmp_path: Path) -> None:
    settings = load_settings({"profile_vars": "MY_PROFILE_VAR"}, {})
    service = ConfigOverrideService(settings, overrides_file=tmp_path / "overrides.env")
    error = _raised(lambda: service.put("my_profile_var", "prod"))
    assert isinstance(error, ValueError)
    assert "MY_PROFILE_VAR" not in os.environ


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


def _spied(real: Callable[..., Any], file: Path, opened: list[str]) -> Callable[..., Any]:
    def wrapper(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == file:
            opened.append(str(self))
        return real(self, *args, **kwargs)

    return wrapper


def test_overrides_file_never_read_by_load_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "overrides.env"
    store = ConfigOverridesFileStore(file)
    store.save({"SHARPIT_READ_ONLY": "false"})
    opened: list[str] = []
    real_open: Callable[..., Any] = builtins.open

    def spy_open(path: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(path, str | Path) and Path(path) == file:
            opened.append(str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(Path, "read_text", _spied(Path.read_text, file, opened))
    monkeypatch.setattr(Path, "open", _spied(Path.open, file, opened))
    settings = load_settings({"overrides_file": str(file), "read_only": True}, {})
    assert opened == []
    assert settings.read_only is True
    store.load()  # the control: the spy does see a real read
    assert opened != []


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


def _fail_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_replace(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("Permission denied")

    monkeypatch.setattr(overrides_mod.os, "replace", failing_replace)


def test_override_write_failure_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=file)
    service.put("keep.me", "1")
    monkeypatch.setenv("TEST_VAR", "original")
    before = file.read_bytes()
    _fail_replace(monkeypatch)
    with pytest.raises(RuntimeError, match="Unable to write sharpit overrides file"):
        service.put("TEST_VAR", "new_val")
    assert os.environ["TEST_VAR"] == "original"
    assert service.overrides() == {"keep.me": "1"}
    assert file.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["overrides.env"]


def test_failed_put_leaves_no_stale_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = ConfigOverrideService(overrides_file=tmp_path / "overrides.env")
    with monkeypatch.context() as failing:
        _fail_replace(failing)
        error = _raised(lambda: service.put("STALE_VAR", "x"))
    assert isinstance(error, RuntimeError)
    monkeypatch.setenv("STALE_VAR", "external")
    service.put("STALE_VAR", "y")
    service.remove("STALE_VAR")
    assert os.environ.get("STALE_VAR") == "external"


@pytest.mark.skipif(os.name != "nt", reason="env names are case-insensitive on Windows only")
def test_windows_case_aliases_undo_to_the_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CaseVar", "orig")
    service = ConfigOverrideService(overrides_file=tmp_path / "overrides.env")
    service.put("CaseVar", "one")
    service.put("CASEVAR", "two")
    service.remove("CaseVar")
    service.remove("CASEVAR")
    assert os.environ.get("CASEVAR") == "orig"


def test_put_and_remove_are_serialised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = ConfigOverrideService(overrides_file=tmp_path / "overrides.env")
    real_save = service.store.save
    state = {"inflight": 0, "peak": 0}
    guard = threading.Lock()

    def slow_save(data: Any) -> None:
        with guard:
            state["inflight"] += 1
            state["peak"] = max(state["peak"], state["inflight"])
        time.sleep(0.05)
        real_save(data)
        with guard:
            state["inflight"] -= 1

    monkeypatch.setattr(service.store, "save", slow_save)
    threads = [threading.Thread(target=service.put, args=(f"K{i}", "v")) for i in range(2)]
    threads.append(threading.Thread(target=service.remove, args=("K0",)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert state["peak"] == 1


# --- hostile files and values: one validator, all or nothing, never raises ---


@pytest.mark.parametrize("raw", [r"x\u0000y", r"a\nb", r"a\rb"])
def test_hostile_file_value_applies_nothing_and_never_raises(tmp_path: Path, raw: str) -> None:
    file = tmp_path / "overrides.env"
    file.write_text(f'FOO="ok"\nBAR="{raw}"\n', encoding="utf-8")
    holder: list[Any] = []
    error = _raised(lambda: holder.append(_install(file)))
    assert error is None
    assert "FOO" not in os.environ
    assert "BAR" not in os.environ
    assert any("overrides" in w for w in holder[0].settings.warnings)


def test_oversized_file_value_applies_nothing(tmp_path: Path) -> None:
    file = tmp_path / "overrides.env"
    file.write_text('FOO="ok"\nBAR="' + "x" * (64 * 1024 + 1) + '"\n', encoding="utf-8")
    holder: list[Any] = []
    error = _raised(lambda: holder.append(_install(file)))
    assert error is None
    assert "FOO" not in os.environ
    assert any("overrides" in w for w in holder[0].settings.warnings)


def test_service_constructor_never_raises_on_a_bad_file(tmp_path: Path) -> None:
    file = tmp_path / "overrides.env"
    file.write_text('FOO="ok"\nBAR="x\\u0000y"\n', encoding="utf-8")
    holder: list[ConfigOverrideService] = []
    error = _raised(lambda: holder.append(ConfigOverrideService(overrides_file=file)))
    assert error is None
    assert holder[0].overrides() == {}
    garbage = tmp_path / "garbage.env"
    garbage.write_text("no equals sign here\n", encoding="utf-8")
    error = _raised(lambda: holder.append(ConfigOverrideService(overrides_file=garbage)))
    assert error is None


def test_file_cannot_smuggle_a_refused_name_by_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path_before = os.environ.get("PATH")
    file = tmp_path / "overrides.env"
    file.write_text('Path="/evil"\nLEGIT_KEY="v"\nNode_Options="--evil"\n', encoding="utf-8")
    monkeypatch.delenv("NODE_OPTIONS", raising=False)
    _install(file)
    assert os.environ.get("PATH") == path_before
    assert "NODE_OPTIONS" not in os.environ
    assert os.environ.get("LEGIT_KEY") == "v"


@pytest.mark.parametrize("raw", ["123", "[1]", "null", "true", '{"a": 1}'])
def test_file_non_string_value_applies_nothing(tmp_path: Path, raw: str) -> None:
    file = tmp_path / "overrides.env"
    file.write_text(f'FOO="ok"\nBAR={raw}\n', encoding="utf-8")
    handle = _install(file)
    assert "FOO" not in os.environ
    assert "BAR" not in os.environ
    assert any("overrides" in w for w in handle.settings.warnings)


@pytest.mark.parametrize("value", [123, [1], True, {"a": 1}])
def test_put_refuses_non_string_values(tmp_path: Path, value: object) -> None:
    service = ConfigOverrideService(overrides_file=tmp_path / "overrides.env")
    error = _raised(lambda: service.put("FOO", value))
    assert isinstance(error, ValueError)
    assert "FOO" not in os.environ


@pytest.mark.parametrize("line", ["password: hunter2 = x", 'FOO="unterminated hunter2', "hunter2"])
def test_malformed_file_warning_names_only_the_line_number(tmp_path: Path, line: str) -> None:
    file = tmp_path / "overrides.env"
    file.write_text(f"# header\n{line}\n", encoding="utf-8")
    handle = _install(file)
    joined = " ".join(handle.settings.warnings)
    assert "hunter2" not in joined
    assert "line 2" in joined


def test_load_accepts_a_utf8_bom(tmp_path: Path) -> None:
    file = tmp_path / "overrides.env"
    file.write_bytes(b'\xef\xbb\xbfFOO="bar"\n')
    holder: list[dict[str, str]] = []
    error = _raised(lambda: holder.append(ConfigOverridesFileStore(file).load()))
    assert error is None
    assert holder == [{"FOO": "bar"}]


def test_load_refuses_an_oversized_file(tmp_path: Path) -> None:
    file = tmp_path / "overrides.env"
    file.write_text("# pad\n" * (200 * 1024), encoding="utf-8")
    handle = _install(file)
    assert any("overrides" in w for w in handle.settings.warnings)
    error = _raised(lambda: ConfigOverridesFileStore(file).load())
    assert isinstance(error, ValueError)


def test_save_never_writes_through_an_existing_temp_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "overrides.env"
    monkeypatch.setattr(overrides_mod.secrets, "token_hex", lambda _n=4: "fixed")
    planted = tmp_path / ".overrides.env.tmp.fixed"
    planted.write_text("precious", encoding="utf-8")
    error = _raised(lambda: ConfigOverridesFileStore(file).save({"a": "1"}))
    assert isinstance(error, RuntimeError)
    assert planted.read_text(encoding="utf-8") == "precious"


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
def test_save_creates_parent_directories_user_only(tmp_path: Path) -> None:
    file = tmp_path / "nested" / "overrides.env"
    ConfigOverridesFileStore(file).save({"a": "1"})
    assert stat.S_IMODE(file.parent.stat().st_mode) == 0o700


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


# --- values the OS environment cannot hold ---

_UNREPRESENTABLE = [pytest.param("a" * 40000, id="40000-chars"), pytest.param("\ud800", id="lone-surrogate")]


@pytest.mark.parametrize("value", _UNREPRESENTABLE)
def test_put_refuses_values_the_environment_cannot_hold(tmp_path: Path, value: str) -> None:
    file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=file)
    error = _raised(lambda: service.put("V", value))
    assert isinstance(error, ValueError)
    assert "V" not in os.environ
    assert not file.exists()


@pytest.mark.parametrize("raw", ['"' + "a" * 40000 + '"', r'"\ud800"'], ids=["40000-chars", "lone-surrogate"])
def test_file_value_the_environment_cannot_hold_applies_nothing(tmp_path: Path, raw: str) -> None:
    file = tmp_path / "overrides.env"
    file.write_text(f'FOO="ok"\nV={raw}\n', encoding="utf-8")
    holder: list[Any] = []
    error = _raised(lambda: holder.append(_install(file)))
    assert error is None
    assert "FOO" not in os.environ
    assert "V" not in os.environ
    assert any("overrides" in w for w in holder[0].settings.warnings)


def _fail_nth_environ_write(monkeypatch: pytest.MonkeyPatch, n: int) -> None:
    real = os._Environ.__setitem__
    calls = {"n": 0}

    def flaky(self: Any, key: str, value: str) -> None:
        calls["n"] += 1
        if calls["n"] == n:
            raise OSError("environment write refused")
        real(self, key, value)

    monkeypatch.setattr(os._Environ, "__setitem__", flaky)


def test_failing_env_write_at_startup_applies_nothing_and_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "overrides.env"
    file.write_text('E1="one"\nE2="two"\n', encoding="utf-8")
    monkeypatch.setenv("E1", "orig")
    _fail_nth_environ_write(monkeypatch, 2)
    holder: list[Any] = []
    error = _raised(lambda: holder.append(_install(file)))
    assert error is None
    assert os.environ["E1"] == "orig"
    assert "E2" not in os.environ
    assert overrides_mod._ORIGINAL_ENVIRON == {}
    assert any("overrides" in w for w in holder[0].settings.warnings)
    assert not any("one" in w or "two" in w for w in holder[0].settings.warnings)


def test_failing_env_write_in_put_restores_file_map_and_originals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "overrides.env"
    service = ConfigOverrideService(overrides_file=file)
    service.put("keep.me", "1")
    before = file.read_bytes()
    originals = dict(overrides_mod._ORIGINAL_ENVIRON)
    _fail_nth_environ_write(monkeypatch, 1)
    error = _raised(lambda: service.put("E1", "new"))
    assert isinstance(error, RuntimeError)
    assert "E1" not in os.environ
    assert service.overrides() == {"keep.me": "1"}
    assert file.read_bytes() == before
    assert overrides_mod._ORIGINAL_ENVIRON == originals


@pytest.mark.skipif(os.name != "nt", reason="env names are case-insensitive on Windows only")
def test_windows_case_duplicates_in_a_file_apply_nothing(tmp_path: Path) -> None:
    file = tmp_path / "overrides.env"
    file.write_text('GOOD1="a"\ngood1="b"\n', encoding="utf-8")
    holder: list[Any] = []
    error = _raised(lambda: holder.append(_install(file)))
    assert error is None
    assert "GOOD1" not in os.environ
    assert any("overrides" in w for w in holder[0].settings.warnings)
