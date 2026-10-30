import builtins
from pathlib import Path

import pytest
from pydantic import AliasChoices, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from sharpit.engine.collectors.config.settings_source import settings_entries


def by_name(entries):
    return {e.name: e for e in entries}


def test_env_prefix_and_provenance():
    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="APP_")
        name: str = Field("n", description="The name")
        port: int = 80

    env = {"APP_NAME": "x"}
    entries, sources = settings_entries(_make(Settings, env), env)
    e = by_name(entries)
    assert sources == ["systemEnvironment"]
    assert (e["APP_NAME"].value, e["APP_NAME"].source, e["APP_NAME"].description) == (
        "x",
        "systemEnvironment",
        "The name",
    )
    assert e["APP_NAME"].default == "n"
    assert (e["APP_PORT"].value, e["APP_PORT"].source) == (80, "default (Settings)")


def _make(cls, env, **kw):
    mp = pytest.MonkeyPatch()
    try:
        for k, v in env.items():
            mp.setenv(k, v)
        return cls(**kw)
    finally:
        mp.undo()


def test_validation_alias():
    class Settings(BaseSettings):
        url: str = Field("u", validation_alias=AliasChoices("MY_URL"))

    entries, _ = settings_entries(_make(Settings, {"MY_URL": "z"}), {"MY_URL": "z"})
    assert (entries[0].name, entries[0].value, entries[0].source) == ("MY_URL", "z", "systemEnvironment")


def test_secret_typed():
    class Settings(BaseSettings):
        token: SecretStr = SecretStr("t")
        other: str = "o"

    e = by_name(settings_entries(Settings(), {})[0])
    assert e["TOKEN"].secret_typed is True
    assert e["OTHER"].secret_typed is False


def test_environ_argument_is_used_not_process_env(monkeypatch):
    class Settings(BaseSettings):
        a: str = "d"

    inst = Settings()
    monkeypatch.setenv("A", "from-process")
    e = by_name(settings_entries(inst, {})[0])
    assert e["A"].source == "default (Settings)"


def test_environ_not_mutated():
    class Settings(BaseSettings):
        a: str = "d"

    env = {"A": "1"}
    settings_entries(Settings(a="1"), env)
    assert env == {"A": "1"}


def test_dotenv(tmp_path: Path):
    f = tmp_path / ".env"
    f.write_text("NAME=fromfile\n")

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=str(f))
        name: str = "n"

    entries, sources = settings_entries(Settings(), {})
    assert sources == ["systemEnvironment", f"dotenv: {f}"]
    assert (entries[0].value, entries[0].source) == ("fromfile", f"dotenv: {f}")


def test_env_beats_dotenv(tmp_path: Path):
    f = tmp_path / ".env"
    f.write_text("NAME=fromfile\n")

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=str(f))
        name: str = "n"

    entries, _ = settings_entries(_make(Settings, {"NAME": "e"}), {"NAME": "e"})
    assert (entries[0].value, entries[0].source) == ("e", "systemEnvironment")


def test_secrets_dir(tmp_path: Path):
    (tmp_path / "db_pass").write_text("sekret")

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(secrets_dir=str(tmp_path))
        db_pass: str = "d"

    entries, sources = settings_entries(Settings(), {})
    assert sources == ["systemEnvironment", f"secrets: {tmp_path}"]
    assert (entries[0].value, entries[0].source) == ("sekret", f"secrets: {tmp_path}")


def test_nested_delimiter():
    class Db(BaseModel):
        host: str = "h"
        port: int = 5

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="APP_", env_nested_delimiter="__")
        db: Db = Db()

    env = {"APP_DB__HOST": "dbhost"}
    e = by_name(settings_entries(_make(Settings, env), env)[0])
    assert (e["APP_DB__HOST"].value, e["APP_DB__HOST"].source) == ("dbhost", "systemEnvironment")
    assert (e["APP_DB__PORT"].value, e["APP_DB__PORT"].source) == (5, "default (Settings)")


def test_init_kwarg_and_default():
    class Settings(BaseSettings):
        a: str = "d"
        b: str = "d"

    e = by_name(settings_entries(Settings(a="x"), {})[0])
    assert e["A"].source == "init (Settings)"
    assert e["B"].source == "default (Settings)"


def test_custom_sources():
    class Settings(BaseSettings):
        a: str = "d"

        @classmethod
        def settings_customise_sources(
            cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
        ):
            return (init_settings,)

    entries, _ = settings_entries(Settings(), {})
    assert entries[0].source == "settings (Settings)"


def test_not_basesettings():
    assert settings_entries(object(), {}) == ([], [])


def test_pydantic_settings_missing(monkeypatch):
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("pydantic_settings"):
            raise ImportError(name)
        return real(name, *a, **k)

    class Settings(BaseSettings):
        a: str = "d"

    inst = Settings()
    monkeypatch.setattr(builtins, "__import__", fake)
    assert settings_entries(inst, {}) == ([], [])
